"""The lv-chordia engine: the chords from a pretrained recognizer instead of the DSP's templates.

lv-chordia is the ensemble of Jiang, Chen, Li & Xia (ISMIR 2019): five nets and an HMM decoder
over a chord dictionary. Its per-frame labels and scores are mapped to the v5 vocabulary and
snapped to the DSP's beat grid; the beats, the bass, the twin resolution and the harmony stay
the DSP's.

lv_chordia and torch are imported only inside the functions that run the nets, so importing this
module loads neither and the DSP path never pays for them.
"""

from __future__ import annotations

import functools
import importlib.metadata
import importlib.resources
import importlib.util
import math
import pickle
import warnings
from itertools import pairwise
from pathlib import Path

import librosa
import numpy as np
from scipy.special import logsumexp

from .chords import LABELS
from .features import HOP, SR
from .harmony import FLATS

NAME = "lv-chordia"
# lv_chordia/data/submission_chord_list.txt: 25 qualities on C, which the decoder transposes to
# 12 roots spelled C C# D Eb E F F# G Ab A Bb B, and N.
DICTIONARY = "submission"
# The nets' memory peak (CNN activations and im2col buffers) grows linearly with length, 2.5 GB
# above the rest of the analysis at 3 minutes and 5.0 GB at 6. So they run over windows of at
# most CHUNK_SECONDS, each with OVERLAP_SECONDS of context on both sides whose outputs are
# discarded, and the HMM decodes the stitched probabilities once; that holds the nets' share at
# 1.1 GB at both lengths. InstanceNorm and the BiLSTM then see at most 70 s, closer to the 23 s
# segments the nets were trained on than a whole song.
CHUNK_SECONDS = 60
OVERLAP_SECONDS = 5
_REINSTALL = (
    "reinstall lv-chordia with `uv sync --extra model --reinstall-package lv-chordia`, "
    "or pass --engine dsp"
)
# The dictionary's qualities, the slash dropped, to v5's; nothing maps to min6. Every triad, sus
# and seventh maps exactly; only the extended chords lose tones.
QUALITY = {
    "maj": "maj",
    "min": "min",
    "7": "7",
    "maj7": "maj7",
    "min7": "min7",
    "hdim7": "hdim7",
    "dim7": "dim7",
    "sus4": "sus4",
    "sus2": "sus2",
    "aug": "aug",
    "dim": "dim",
    "9": "7",  # loses the ninth
    "11": "7",  # loses the ninth and eleventh
    "13": "7",  # loses the ninth, eleventh and thirteenth
    "maj9": "maj7",  # loses the ninth
    "min9": "min7",  # loses the ninth
    "sus4(b7)": "sus4",  # loses the seventh
}


class EngineError(Exception):
    """The model engine is installed but cannot run, as with a missing or damaged checkpoint."""


def available() -> bool:
    """Whether lv_chordia is installed; finding it does not import it, so torch stays unloaded."""
    return importlib.util.find_spec("lv_chordia") is not None


def version() -> str:
    """The installed lv-chordia package version."""
    try:
        return importlib.metadata.version("lv-chordia")
    except importlib.metadata.PackageNotFoundError as exc:
        raise EngineError(f"lv-chordia's package metadata is missing; {_REINSTALL}") from exc


def to_label(name: str) -> str:
    """The v5 label of a dictionary name, such as Eb:maj/3 -> D#:maj.

    The slash is dropped: the bass comes from pick_bass, as on the DSP path.
    """
    if name == "N":
        return name
    root, quality = name.split(":")
    root = FLATS.get(root, root)
    quality = quality.partition("/")[0]
    return f"{root}:{QUALITY[quality]}"


def fold(names: list[str], logprob: np.ndarray) -> np.ndarray:
    """Fold the decoder's (n_frames, n_names) log-scores onto LABELS, shape (157, n_frames).

    names and logprob are what XHMMDecoder.get_chord_tag_obs returns: per frame, the natural log
    of each name's joint probability under the nets' heads, not normalized over the names. A
    label's score is the log of the summed probability of the names that map to it; a label
    with none (every min6) is -inf.
    """
    rows = np.array([LABELS.index(to_label(name)) for name in names])
    scores = np.full((len(LABELS), logprob.shape[0]), -np.inf)
    for row in np.unique(rows):
        scores[row] = logsumexp(logprob[:, rows == row], axis=1)
    return scores


def beat_states(frame_states: np.ndarray, boundaries: list[int]) -> np.ndarray:
    """The majority LABELS index over each beat's frames.

    boundaries are the beat start frames followed by the frame count, as beat_features builds
    them. A tie goes to the lowest index, as in the DSP's decoder.
    """
    return np.array(
        [
            np.bincount(frame_states[start:end], minlength=len(LABELS)).argmax()
            for start, end in pairwise(boundaries)
        ]
    )


def beat_scores(frame_scores: np.ndarray, boundaries: list[int]) -> np.ndarray:
    """The mean of (m, n_frames) frame scores over each beat's frames, shape (m, n_beats)."""
    return np.stack(
        [frame_scores[:, start:end].mean(axis=1) for start, end in pairwise(boundaries)], axis=1
    )


