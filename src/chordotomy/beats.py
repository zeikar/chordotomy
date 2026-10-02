"""The Beat This! beat grid for the model engine, and the weights it runs on.

Beat This! (Foscarin, Schlüter & Widmer, ISMIR 2024; code and weights MIT) finds beats and
downbeats with a transformer. Its checkpoint is not in the package: it is downloaded on first use
into the cache, pinned to a SHA-256 and checked on every load, and `chordotomy fetch-weights`
fetches it ahead of time.

beat_this and torch are imported only inside the functions that run the net, so importing this
module loads neither and the DSP path never pays for them.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from http.client import HTTPException
from pathlib import Path
from urllib.request import urlopen

from .model import EngineError

CHECKPOINT = "final0"
# beat_this.inference.CHECKPOINT_URL, copied because that module imports torchaudio and so cannot
# be read without the extra.
CHECKPOINT_URL = "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp"
# name -> (SHA-256, bytes). The pin is ours, not the server's: the URL has changed once before.
CHECKPOINTS = {
    "final0": ("8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331", 81_058_141),
}
CACHE_DIR: Path | None = None
_TIMEOUT = 30  # seconds per socket operation, not for the whole download
_CHUNK = 1 << 20
_REFETCH = "run `chordotomy fetch-weights` once online, or pass --engine dsp"


def cache_dir() -> Path:
    """CACHE_DIR if set, else $XDG_CACHE_HOME/chordotomy, else ~/.cache/chordotomy."""
    if CACHE_DIR is not None:
        return CACHE_DIR
    # An empty XDG_CACHE_HOME counts as unset, per the XDG spec.
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base) if base else Path.home() / ".cache") / "chordotomy"


def checkpoint_path(name: str = CHECKPOINT) -> Path:
    return cache_dir() / f"beat_this-{name}.ckpt"


def verified(name: str = CHECKPOINT) -> bool:
    """Whether the cached checkpoint exists and matches the pinned size and SHA-256.

    Checked on every load, about 0.03 s here for 81 MB, rather than recorded once, so a copied or
    damaged file never runs.
    """
    digest, size = CHECKPOINTS[name]
    path = checkpoint_path(name)
    try:
        if path.stat().st_size != size:
            return False
        sha = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(_CHUNK):
                sha.update(chunk)
    except FileNotFoundError:
        return False
    return sha.hexdigest() == digest


def fetch(name: str = CHECKPOINT) -> Path:
    """The verified checkpoint's path, downloading it first if the cache does not hold it.

    A plain GET of a fixed URL that carries nothing about the audio. torch.hub would fetch the
    same file but never checks a hash, so this streams to a temp file, checks the pin, and only
    then moves it into place; a download that fails the pin is not kept.
    """
    path = checkpoint_path(name)
    if verified(name):
        return path
    digest, size = CHECKPOINTS[name]
    url = f"{CHECKPOINT_URL}/{name}.ckpt"
    tmp = None
    try:
        # Present but failing the pin: damaged or a different file, so it goes like a bad download.
        path.unlink(missing_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256()
        count = 0
        with (
            urlopen(url, timeout=_TIMEOUT) as response,
            tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as out,
        ):
            tmp = Path(out.name)
            while chunk := response.read(_CHUNK):
                out.write(chunk)
                sha.update(chunk)
                count += len(chunk)
        if count != size:
            raise EngineError(
                f"the download from {url} has {count} bytes, not the pinned {size}, and was not "
                f"kept; {_REFETCH}"
            )
        if sha.hexdigest() != digest:
            raise EngineError(
                f"the download from {url} does not match the pinned SHA-256 and was not kept; "
                f"{_REFETCH}"
            )
        os.replace(tmp, path)
        tmp = None
    except (OSError, HTTPException) as exc:
        raise EngineError(
            f"cannot fetch the Beat This! weights from {url} into {path} ({exc}); {_REFETCH}"
        ) from exc
    finally:
        # Anything but a completed replace, KeyboardInterrupt included, leaves no temp file.
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return path
