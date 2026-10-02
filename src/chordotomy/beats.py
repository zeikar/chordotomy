"""The Beat This! beat grid for the model engine, and the weights it runs on.

Beat This! (Foscarin, Schlüter & Widmer, ISMIR 2024; code and weights MIT) finds beats and
downbeats with a transformer. Its checkpoint is not in the package: it is downloaded on first use
into the cache, pinned to a SHA-256 and checked on every load, and `chordotomy fetch-weights`
fetches it ahead of time.

beat_this and torch are imported only inside the functions that use them, so importing this
module loads neither and the DSP path never pays for them.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import os
import pickle
import tempfile
from collections.abc import Callable
from http.client import HTTPException
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import urlopen

import librosa
import numpy as np
from scipy.special import expit

from .features import HOP, SR, NoBeatsError
from .model import EngineError

if TYPE_CHECKING:
    from beat_this.model.beat_tracker import BeatThis

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
_REINSTALL = (
    "reinstall beat-this with `uv sync --extra model --reinstall-package beat-this`, "
    "or pass --engine dsp"
)

# beat_this.preprocessing.LogMelSpect's spectrogram, of a signal at SR as LogMelSpect expects:
# FPS frames a second, MEL_HOP = SR / FPS samples apart.
FPS = 50
N_FFT = 1024
MEL_HOP = 441
N_MELS = 128
FMIN = 30
FMAX = 11000
LOG_MULTIPLIER = 1000
# beat_this.inference.Spect2Frames: the net runs over chunks of the 30 s it was trained on and drops
# BORDER_FRAMES of each chunk's output at both ends, edges it was not trained on (split_piece).
CHUNK_FRAMES = 1500
BORDER_FRAMES = 6


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
    """Whether the cached checkpoint exists, can be read, and matches the pinned size and SHA-256.

    Checked on every load, about 0.03 s here for 81 MB, rather than recorded once, so a copied or
    damaged file never runs. A file that cannot be read, as a root-owned one left by a sudo
    fetch-weights, is not verified either, so fetch replaces it instead of the CLI raising.
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
    except OSError:
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
        # Present but unreadable or failing the pin (damaged, a different file, or another
        # user's): it goes like a bad download.
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