def _cqt(y: np.ndarray) -> np.ndarray:
    """The nets' input: the (n_frames, 288) float32 CQT magnitude of a mono signal at SR.

    This is the package's own front end, extractors/cqt.py's CQTV2, run on the signal load_audio
    already decoded: CQTV2 reads the file through librosa.load at SR, mono, as load_audio does.
    The DSP's chord CQT runs on the harmonic part of the same signal, which has its length; same
    length, hop and centring, so the frame count is the same, 1 + len(y) // HOP, and frame k of
    one is frame k of the other.
    """
    cqt = librosa.hybrid_cqt(
        y,
        sr=SR,
        hop_length=HOP,
        fmin=librosa.note_to_hz("F#0"),
        n_bins=288,
        bins_per_octave=36,
        tuning=None,
    )
    return np.abs(cqt.T).astype(np.float32)


@functools.cache
def _networks() -> tuple:
    """The ensemble's five NetworkInterfaces, their bundled checkpoints loaded on the CPU."""
    try:
        # Outside the block below: catch_warnings restores the filter list on exit, which would
        # drop the filters torch installs when it is imported.
        import torch  # noqa: F401

        # pydub, which lv_chordia imports, has invalid escape sequences that Python warns about
        # when it compiles them on first import; they are pydub's to fix, not the user's. A
        # compile-time warning's module is its file path, hence the leading wildcard.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning, module=r".*pydub")
            from lv_chordia.chord_recognition import MODEL_NAMES
            from lv_chordia.chordnet_ismir_naive import ChordNet
            from lv_chordia.mir.common import CACHE_DATA_PATH
            from lv_chordia.mir.nn.train import NetworkInterface
    except ImportError as exc:
        raise EngineError(
            f"lv_chordia cannot be imported ({exc}); install the model extra with "
            "`uv sync --extra model`, or pass --engine dsp"
        ) from exc

    networks = []
    for name in MODEL_NAMES:
        path = Path(CACHE_DATA_PATH) / f"{name}.sdict"
        net = ChordNet(None)
        # NetworkBehavior sets use_gpu from torch.cuda.device_count(), and the interface's
        # placement, torch.load's map_location, inference and the LSTM's initial state all follow
        # it; cleared before the interface loads, the nets run on the CPU whatever torch is
        # installed.
        net.use_gpu = False
        try:
            # load_checkpoint=False only skips the training-time .cp.sdict fallback.
            interface = NetworkInterface(net, name, load_checkpoint=False)
        except (
            OSError,
            EOFError,
            RuntimeError,
            pickle.UnpicklingError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as exc:
            raise EngineError(f"{path} cannot be loaded ({exc!r}); {_REINSTALL}") from exc
        # The interface builds an untrained net without a word when the file is missing.
        if not interface.finalized:
            raise EngineError(f"{path} is missing from {CACHE_DATA_PATH}; {_REINSTALL}")
        networks.append(interface)
    return tuple(networks)


def _probabilities(cqt: np.ndarray) -> list[np.ndarray]:
    """The ensemble's six heads per frame of a (n_frames, 288) CQT, averaged over the nets.

    The nets run over ceil(length / CHUNK_SECONDS) equal windows, each with OVERLAP_SECONDS of
    context on both sides (clipped to the track) whose outputs are dropped. inference already
    runs under torch.no_grad().
    """
    n = cqt.shape[0]
    count = math.ceil(n / int(CHUNK_SECONDS * SR / HOP))
    size = math.ceil(n / count)
    overlap = round(OVERLAP_SECONDS * SR / HOP)
    windows = [(start, min(start + size, n)) for start in range(0, n, size)]
    nets = []
    for interface in _networks():
        parts = []
        for start, end in windows:
            low = max(start - overlap, 0)
            heads = interface.inference(cqt[low : min(end + overlap, n)])
            parts.append([head[start - low : end - low] for head in heads])
        nets.append([np.concatenate(head) for head in zip(*parts, strict=True)])
    # As chord_recognition averages them.
    return [np.mean(head, axis=0) for head in zip(*nets, strict=True)]


def _decoder():
    """The package's XHMMDecoder on the DICTIONARY chord list."""
    try:
        from lv_chordia.extractors.xhmm_ismir import XHMMDecoder
    except ImportError as exc:
        raise EngineError(
            f"lv_chordia cannot be imported ({exc}); install the model extra with "
            "`uv sync --extra model`, or pass --engine dsp"
        ) from exc

    template = importlib.resources.files("lv_chordia") / "data" / f"{DICTIONARY}_chord_list.txt"
    try:
        with importlib.resources.as_file(template) as path:
            return XHMMDecoder(template_file=str(path))
    except OSError as exc:
        raise EngineError(f"{template} cannot be read ({exc!r}); {_REINSTALL}") from exc


def recognize(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-frame LABELS indices and (157, n_frames) label scores of a mono signal at SR.

    The states are the decoder's smoothed labels, decoded without beats as chord_recognition
    does, so a chord can change on any frame; the scores are fold()'s, from the same
    probabilities before smoothing. Raises EngineError when the nets cannot be loaded.
    """
    probs = _probabilities(_cqt(y))
    decoder = _decoder()
    names, logprob = decoder.get_chord_tag_obs(probs)
    decoded = decoder.decode(probs, np.ones(logprob.shape[0], dtype=np.int8))
    index = {name: LABELS.index(to_label(name)) for name in names}
    return np.array([index[name] for name in decoded]), fold(names, logprob)
