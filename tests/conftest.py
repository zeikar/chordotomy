"""Synthesized-audio fixtures: chord progressions at a known tempo, with exact ground truth.

A progression entry is (label, n_beats) or (label, n_beats, bass_midi); the bass is an extra tone
under the chord. `synth` also takes a `chord_midi` register for the chord tones. Keep clips at
least 8 beats: `chroma_cqt` warns on shorter ones, which fails under `-W error::UserWarning`.
"""

from collections.abc import Callable

import numpy as np
import pytest

from chordotomy.features import SR

BPM = 120
BEAT = 60 / BPM

# Literal music-theory ground truth, deliberately not imported from chordotomy.chords.
ROOT_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
INTERVALS = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10)}

Progression = list[tuple[str, int] | tuple[str, int, int]]


def _strike(label: str, bass: int | None = None, chord_midi: int = 48) -> np.ndarray:
    """One beat of a chord struck at the downbeat, or silence for N.

    A bass sits at MIDI 36-47 under a chord at 48: the bass register ends at B3, so the bass tone
    is the lowest note by construction and the ground truth is exact. chord_midi=60 voices the
    chord above the register for the no-bass cases.
    """
    n = int(round(BEAT * SR))
    if label == "N":
        return np.zeros(n)
    root, quality = label.split(":")
    t = np.arange(n) / SR
    tone = np.zeros(n)
    notes = [chord_midi + ROOT_NAMES.index(root) + i for i in INTERVALS[quality]]
    if bass is not None:
        notes.append(bass)
    for note in notes:
        freq = 440.0 * 2 ** ((note - 69) / 12)
        for h in range(1, 5):
            tone += np.sin(2 * np.pi * h * freq * t) / h
    envelope = np.minimum(t / 0.005, 1.0) * np.exp(-t / 0.25)
    return tone * envelope


@pytest.fixture
def synth() -> Callable[..., np.ndarray]:
    def make(progression: Progression, chord_midi: int = 48) -> np.ndarray:
        # Each beat is re-struck and decays: a sustained chord has no onsets for the beat
        # tracker to lock onto.
        beats = [
            _strike(label, bass=(rest[0] if rest else None), chord_midi=chord_midi)
            for label, n_beats, *rest in progression
            for _ in range(n_beats)
        ]
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
        for label, n_beats, *_ in progression:
            end += n_beats * BEAT
            if t < end:
                return label
        return "N"

    return label_at