@functools.cache
def _tracker(name: str) -> BeatThis:
    """The named checkpoint's BeatThis net, fetched (again) if the cache lacks it or it fails the
    pin, and loaded on the CPU."""
    try:
        import torch
        from beat_this.model.beat_tracker import BeatThis
        from beat_this.utils import replace_state_dict_key
    except ImportError as exc:
        raise EngineError(
            f"beat_this cannot be imported ({exc}); install the model extra with "
            "`uv sync --extra model`, or pass --engine dsp"
        ) from exc

    path = fetch(name)
    # beat_this.inference.load_model's steps; that module imports torchaudio. map_location keeps
    # every tensor on the CPU and nothing moves the net, so it runs there whatever torch sees.
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        # The hyperparameters include the training run's; final0's lack sum_head and
        # partial_transformers, which then take BeatThis's defaults.
        accepted = inspect.signature(BeatThis).parameters
        net = BeatThis(**{k: v for k, v in checkpoint["hyper_parameters"].items() if k in accepted})
        # The Lightning module held the net as its "model" attribute.
        net.load_state_dict(replace_state_dict_key(checkpoint["state_dict"], "model.", ""))
    except (
        OSError,
        EOFError,
        RuntimeError,
        pickle.UnpicklingError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        # fetch has just checked the file against its pin, so fetching it again cannot help.
        raise EngineError(
            f"the Beat This! checkpoint {path} matches its pin but the installed beat_this or "
            f"torch cannot load it ({exc!r}); {_REINSTALL}"
        ) from exc
    return net.eval()


def _log_mel(y: np.ndarray) -> np.ndarray:
    """The net's input: the (1 + len(y) // MEL_HOP, N_MELS) log-mel spectrogram of a signal at SR.

    A replica of beat_this.preprocessing.LogMelSpect, which is torchaudio's MelSpectrogram with
    mel_scale="slaney", normalized="frame_length" and power=1, built from torch.stft and librosa's
    Slaney filterbank so torchaudio is never imported. It matches LogMelSpect to 2e-5.
    """
    import torch

    magnitude = torch.stft(
        torch.as_tensor(y, dtype=torch.float32),
        n_fft=N_FFT,
        hop_length=MEL_HOP,
        window=torch.hann_window(N_FFT),
        center=True,
        pad_mode="reflect",
        normalized=True,
        return_complex=True,
    ).abs()
    bank = librosa.filters.mel(
        sr=SR, n_fft=N_FFT, n_mels=N_MELS, fmin=FMIN, fmax=FMAX, htk=False, norm=None
    )
    return torch.log1p(LOG_MULTIPLIER * (torch.from_numpy(bank) @ magnitude)).T.numpy()


def _chunked(spect: np.ndarray, run: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    """Per-frame outputs of run over a (n_frames, bins) spectrogram, run on chunks of CHUNK_FRAMES.

    beat_this.inference's split_piece(avoid_short_end=True) and
    aggregate_prediction(overlap_mode="keep_first"): the chunks start BORDER_FRAMES before the
    piece and overlap by 2 * BORDER_FRAMES, the last one ends at the piece's end, and each is
    zero-padded by at most BORDER_FRAMES where it runs past either end, so a piece of at most
    CHUNK_FRAMES - 2 * BORDER_FRAMES frames runs as one shorter chunk. Of each chunk's output the
    BORDER_FRAMES at both ends are dropped, and where the kept spans overlap the earlier chunk's
    is kept.
    """
    n = len(spect)
    step = CHUNK_FRAMES - 2 * BORDER_FRAMES
    starts = list(range(-BORDER_FRAMES, n - BORDER_FRAMES, step))
    if n > step:
        starts[-1] = n - (CHUNK_FRAMES - BORDER_FRAMES)
    out = np.empty(n, dtype=np.float32)
    # Last chunk first, so each earlier chunk overwrites the overlap.
    for start in reversed(starts):
        left = max(-start, 0)
        right = max(0, min(BORDER_FRAMES, start + CHUNK_FRAMES - n))
        chunk = np.pad(spect[max(start, 0) : start + CHUNK_FRAMES], ((left, right), (0, 0)))
        kept = run(chunk)[BORDER_FRAMES:-BORDER_FRAMES]
        out[start + BORDER_FRAMES : start + BORDER_FRAMES + len(kept)] = kept
    return out


def logits(y: np.ndarray) -> np.ndarray:
    """The net's beat logit per FPS frame of a mono signal at SR, 1 + len(y) // MEL_HOP of them.

    Raises EngineError when the net cannot be loaded.
    """
    # First, so a missing torch is _tracker's EngineError rather than an ImportError.
    net = _tracker(CHECKPOINT)
    import torch

    def run(chunk: np.ndarray) -> np.ndarray:
        return net(torch.as_tensor(chunk, dtype=torch.float32)[None])["beat"][0].numpy()

    with torch.inference_mode():
        return _chunked(_log_mel(y), run)


def has_peaks(values: np.ndarray) -> bool:
    """Whether Beat This!'s own peak picking finds a beat in these logits.

    Postprocessor.postp_minimal keeps a frame as a beat when it is the maximum of the 7-frame
    window centred on it (max_pool1d(7, 1, 3)) and its logit is above 0, a probability over 0.5.
    For finite logits the global maximum is such a frame whenever any logit is above 0, and no
    frame is when none is, so the gate is this one test, needs no torch, and the deduplication of
    adjacent peaks cannot change it.
    """
    return bool(np.any(values > 0))


def resample(values: np.ndarray, n_frames: int) -> np.ndarray:
    """A series at FPS linearly interpolated onto n_frames frames HOP samples apart at SR."""
    times = librosa.frames_to_time(np.arange(n_frames), sr=SR, hop_length=HOP)
    return np.interp(times, np.arange(len(values)) / FPS, values)


def activation(y: np.ndarray) -> np.ndarray:
    """The model engine's onset envelope for beat_features: the net's beat probability per HOP
    frame of a mono signal at SR, 1 + len(y) // HOP float64 values.

    Raises NoBeatsError when Beat This! finds no beat, and EngineError when the net cannot be
    loaded.
    """
    # torch.stft's reflect padding needs more samples than the N_FFT // 2 it pads, so it raises
    # RuntimeError on a shorter signal, and 23 ms holds no beat. The DSP's beat_features raises
    # NoBeatsError on every signal up to 1,024 samples (measured), so the engines agree here.
    if len(y) <= N_FFT // 2:
        raise NoBeatsError("no beats detected")
    beat_logits = logits(y)
    # The one-tempo DP puts beats into digital silence, 10 in 4 s of zeros, so the gate is
    # Beat This!'s own peak picking.
    if not has_peaks(beat_logits):
        raise NoBeatsError("no beats detected")
    return resample(expit(beat_logits), 1 + len(y) // HOP)
