"""Beat tracking and beat-synchronous features: treble and bass chroma, a level, a bass CQT.

The chroma follows the log-frequency front end of Mauch & Dixon, "Approximate Note Transcription
for the Improved Identification of Difficult Chords" (ISMIR 2010): a 1/3-semitone spectrum,
whitened against its running octave background, folded to pitch classes through a treble and a
bass pitch window. Implemented from the paper, not from their GPL-licensed plugin.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import NamedTuple

import librosa
import numpy as np
from scipy.ndimage import convolve1d

from .chords import BASS_BINS, match, pick_bass, smooth

SR = 22050
HOP = 512
SILENCE_FLOOR = 0.01
# Seven octaves from C1 at one bin per semitone, the chord CQT's span. The lowest BASS_BINS are
# the bass register; the rest give the peak test its context above the register and the silence
# floor the file's level.
CQT_BINS = 84
# The chord CQT: the same seven octaves at three bins per semitone, the paper's resolution. Each
# pitch class folds the bin on its pitch and one either side, which absorbs what the tuning
# estimate leaves.
CHORD_BINS = 252
CHORD_BINS_PER_OCTAVE = 36
# The whitening background: one octave, bins k-18 to k+18, so every pitch class sits in each
# bin's background and a chord's own tones cannot dominate it.
WHITEN_BINS = 37
# Raised-cosine pitch windows, (start, end) of each ramp in MIDI notes.
# Treble fades in from E2 to C3: above the bass line and the kick, which would flatten it.
TREBLE_IN = (40, 48)
# Treble fades out from C6 to C7: below the hi-hat and sibilance octaves (research pitfall 6).
TREBLE_OUT = (84, 96)
# Bass is flat through B2 and fades out by B3, the top of the pick_bass register.
BASS_OUT = (47, 59)
# The octave check doubles the grid when at least this share of the chord changes decoded on the
# doubled grid fall on its inserted beats. The synthesized half-lock scores 1.00 on 35 changes;
# tracks whose grid is right (period ratio within 10 % of 1) score up to 0.34 on Tiny AAM and 0.71
# on GuitarSet takes with 24 or more changes, so a step either way flags none (0.70 would flag two).
# One-beat chords under a half lock score 0.50, so they are not covered.
OCTAVE_INSERTED_SHARE = 0.80
# With fewer changes the share is noise: an 84 BPM GuitarSet take whose grid is right scores 0.84
# on 19, which 16 would flag. A step either way stays clear of it and under the half-lock's 35.
OCTAVE_MIN_CHANGES = 24


def _ramp(midi: np.ndarray, start: float, end: float) -> np.ndarray:
    """0 up to start, 1 from end, a raised cosine in between."""
    x = np.clip((midi - start) / (end - start), 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(np.pi * x)


@functools.cache
def _windows() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(treble window, bass window, fold to 12 pitch classes) over the chord CQT's bins.

    Built on first use: librosa's filter code initialises numba, which importing the package for
    a command like --version should not pay for (or fail on, in a read-only cache).
    """
    midi = librosa.note_to_midi("C1") + np.arange(CHORD_BINS) * 12 / CHORD_BINS_PER_OCTAVE
    fold = librosa.filters.cq_to_chroma(
        CHORD_BINS,
        bins_per_octave=CHORD_BINS_PER_OCTAVE,
        n_chroma=12,
        fmin=librosa.note_to_hz("C1"),
    )
    treble = _ramp(midi, *TREBLE_IN) * (1.0 - _ramp(midi, *TREBLE_OUT))
    return treble, 1.0 - _ramp(midi, *BASS_OUT), fold


