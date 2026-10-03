"""Synthesized-audio fixtures: chord progressions at a known tempo, with exact ground truth.

A progression entry is (label, n_beats), (label, n_beats, bass_midi) or (label, n_beats,
bass_midi, melody_midi); the bass is an extra tone under the chord, the melody an extra tone
struck with it at a chord tone's level. `synth` also takes a `chord_midi` register for the chord
tones, a `bpm` and an envelope `decay`; `chord_at` assumes the default tempo. Keep clips at least
8 beats: `chroma_cqt` warns on shorter ones, which fails under `-W error::UserWarning`.
"""

from collections.abc import Callable

import librosa
import numpy as np
import pytest
from scipy.signal import fftconvolve

import chordotomy.beats
import chordotomy.model
from chordotomy.features import HOP, SR


def _no_beat_this(y: np.ndarray) -> np.ndarray:
    pytest.fail("the model beat tracker ran in the default suite")


@pytest.fixture(autouse=True)
def dsp_engine(monkeypatch):
    """The default suite runs the DSP whether or not the model extra is installed.

    `--engine auto` then resolves to the DSP and `--engine model` is unavailable;
    test_model_engine.py opts back in. Beat This! never runs: a test that runs the model engine
    stubs its activation, test_beats_engine.py and the tests of test_model_engine.py that take
    `beat_this_weights` restore the real one, and test_beats.py calls it directly.
    """
    monkeypatch.setattr(chordotomy.model, "available", lambda: False)
    monkeypatch.setattr(chordotomy.beats, "activation", _no_beat_this)


def librosa_activation(y: np.ndarray) -> np.ndarray:
    """librosa's own onset envelope, the one beat_track(y=y) tracks: a stubbed model engine given
    it as Beat This!'s activation keeps the DSP's grid."""
    return librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP, aggregate=np.median)


BPM = 120
BEAT = 60 / BPM

# Literal music-theory ground truth, deliberately not imported from chordotomy.chords.
ROOT_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
INTERVALS = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "min6": (0, 3, 7, 9),
    "hdim7": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "sus4": (0, 5, 7),
    "aug": (0, 4, 8),
    "dim": (0, 3, 6),
    "sus2": (0, 2, 7),
    "sus4(b7)": (0, 5, 7, 10),
}

Progression = list[tuple[str, int] | tuple[str, int, int] | tuple[str, int, int, int]]


def _strike(
    label: str,
    bass: int | None = None,
    chord_midi: int = 48,
    melody: int | None = None,
    beat: float = BEAT,
    decay: float = 0.25,
) -> np.ndarray:
    """One beat of a chord struck at the downbeat, or silence for N; beat is its length in seconds.

    A bass sits at MIDI 36-47 under a chord at 48: the bass register ends at B3, so the bass tone
    is the lowest note by construction and the ground truth is exact. chord_midi=60 voices the
    chord above the register for the no-bass cases. A melody note is one more tone, as loud as
    each chord tone. decay is the envelope's time constant in seconds: a long beat with a long
    decay is a chord struck once and held.
    """
    n = int(round(beat * SR))
    if label == "N":
        return np.zeros(n)
    root, quality = label.split(":")
    t = np.arange(n) / SR
    tone = np.zeros(n)
    notes = [chord_midi + ROOT_NAMES.index(root) + i for i in INTERVALS[quality]]
    if bass is not None:
        notes.append(bass)
    if melody is not None:
        notes.append(melody)
    for note in notes:
        freq = 440.0 * 2 ** ((note - 69) / 12)
        for h in range(1, 5):
            tone += np.sin(2 * np.pi * h * freq * t) / h
    envelope = np.minimum(t / 0.005, 1.0) * np.exp(-t / decay)
    return tone * envelope


