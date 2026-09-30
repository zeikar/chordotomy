"""Chord vocabulary and template matching."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise

import librosa
import numpy as np

ROOTS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
QUALITIES = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10)}
LABELS = [f"{root}:{quality}" for root in ROOTS for quality in QUALITIES] + ["N"]


def _build_templates() -> np.ndarray:
    templates = np.zeros((len(LABELS), 12))
    for row, label in enumerate(LABELS):
        if label == "N":
            templates[row] = 1.0  # N is the flat template
            continue
        root, quality = label.split(":")
        templates[row, [(ROOTS.index(root) + i) % 12 for i in QUALITIES[quality]]] = 1.0
    return templates / np.linalg.norm(templates, axis=1, keepdims=True)


TEMPLATES = _build_templates()

# Cosine gaps between a chord and its maj/7 sibling are only ~0.1. Without sharpening them by a
# temperature, the transition prior swamps the observations and the whole track collapses to N.
TEMPERATURE = 0.02
SELF_LOOP = 0.5


def match(chroma: np.ndarray) -> np.ndarray:
    """Cosine similarity of each chroma column (12, n) to every label, shape (37, n)."""
    # A zero vector has no direction; the epsilon makes it flat, which matches N.
    chroma = chroma + 1e-9
    chroma = chroma / np.linalg.norm(chroma, axis=0, keepdims=True)
    # Floating error can push values past 1, and librosa.sequence.viterbi rejects that.
    return np.clip(TEMPLATES @ chroma, 0.0, 1.0)


def smooth(sims: np.ndarray) -> np.ndarray:
    """Viterbi-decode (37, n) similarities into one label index per beat."""
    likelihood = np.exp((sims - 1.0) / TEMPERATURE)
    transition = librosa.sequence.transition_loop(len(LABELS), SELF_LOOP)
    return librosa.sequence.viterbi(likelihood, transition)


CANDIDATES = 3


def segment(states: np.ndarray, sims: np.ndarray, cqt: np.ndarray) -> list[dict]:
    """Merge runs of equal state into segments, each with ranked candidate labels and a bass.

    cqt is the (84, n) beat-synchronous matrix from beat_chroma. A segment's bass is the most
    frequent per-beat pick_bass value (ties to the earliest), or None for N or a silent register.
    """
    boundaries = [0, *(np.flatnonzero(np.diff(states)) + 1), len(states)]
    segments = []
    for start, end in pairwise(boundaries):
        chosen = int(states[start])
        mean = sims[:, start:end].mean(axis=1)
        # Rank by mean similarity, but the smoothed label leads: it is what the timeline shows.
        ranked = [i for i in np.argsort(-mean, kind="stable") if i != chosen]
        candidates = [LABELS[i] for i in [chosen, *ranked][:CANDIDATES]]
        # A vote over per-beat values, not a pick on the mean profile: the reported bass must come
        # from the same per-beat values the bass-change cut rule uses, so a loud one-beat note
        # cannot outvote the beats around it.
        votes = Counter(b for b in map(pick_bass, cqt[:, start:end].T) if b is not None)
        bass = votes.most_common(1)[0][0] if votes and LABELS[chosen] != "N" else None
        segments.append(
            {
                "start_beat": int(start),
                "end_beat": int(end),
                "chord": LABELS[chosen],
                "candidates": candidates,
                "bass": bass,
            }
        )
    return segments


# The bass register: C1-B3, the three lowest octaves of the CQT that beat_chroma returns.
BASS_BINS = 36
# Leakage into a neighbouring bin is 0.5-0.6 of a peak but is never a local maximum, so a bin
# needs to be both a local maximum and at least this fraction of the register's strongest.
BASS_SALIENCE = 0.5
# Position names index a quality's QUALITIES intervals in order.
INVERSIONS = ("root", "first", "second", "third")


def pick_bass(profile: np.ndarray) -> str | None:
    """Name the lowest salient note in a beat's CQT profile, or None if the register is silent.

    The profile has one bin per semitone with bin 0 = C1, as beat_chroma returns it. Only the
    first BASS_BINS bins are candidates; the bins above are context for the local-maximum test.
    """
    reference = profile[:BASS_BINS].max()
    if reference == 0:
        return None
    padded = np.pad(profile, 1)
    is_peak = (profile >= padded[:-2]) & (profile >= padded[2:])
    for b in range(BASS_BINS):
        if is_peak[b] and profile[b] >= BASS_SALIENCE * reference:
            return ROOTS[b % 12]
    return None


def inversion(label: str, bass: str | None) -> str | None:
    """Position of the bass note within a chord label: root/first/second/third or non_chord."""
    if label == "N" or bass is None:
        return None
    root, quality = label.split(":")
    offset = (ROOTS.index(bass) - ROOTS.index(root)) % 12
    intervals = QUALITIES[quality]
    return INVERSIONS[intervals.index(offset)] if offset in intervals else "non_chord"
