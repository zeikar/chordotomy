"""Beat tracking and beat-synchronous features: treble and bass chroma, a level, a bass CQT.

The chroma follows the log-frequency front end of Mauch & Dixon, "Approximate Note Transcription
for the Improved Identification of Difficult Chords" (ISMIR 2010): a 1/3-semitone spectrum,
whitened against its running octave background, folded to pitch classes through a treble and a
bass pitch window. Implemented from the paper, not from their GPL-licensed plugin.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import librosa
import numpy as np
from scipy.ndimage import convolve1d

from .chords import BASS_BINS

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


def _ramp(midi: np.ndarray, start: float, end: float) -> np.ndarray:
    """0 up to start, 1 from end, a raised cosine in between."""
    x = np.clip((midi - start) / (end - start), 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(np.pi * x)


_MIDI = librosa.note_to_midi("C1") + np.arange(CHORD_BINS) * 12 / CHORD_BINS_PER_OCTAVE
TREBLE_WINDOW = _ramp(_MIDI, *TREBLE_IN) * (1.0 - _ramp(_MIDI, *TREBLE_OUT))
BASS_WINDOW = 1.0 - _ramp(_MIDI, *BASS_OUT)
FOLD = librosa.filters.cq_to_chroma(
    CHORD_BINS,
    bins_per_octave=CHORD_BINS_PER_OCTAVE,
    n_chroma=12,
    fmin=librosa.note_to_hz("C1"),
)


class Features(NamedTuple):
    """Beat-synchronous features of a signal with n beats.

    times: (n,) beat starts in seconds. Beat i spans [times[i], times[i + 1]); the last beat
        runs to the end of the audio.
    treble, bass: (12, n) whitened chroma through the treble and bass pitch windows, C first,
        the median per beat.
    cqt: (84, n) CQT magnitude, bin k is k semitones above C1, the median per beat; beats with a
        silent bass register are all-zero columns.
    level: (n,) the median RMS per beat in dB relative to the 95th-percentile beat.
    period: the grid's beat period in seconds.
    """

    times: np.ndarray
    treble: np.ndarray
    bass: np.ndarray
    cqt: np.ndarray
    level: np.ndarray
    period: float


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


def beat_features(y: np.ndarray) -> Features:
    """Beat-synchronous chord, bass and level features of a mono signal at SR."""
    # The default trim dropped the last two real beats of a synthesized clip.
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=SR, hop_length=HOP, trim=False)
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
    # The tracker places no beats in edge silence. Without extending the grid, the last beat
    # would swallow seconds of silent tail, and leading silence would have no beats to label
    # N. The half-period guard avoids a sliver interval at the end.
    if len(beat_frames) >= 2:
        period = int(round(np.median(np.diff(beat_frames))))
    else:
        # A single beat has no spacing to measure, so fall back to the tracker's tempo (a
        # positive 1-element array whenever any beat was found).
        period = int(round(60 / float(np.ravel(tempo)[0]) * SR / HOP))
    head = np.arange(beat_frames[0] % period, beat_frames[0], period)
    tail = np.arange(beat_frames[-1] + period, n_frames - period // 2, period)
    beat_frames = np.concatenate([head, beat_frames, tail])

    boundaries = list(beat_frames) + [n_frames]
    whitened = _whiten(chord_cqt)
    # No max-normalisation: the correlation that scores these is scale-free.
    treble = librosa.util.sync(
        (FOLD * TREBLE_WINDOW) @ whitened, boundaries, aggregate=np.median, pad=False
    )
    bass = librosa.util.sync(
        (FOLD * BASS_WINDOW) @ whitened, boundaries, aggregate=np.median, pad=False
    )
    rms = librosa.util.sync(
        librosa.feature.rms(y=harmonic, hop_length=HOP), boundaries, aggregate=np.median, pad=False
    )[0]
    # Relative to a high percentile rather than the maximum, so one loud hit cannot push a quiet
    # intro under the N gate. Digital silence lands at librosa's -80 dB floor.
    level = librosa.amplitude_to_db(rms, ref=np.percentile(rms, 95))
    cqt = librosa.util.sync(cqt, boundaries, aggregate=np.median, pad=False)
    # The reference is the file's loudest bin anywhere, not the register's own maximum, so a file
    # with no bass never sets its own reference from leakage: what survives in its register is
    # leakage slopes under real notes above, which the peak test rejects. Zeroed rather than
    # lifted by an additive floor, because a flat column would make C1 the lowest peak.
    cqt[:, cqt[:BASS_BINS].max(axis=0) < SILENCE_FLOOR * cqt.max()] = 0.0
    return Features(
        times=librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP),
        treble=treble,
        bass=bass,
        cqt=cqt,
        level=level,
        period=period * HOP / SR,
    )
