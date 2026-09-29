"""Chord vocabulary and template matching."""

from __future__ import annotations

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