class Features(NamedTuple):
    """Beat-synchronous features of a signal with n beats.

    times: (n,) beat starts in seconds. Beat i spans [times[i], times[i + 1]); the last beat
        runs to the end of the audio.
    frames: (n,) the same beat starts as frame indices at HOP, which times is computed from.
    treble, bass: (12, n) whitened chroma through the treble and bass pitch windows, C first,
        the median per beat. bass is all zero on beats where pick_bass finds no note: the
        correlation that scores it is scale-free, so leakage there would count as a bass.
    cqt: (84, n) CQT magnitude, bin k is k semitones above C1, the median per beat; beats with a
        silent bass register are all-zero columns.
    level: (n,) the median RMS per beat in dB relative to the 95th-percentile beat.
    onset: (n,) the beat's peak onset strength in units of the track's median frame; where that
        median is 0, as on a mostly silent clip, inf on a beat with any flux and 0 on one without.
    flatness: (n,) the median spectral flatness per beat of the harmonic signal: near 0 for tones,
        1 for digital silence.
    harmonic: (n,) the share of the beat's energy in the harmonic signal, the lower of its share
        summed over the beat and its median per frame; 0 on a beat with none.
    """

    times: np.ndarray
    frames: np.ndarray
    treble: np.ndarray
    bass: np.ndarray
    cqt: np.ndarray
    level: np.ndarray
    onset: np.ndarray
    flatness: np.ndarray
    harmonic: np.ndarray


class NoBeatsError(Exception):
    """The beat tracker found no beats, as in silence or a clip shorter than one beat."""


def load_audio(path: Path) -> np.ndarray:
    """Decode an audio file to a mono signal at SR."""
    y, _ = librosa.load(path, sr=SR, mono=True)
    return y


def _whiten(cqt: np.ndarray) -> np.ndarray:
    """The paper's "std" preprocessing with rho = 1, per frame along the frequency axis.

    Each bin becomes its excess over the Hamming-weighted running mean of its octave, in running
    standard deviations; a bin at or below the mean is 0.
    """
    window = np.hamming(WHITEN_BINS)
    window /= window.sum()
    # The octave around an edge bin is cut short. Repeating the edge value fills it with the
    # bin's own level; zeros would read as a quiet background and whiten the edge up.
    mean = convolve1d(cqt, window, axis=0, mode="nearest")
    # Rounding can take a flat stretch's variance a hair below 0.
    std = np.sqrt(np.maximum(convolve1d(cqt**2, window, axis=0, mode="nearest") - mean**2, 0.0))
    excess = cqt - mean
    # Digital silence has sigma 0: nothing stands out from a background of nothing, so it is 0
    # rather than a division by zero.
    return np.divide(excess, std, out=np.zeros_like(cqt), where=(excess > 0) & (std > 0))