@pytest.fixture
def synth() -> Callable[..., np.ndarray]:
    def make(
        progression: Progression, chord_midi: int = 48, bpm: float = BPM, decay: float = 0.25
    ) -> np.ndarray:
        # Each beat is re-struck and decays: a sustained chord has no onsets for the beat
        # tracker to lock onto.
        beats = []
        for label, n_beats, *rest in progression:
            bass, melody = (*rest, None, None)[:2]  # both optional, in that order
            beats += [
                _strike(label, bass, chord_midi, melody, 60 / bpm, decay) for _ in range(n_beats)
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


def _kick() -> np.ndarray:
    """A kick drum: a sine swept from 150 down to 50 Hz over 80 ms."""
    t = np.arange(int(0.08 * SR)) / SR
    # Exponential sweep 150 -> 50 Hz: the phase is the integral of the frequency.
    rate = np.log(50 / 150) / 0.08
    return np.sin(2 * np.pi * 150 * (np.exp(rate * t) - 1) / rate) * np.exp(-t / 0.05)


def _hat(rng: np.random.Generator) -> np.ndarray:
    """A hi-hat: a 30 ms burst of white noise."""
    return rng.standard_normal(int(0.03 * SR)) * 0.3


@pytest.fixture
def half_locked() -> Callable[[list[tuple[str, int]], float], np.ndarray]:
    """A progression rendered like `synth`, with a kick and a hat struck on every odd beat.

    The drums on the beats between two-beat chord changes make librosa lock at half tempo, on the
    drummed beats, so the changes fall between its beats (measured for this plan at 160, 180 and
    200 BPM). Seeded, so the clip is identical on every run.
    """
    rng = np.random.default_rng(0)

    def make(progression: list[tuple[str, int]], bpm: float) -> np.ndarray:
        beats = [
            _strike(label, beat=60 / bpm) for label, n_beats in progression for _ in range(n_beats)
        ]
        kick = _kick()
        for beat in beats[1::2]:
            beat[: len(kick)] += kick
            hat = _hat(rng)
            beat[: len(hat)] += hat
        y = np.concatenate(beats)
        return (y / np.abs(y).max() * 0.5).astype(np.float32)

    return make


@pytest.fixture
def drums() -> Callable[[int], np.ndarray]:
    """n_beats of a kick on each beat and a hat on each eighth at the fixture tempo, no tones.

    Normalised like `synth`. Seeded, so the clip is identical on every run.
    """
    rng = np.random.default_rng(0)

    def make(n_beats: int) -> np.ndarray:
        n = int(round(BEAT * SR))
        kick = _kick()
        beats = []
        for _ in range(n_beats):
            beat = np.zeros(n)
            beat[: len(kick)] += kick
            for offset in (0, n // 2):
                hat = _hat(rng)
                beat[offset : offset + len(hat)] += hat
            beats.append(beat)
        y = np.concatenate(beats)
        return (y / np.abs(y).max() * 0.5).astype(np.float32)

    return make


# Hat positions in beats of a 4/4 bar: eighths; 3-3-2 sixteenths, a 4:3 period over the pulse;
# quarter-note triplets, a 3:2 period.
STRAIGHT = tuple(i / 2 for i in range(8))
TRESILLO = (0, 0.75, 1.5, 2, 2.75, 3.5)
TRIPLETS = tuple(i * 2 / 3 for i in range(6))


@pytest.fixture
def syncopated() -> Callable[[int, int, float], np.ndarray]:
    """Drums alone at one tempo: a kick on 1 and 3 of every bar, hats on the eighths for
    n_straight bars, then for n_syncopated bars in 3-3-2 sixteenths and in quarter-note triplets,
    two bars each. As long as `synth` at the same tempo and n_straight + n_syncopated bars.

    The pulse never changes, but the syncopated hats make librosa's local tempo flicker between
    the pulse's levels and the 4:3 and 3:2 readings, as a syncopated pop track does. Normalised
    like `synth`. Seeded, so the clip is identical on every run.
    """
    rng = np.random.default_rng(0)

    def make(n_straight: int, n_syncopated: int, bpm: float) -> np.ndarray:
        beat = int(round(60 / bpm * SR))  # samples, rounded as `synth` rounds them
        syncopations = [(TRESILLO, TRIPLETS)[i // 2 % 2] for i in range(n_syncopated)]
        bars = [STRAIGHT] * n_straight + syncopations
        y = np.zeros(len(bars) * 4 * beat + SR)
        kick = _kick()
        for i, hats in enumerate(bars):
            for at in (0, 2):
                start = (4 * i + at) * beat
                y[start : start + len(kick)] += kick
            for at in hats:
                hat = _hat(rng)
                start = int(round((4 * i + at) * beat))
                y[start : start + len(hat)] += hat
        y = y[: len(bars) * 4 * beat]
        return (y / np.abs(y).max() * 0.5).astype(np.float32)

    return make


DETUNE = 2 ** (0.4 / 12)  # +40 cents: real recordings are never at A440 to the cent


def _partials(t: np.ndarray, note: int, n_harmonics: int, rng, decay: float | None = None):
    freq = 440.0 * 2 ** ((note - 69) / 12) * DETUNE
    tone = np.zeros_like(t)
    for h in range(1, n_harmonics + 1):
        tone += np.sin(2 * np.pi * h * freq * t + rng.uniform(0, 2 * np.pi)) * h**-0.5
    return tone if decay is None else tone * np.exp(-t / decay)


@pytest.fixture
def mix() -> Callable[[Progression], np.ndarray]:
    """A progression rendered like a produced mix, not like a clean test tone.

    The `synth` clips can never produce a flat chroma; a real mix can, and then every chord
    scores like the N template. Each ingredient is one way a mix flattens chroma:
    - 12 harmonics with random phases, the root an octave below, sustained: harmonics of every
      note leak into the other pitch classes, and a held chord has no onsets for HPSS to drop.
    - two melody tones per beat on non-chord tones (root + 2, root + 5 an octave up): pitch
      classes that contradict the chord.
    - hi-hat bursts and a kick sweep: percussive energy across the spectrum.
    - a white-noise wash: broadband energy HPSS keeps as "harmonic", filling all 12 bins.
    - +40 cents on every pitch: energy straddles two semitone bins instead of landing in one.
    - reverb, added 1:1: smears each chord into the next and adds diffuse energy.
    Seeded, so the clip is identical on every run.
    """
    rng = np.random.default_rng(0)

    def make(progression: Progression) -> np.ndarray:
        n = int(round(BEAT * SR))
        t = np.arange(n) / SR
        envelope = np.minimum(t / 0.005, 1.0) * (0.4 + 0.6 * np.exp(-t / 0.4))
        eighth = n // 2
        t8 = t[:eighth]
        kick = _kick()
        beats = []
        for label, n_beats, *_ in progression:
            root_pc = ROOT_NAMES.index(label.split(":")[0])
            quality = label.split(":")[1]
            for _ in range(n_beats):
                notes = [48 + root_pc + i for i in INTERVALS[quality]] + [36 + root_pc]
                beat = sum(_partials(t, note, 12, rng) for note in notes) * envelope
                for offset, step in ((0, 2), (eighth, 5)):
                    melody = 60 + root_pc + step
                    beat[offset : offset + eighth] += 0.8 * _partials(t8, melody, 8, rng, 0.15)
                    hat = _hat(rng)
                    beat[offset : offset + len(hat)] += hat
                beat[: len(kick)] += kick
                beat += rng.standard_normal(n) * 0.2 * np.abs(beat).max()
                beats.append(beat)
        y = np.concatenate(beats)
        m = int(0.8 * SR)
        impulse = rng.standard_normal(m) * np.exp(-np.arange(m) / SR / 0.25)
        y = y + fftconvolve(y, impulse)[: len(y)]
        return (y / np.abs(y).max() * 0.5).astype(np.float32)

    return make
