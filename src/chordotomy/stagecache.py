"""An on-disk cache of analyze's slow stages, for scoring many variants of what follows them.

`chordotomy evaluate --cache` keeps three stages per recording: Beat This!'s activation, the beat
features and lv-chordia's frames. They are most of an analysis; what follows them (the bass, the
segments, the twins, the harmony) and the scoring take under a second a song, so a change there
rescores a dataset in seconds once the stages are cached.

An entry is keyed by its stage, its input and the stage's fingerprint: the source of every function
and class the stage reaches by name in the package or in the stage's own module, the values of the
constants they read, and the versions of the packages they call. The fingerprint is taken on every
call, so an edited file and a constant a sweep reassigns both miss the cache, and a stale entry is
never served. Code reached only another way, through a string or a callback argument, is not seen.
Old entries stay behind, and deleting the directory is always safe.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import os
import pickle
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

# What a stage's output can depend on outside the package: the libraries it calls, and through
# them their own native code and weights (lv-chordia's checkpoints ship in its wheel; Beat This!'s
# are pinned by their SHA-256 in beats.CHECKPOINTS, a constant the fingerprint reads).
PACKAGES = ("numpy", "scipy", "librosa", "soxr", "torch", "lv-chordia", "beat-this")


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "absent"


def _names(code: Any) -> set[str]:
    """The global and attribute names a code object uses, nested functions and lambdas included."""
    names = set(code.co_names)
    for constant in code.co_consts:
        if inspect.iscode(constant):
            names |= _names(constant)
    return names


class _Hasher:
    """A SHA-256 over code and values, walking what a function reaches by name."""

    def __init__(self, local: str) -> None:
        self.digest = hashlib.sha256()
        self.local = local
        self.seen: set[int] = set()

    def ours(self, module: str | None) -> bool:
        return bool(module) and (module.partition(".")[0] == __package__ or module == self.local)

    def feed(self, value: Any) -> None:
        if hasattr(value, "__wrapped__"):  # functools.cache and other wrappers
            value = inspect.unwrap(value)
        if inspect.ismodule(value) or inspect.isfunction(value) or inspect.isclass(value):
            self._feed_code(value)
        elif isinstance(value, np.ndarray):
            self.digest.update(f"array{value.dtype}{value.shape}".encode())
            self.digest.update(np.ascontiguousarray(value).tobytes())
        elif isinstance(value, dict):
            self.digest.update(b"{")
            for key in sorted(value, key=repr):
                self.feed(key)
                self.feed(value[key])
            self.digest.update(b"}")
        elif isinstance(value, set | frozenset):
            self.digest.update(b"set(")
            for item in sorted(value, key=repr):
                self.feed(item)
            self.digest.update(b")")
        elif isinstance(value, list | tuple):
            self.digest.update(f"{type(value).__name__}(".encode())
            for item in value:
                self.feed(item)
            self.digest.update(b")")
        else:
            # A value whose repr changes from run to run only misses the cache.
            self.digest.update(f"{type(value).__qualname__}:{value!r};".encode())

    def _feed_code(self, value: Any) -> None:
        module = value.__name__ if inspect.ismodule(value) else value.__module__
        if not self.ours(module):
            # Another package's code: PACKAGES' versions stand for it.
            self.digest.update(f"<{module}.{getattr(value, '__qualname__', '')}>".encode())
            return
        if id(value) in self.seen or inspect.ismodule(value):
            # A module of ours counts through the names read from it (below).
            return
        self.seen.add(id(value))
        self.digest.update(inspect.getsource(value).encode())
        if inspect.isclass(value):
            for member in vars(value).values():
                if inspect.isfunction(member):
                    self.feed(member)
            return
        names = sorted(_names(value.__code__))
        scope = value.__globals__
        for name in names:
            if name not in scope:
                continue
            target = scope[name]
            self.feed(target)
            # chords.match: a name read as an attribute of a module of ours.
            if inspect.ismodule(target) and self.ours(target.__name__):
                for attribute in names:
                    if attribute in vars(target):
                        self.feed(vars(target)[attribute])
        for default in [*(value.__defaults__ or ()), *(value.__kwdefaults__ or {}).values()]:
            self.feed(default)


def fingerprint(stage: Callable) -> str:
    """The hex digest of what decides `stage`'s output besides its arguments."""
    hasher = _Hasher(stage.__module__)
    hasher.digest.update(";".join(f"{name}={_version(name)}" for name in PACKAGES).encode())
    hasher.feed(stage)
    return hasher.digest.hexdigest()


class StageCache:
    """Stage results under `root`, one pickle per stage, input and fingerprint."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, stage: Callable, *args: Any, **kwargs: Any) -> Path:
        hasher = _Hasher(stage.__module__)
        hasher.digest.update(fingerprint(stage).encode())
        hasher.feed(list(args))
        hasher.feed(kwargs)
        name = f"{stage.__module__}.{stage.__qualname__}"
        return self.root / f"{name}-{hasher.digest.hexdigest()}.pkl"

    def run(self, stage: Callable, *args: Any, **kwargs: Any) -> Any:
        """`stage(*args, **kwargs)`, read back if this stage, code and input ran before."""
        path = self.path(stage, *args, **kwargs)
        try:
            return pickle.loads(path.read_bytes())
        except (FileNotFoundError, EOFError, pickle.UnpicklingError):
            # Not cached yet, or a damaged entry: computed and written over below.
            pass
        result = stage(*args, **kwargs)
        self.root.mkdir(parents=True, exist_ok=True)
        # Written beside its name and moved into place, so a reader never sees half a file.
        fd, temporary = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(pickle.dumps(result))
            os.replace(temporary, path)
        except BaseException:
            os.unlink(temporary)
            raise
        return result