def _extend(beat_frames: np.ndarray, n_frames: int, tempo: float) -> np.ndarray:
    """The grid carried through edge silence, where the tracker places no beats.

    Without it, the last beat would swallow seconds of silent tail, and leading silence would
    have no beats to label N. The head steps at the first gap and the tail at the last: the
    grid's local period at each edge, which the tracker bends to follow a drifting tempo. On a
    constant grid both are the median gap within a frame. A single beat
    has no gap, so it steps at the global tempo's period. The half-period guard avoids a sliver
    interval at the end.
    """
    if len(beat_frames) >= 2:
        head_gap, tail_gap = np.diff(beat_frames)[[0, -1]]
    else:
        head_gap = tail_gap = int(round(60 / tempo * SR / HOP))
    head = np.arange(beat_frames[0] % head_gap, beat_frames[0], head_gap)
    tail = np.arange(beat_frames[-1] + tail_gap, n_frames - tail_gap // 2, tail_gap)
    return np.concatenate([head, beat_frames, tail])


def _double(beat_frames: np.ndarray, n_frames: int, tempo: float) -> tuple[np.ndarray, int]:
    """The tracker's grid at twice its tempo, and the parity of the tracker's beats in it.

    A beat is inserted at every midpoint, and the grid is extended at half the edge gaps (twice
    the tempo, for a single beat). The extension alternates too, so every beat at the other
    parity is an inserted one.
    """
    doubled = np.sort(np.concatenate([beat_frames, (beat_frames[:-1] + beat_frames[1:]) // 2]))
    frames = _extend(doubled, n_frames, 2 * tempo)
    return frames, int(np.searchsorted(frames, beat_frames[0])) % 2


def _sync(
    boundaries: list[int], whitened: np.ndarray, cqt: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Treble and bass chroma and the bass CQT per beat between boundaries, as in Features."""
    treble_window, bass_window, fold = _windows()
    # No max-normalisation: the correlation that scores these is scale-free.
    treble = librosa.util.sync(
        (fold * treble_window) @ whitened, boundaries, aggregate=np.median, pad=False
    )
    bass = librosa.util.sync(
        (fold * bass_window) @ whitened, boundaries, aggregate=np.median, pad=False
    )
    cqt = librosa.util.sync(cqt, boundaries, aggregate=np.median, pad=False)
    # The reference is the file's loudest bin anywhere, not the register's own maximum, so a file
    # with no bass never sets its own reference from leakage: what survives in its register is
    # leakage slopes under real notes above, which the peak test rejects. Zeroed rather than
    # lifted by an additive floor, because a flat column would make C1 the lowest peak.
    cqt[:, cqt[:BASS_BINS].max(axis=0) < SILENCE_FLOOR * cqt.max()] = 0.0
    # The bass correlation is scale-free, so on a beat with no bass note the leakage under a chord
    # above the register would vote at full strength (it pulls a bass-less C:maj toward C:maj7).
    bass[:, np.array([pick_bass(column) is None for column in cqt.T])] = 0.0
    return treble, bass, cqt


def _changes_between(states: np.ndarray, parity: int) -> bool:
    """Whether the chord changes decoded on a doubled grid fall between the tracker's beats.

    states is one label per beat of the doubled grid, and the tracker's beats sit at parity. True
    when at least OCTAVE_MIN_CHANGES changes were decoded and at least OCTAVE_INSERTED_SHARE of
    them start on inserted beats.
    """
    starts = np.flatnonzero(np.diff(states)) + 1
    return (
        len(starts) >= OCTAVE_MIN_CHANGES and np.mean(starts % 2 != parity) >= OCTAVE_INSERTED_SHARE
    )


def _too_slow(treble: np.ndarray, bass: np.ndarray, durations: np.ndarray, parity: int) -> bool:
    """Whether the tracker has locked at half tempo with the chord changes between its beats.

    treble and bass are synced on the doubled grid from _double, durations are its (n - 1,) gaps
    in seconds, and parity is its tracker beats' parity. The DSP's own decode places the chord
    changes on that grid, and when they fall on the inserted beats (_changes_between), the
    tracker's grid would merge the chords on either side of each change. A half-tempo grid in
    phase with the changes is left: each chord is one beat on it, and the decoder keeps a one-beat
    change to a distinct chord, so it costs granularity, not labels.

    Two limits. Under a half lock, one-beat chords at the true tempo change on inserted and
    tracker beats alike (a share of 0.50), so that lock is not caught. And a grid at double tempo
    is never halved: it loses no chord, since CHORD_SECONDS is in seconds, while halving a grid
    could merge real two-beat chords.
    """
    # No beat is gated: the check asks where the chords change, the gate's evidence belongs to the
    # grid that is kept, and digital silence's flat chroma decodes as N without the gate.
    states = smooth(match(treble, bass), np.zeros(treble.shape[1], dtype=bool), durations)
    return _changes_between(states, parity)


def beat_features(y: np.ndarray) -> Features:
    """Beat-synchronous chord, bass and level features of a mono signal at SR."""
    # One tempo per file: a local tempo curve took syncopation over an unchanged pulse for a tempo
    # change (docs/ARCHITECTURE.md, "Tempo changes are not followed"). The default trim dropped the
    # last two real beats of a synthesized clip.
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=SR, hop_length=HOP, trim=False)
    # A 1-element array, positive whenever a beat was found: a single beat extends at its period.
    tempo = float(np.ravel(tempo)[0])
    # Checked before the features: otherwise sync returns empty matrices and the floor's max()
    # raises a bare numpy error, after estimate_tuning has warned about tuning on an empty signal.
    if len(beat_frames) == 0:
        raise NoBeatsError("no beats detected")

    harmonic = librosa.effects.harmonic(y)
    # One estimate for both CQTs, so the bass bins line up with the chord chroma's: on a recording
    # detuned by half a semitone, the chroma's root and the bass note fall on the same side.
    # tuning is in fractions of a bin, 36 per octave for the chord CQT and 12 for the bass CQT,
    # hence the division.
    tuning = librosa.estimate_tuning(y=harmonic, sr=SR, bins_per_octave=CHORD_BINS_PER_OCTAVE)
    chord_cqt = np.abs(
        librosa.cqt(
            harmonic,
            sr=SR,
            hop_length=HOP,
            fmin=librosa.note_to_hz("C1"),
            n_bins=CHORD_BINS,
            bins_per_octave=CHORD_BINS_PER_OCTAVE,
            tuning=tuning,
        )
    )
    # 12 bins per octave, not the chord CQT's 36: the window at C1 is 0.53 s instead of 1.59 s, so
    # beats stay separable. The cost is leakage into neighbour semitone bins, which pick_bass
    # tells apart from a note.
    cqt = np.abs(
        librosa.cqt(
            harmonic,
            sr=SR,
            hop_length=HOP,
            fmin=librosa.note_to_hz("C1"),
            n_bins=CQT_BINS,
            bins_per_octave=12,
            tuning=tuning / 3,
        )
    )
    n_frames = chord_cqt.shape[1]
    whitened = _whiten(chord_cqt)
    # The octave check: the doubled grid is read first, and kept with its features when the
    # tracker's beats fall between the chord changes.
    doubled, parity = _double(beat_frames, n_frames, tempo)
    boundaries = list(doubled) + [n_frames]
    treble, bass, beat_cqt = _sync(boundaries, whitened, cqt)
    durations = np.diff(librosa.frames_to_time(doubled, sr=SR, hop_length=HOP))
    if _too_slow(treble, bass, durations, parity):
        beat_frames = doubled
    else:
        beat_frames = _extend(beat_frames, n_frames, tempo)
        boundaries = list(beat_frames) + [n_frames]
        treble, bass, beat_cqt = _sync(boundaries, whitened, cqt)

    harmonic_rms = librosa.feature.rms(y=harmonic, hop_length=HOP)
    rms = librosa.util.sync(harmonic_rms, boundaries, aggregate=np.median, pad=False)[0]
    # Relative to a high percentile rather than the maximum, so one loud hit cannot push a quiet
    # intro under the N gate. Digital silence lands at librosa's -80 dB floor.
    level = librosa.amplitude_to_db(rms, ref=np.percentile(rms, 95))
    # The mean over bands, not the tracker's median: at -50 dB only a few mel bands rise, so their
    # median is 0 where the mean still shows the strike.
    flux = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    peak = librosa.util.sync(flux[None], boundaries, aggregate=np.max, pad=False)[0]
    flux_median = np.median(flux)
    struck = peak / flux_median if flux_median > 0 else np.where(peak > 0, np.inf, 0.0)
    flatness = librosa.util.sync(
        librosa.feature.spectral_flatness(y=harmonic, hop_length=HOP),
        boundaries,
        aggregate=np.median,
        pad=False,
    )[0]
    mix_rms = librosa.feature.rms(y=y, hop_length=HOP)
    energy = librosa.util.sync(
        np.vstack([harmonic_rms, mix_rms]) ** 2, boundaries, aggregate=np.sum, pad=False
    )
    summed = np.divide(energy[0], energy[1], out=np.zeros(len(beat_frames)), where=energy[1] > 0)
    per_frame = np.divide(
        harmonic_rms**2, mix_rms**2, out=np.zeros_like(mix_rms), where=mix_rms > 0
    )
    median = librosa.util.sync(per_frame, boundaries, aggregate=np.median, pad=False)[0]
    # Harmonic only where both agree. The sum is set by the beat's loudest frames, so a drum hit
    # outweighs the cymbal sustain HPSS keeps as harmonic (the median Tiny AAM drum stem decodes
    # 81 % N with the summed share, 53 % with the median one). The median is set by most of its
    # frames, so a beat that is mostly silence reads 0 though its first frames carry the last
    # chord or a cut's click, or its last frame the next strike.
    share = np.minimum(summed, median)
    return Features(
        times=librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP),
        frames=beat_frames,
        treble=treble,
        bass=bass,
        cqt=beat_cqt,
        level=level,
        onset=struck,
        flatness=flatness,
        harmonic=share,
    )
