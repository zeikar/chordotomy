"""An on-disk cache of analyze's slow stages, for scoring many variants of what follows them.

`chordotomy evaluate --cache` keeps three stages per recording: Beat This!'s activation, the beat
features and lv-chordia's frames. They are most of an analysis; what follows them (the bass, the
segments, the twins, the harmony) and the scoring take under a second a song, so a change there
rescores a dataset in seconds once the stages are cached.

An entry is keyed by its stage, its input, the stage's fingerprint and the dependencies. The
fingerprint is the source of every function and class the stage reaches by name in the package or
in the stage's own module, and the values of the constants they read; it is taken on every call, so
an edited file and a constant a sweep reassigns both miss the cache. The dependencies are the
libraries in PACKAGES, each by its version and the size and modification time of every file it
installed (lv-chordia's weights and dictionary among them), read when the cache is made and again
at the start of every evaluate run (refresh): a dependency changed during a run is seen by the next,
and the entries written after the change carry a key no later run makes unless its files return to
their old size and time. Every stage keys on
every dependency, since torch, lv-chordia and beat-this are imported inside the functions that use
them, where the fingerprint cannot tell which stage reaches which; a model upgrade recomputes all
three. Not seen: code reached only through a string or a callback argument, and the source tree of
a dependency installed as editable. Old entries stay behind; deleting the directory is always safe.
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

# What a stage's output can depend on outside the package: the libraries it calls, with their
# native code and data (lv-chordia's checkpoints and chord dictionary ship in its wheel). Beat
# This!'s weights live outside it, pinned by their SHA-256 in beats.CHECKPOINTS, a constant the
# fingerprint reads, and checked on every load.
PACKAGES = ("numpy", "scipy", "librosa", "soxr", "torch", "lv-chordia", "beat-this")


def _package(name: str) -> str:
    """A package's version and the size and modification time of every file it installed.

    Stat, not content: torch alone installs thousands of files, and a reinstall or an edit changes
    either.
    """
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return "absent"
    digest = hashlib.sha256()
    for file in sorted(distribution.files or [], key=str):
        try:
            stat = Path(file.locate()).stat()
        except FileNotFoundError:
            digest.update(f"{file}:missing;".encode())
            continue
        digest.update(f"{file}:{stat.st_size}:{stat.st_mtime_ns};".encode())
    return f"{distribution.version}+{digest.hexdigest()}"


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
    """The hex digest of the package code and constants that decide `stage`'s output."""
    hasher = _Hasher(stage.__module__)
    hasher.feed(stage)
    return hasher.digest.hexdigest()


class StageCache:
    """Stage results under `root`, one pickle per stage, input, fingerprint and dependencies."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.refresh()

    def refresh(self) -> None:
        """Read the dependencies again: once per run, as stat-ing torch's files takes 0.5 s."""
        self.dependencies = ";".join(f"{name}={_package(name)}" for name in PACKAGES)

    def path(self, stage: Callable, *args: Any, **kwargs: Any) -> Path:
        hasher = _Hasher(stage.__module__)
        hasher.digest.update(self.dependencies.encode())
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
