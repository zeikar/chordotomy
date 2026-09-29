"""Synthesized-audio fixtures: chord progressions at a known tempo, with exact ground truth."""

from collections.abc import Callable

import numpy as np
import pytest

from chordotomy.features import SR

BPM = 120
BEAT = 60 / BPM

# Literal music-theory ground truth, deliberately not imported from chordotomy.chords.
ROOT_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
INTERVALS = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10)}

Progression = list[tuple[str, int]]


def _strike(label: str) -> np.ndarray:
    """One beat of a chord struck at the downbeat, or silence for N."""
    n = int(round(BEAT * SR))
    if label == "N":
        return np.zeros(n)
    root, quality = label.split(":")
    t = np.arange(n) / SR
    tone = np.zeros(n)
    for interval in INTERVALS[quality]:
        freq = 440.0 * 2 ** ((48 + ROOT_NAMES.index(root) + interval - 69) / 12)
        for h in range(1, 5):
            tone += np.sin(2 * np.pi * h * freq * t) / h
    envelope = np.minimum(t / 0.005, 1.0) * np.exp(-t / 0.25)
    return tone * envelope


@pytest.fixture
def synth() -> Callable[[Progression], np.ndarray]:
    def make(progression: Progression) -> np.ndarray:
        # Each beat is re-struck and decays: a sustained chord has no onsets for the beat
        # tracker to lock onto.
        beats = [_strike(label) for label, n_beats in progression for _ in range(n_beats)]
        y = np.concatenate(beats)
        peak = np.abs(y).max()
        if peak > 0:
            y = y / peak * 0.5
        return y.astype(np.float32)

    return make


@pytest.fixture
def chord_at() -> Callable[[Progression, float], str]:
    def label_at(progression: Progression, t: float) -> str:
        end = 0.0
        for label, n_beats in progression:
            end += n_beats * BEAT
            if t < end:
                return label
        return "N"

    return label_at
