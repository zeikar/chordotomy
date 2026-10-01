"""The lv-chordia engine: the chords from a pretrained recognizer instead of the DSP's templates.

lv-chordia is the ensemble of Jiang, Chen, Li & Xia (ISMIR 2019): five nets and an HMM decoder
over a chord dictionary. Its per-frame labels and scores are mapped to the v4 vocabulary and
snapped to the DSP's beat grid; the beats, the bass, the twin resolution and the harmony stay
the DSP's.

lv_chordia and torch are imported only inside the functions that run the nets, so importing this
module loads neither and the DSP path never pays for them.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
from itertools import pairwise

import numpy as np
from scipy.special import logsumexp

from .chords import LABELS
from .harmony import FLATS

NAME = "lv-chordia"
# lv_chordia/data/submission_chord_list.txt: 25 qualities on C, which the decoder transposes to
# 12 roots spelled C C# D Eb E F F# G Ab A Bb B, and N.
DICTIONARY = "submission"
# The nets' memory peak (CNN activations and im2col buffers) grows linearly with length, 3.5 GB
# at 3 min, so they run over windows of at most CHUNK_SECONDS, each with OVERLAP_SECONDS of
# context on both sides whose outputs are discarded, and the HMM decodes the stitched
# probabilities once. InstanceNorm and the BiLSTM then see at most 70 s, closer to the 23 s
# segments the nets were trained on than a whole song.
CHUNK_SECONDS = 60
OVERLAP_SECONDS = 5
# The dictionary's qualities, the slash dropped, to v4's; nothing maps to min6.
QUALITY = {
    "maj": "maj",
    "min": "min",
    "7": "7",
    "maj7": "maj7",
    "min7": "min7",
    "hdim7": "hdim7",
    "dim7": "dim7",
    "sus4": "sus4",
    "9": "7",  # loses the ninth
    "11": "7",  # loses the ninth and eleventh
    "13": "7",  # loses the ninth, eleventh and thirteenth
    "maj9": "maj7",  # loses the ninth
    "min9": "min7",  # loses the ninth
    "sus4(b7)": "sus4",  # loses the seventh
    "sus2": "maj",  # keeps root and function, loses the suspension: a third where a second sounds
    "aug": "maj",  # keeps root and function, loses the raised fifth
    # "dim" on a pop chart usually means the seventh chord; a diatonic vii° in major then reads
    # as a borrowed vii°7.
    "dim": "dim7",
}


class EngineError(Exception):
    """The model engine is installed but cannot run, as with a missing or damaged checkpoint."""


def available() -> bool:
    """Whether lv_chordia is installed; finding it does not import it, so torch stays unloaded."""
    return importlib.util.find_spec("lv_chordia") is not None


def version() -> str:
    """The installed lv-chordia package version."""
    return importlib.metadata.version("lv-chordia")


def to_label(name: str) -> str:
    """The v4 label of a dictionary name, such as Eb:maj/3 -> D#:maj.

    The slash is dropped: the bass comes from pick_bass, as on the DSP path.
    """
    if name == "N":
        return name
    root, quality = name.split(":")
    return f"{FLATS.get(root, root)}:{QUALITY[quality.partition('/')[0]]}"


def fold(names: list[str], logprob: np.ndarray) -> np.ndarray:
    """Fold the decoder's (n_frames, n_names) log-scores onto LABELS, shape (109, n_frames).

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
