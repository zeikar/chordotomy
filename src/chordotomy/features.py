"""Beat tracking, beat-synchronous chroma, and a beat-synchronous CQT for the bass note."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

from .chords import BASS_BINS

SR = 22050
HOP = 512
SILENCE_FLOOR = 0.01
# Seven octaves from C1 at one bin per semitone, the chroma's span. The lowest BASS_BINS are the
# bass register; the rest give the peak test its context above the register and the silence
# floor the file's level.
CQT_BINS = 84


class NoBeatsError(Exception):
    """The beat tracker found no beats, as in silence or a clip shorter than one beat."""


def load_audio(path: Path) -> np.ndarray:
    """Decode an audio file to a mono signal at SR."""
    y, _ = librosa.load(path, sr=SR, mono=True)
    return y


def beat_chroma(y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Beat times in seconds (n,), median chroma per beat (12, n) and median CQT per beat (84, n).

    Beat i spans [beat i, beat i + 1); the last beat runs to the end of the audio. CQT bin k is
    the magnitude k semitones above C1; beats with a silent bass register are all-zero columns.
    """
    # The default trim dropped the last two real beats of a synthesized clip.
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=SR, hop_length=HOP, trim=False)
    # Checked before the chroma: otherwise sync returns a (12, 0) matrix and the floor's max()
    # raises a bare numpy error, after chroma_cqt has warned about tuning on an empty signal.
    if len(beat_frames) == 0:
        raise NoBeatsError("no beats detected")

    harmonic = librosa.effects.harmonic(y)
    # The default per-frame max-normalisation scales near-silent CQT ringing up to full scale,
    # which gives a silent beat a random chord. Raw magnitudes keep silence small.
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=SR, hop_length=HOP, norm=None)
    # This is the estimate chroma_cqt makes for itself on the locked librosa 1.0.0, so the bass
    # bins line up with the chord chroma's tuning: on a recording detuned by half a semitone, the
    # chroma's root and the bass note fall on the same side. tuning is in fractions of a bin,
    # 36 per octave there and 12 here, hence the division.
    tuning = librosa.estimate_tuning(y=harmonic, sr=SR, bins_per_octave=36)
    # 12 bins per octave, not the chroma's 36: the window at C1 is 0.53 s instead of 1.59 s, so
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
    n_frames = chroma.shape[1]
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
    beat_sync = librosa.util.sync(chroma, boundaries, aggregate=np.median, pad=False)
    # Beats whose energy sits far below 1 % of the loudest bin end up close to flat, so digital
    # silence and faint noise rank N first. It is a bias: a quiet chord well above the floor
    # keeps its shape.
    beat_sync = beat_sync + SILENCE_FLOOR * beat_sync.max()
    cqt = librosa.util.sync(cqt, boundaries, aggregate=np.median, pad=False)
    # The reference is the file's loudest bin anywhere, not the register's own maximum, so a file
    # with no bass never sets its own reference from leakage: what survives in its register is
    # leakage slopes under real notes above, which the peak test rejects. Zeroed rather than
    # lifted by the additive floor above, because a flat column would make C1 the lowest peak.
    cqt[:, cqt[:BASS_BINS].max(axis=0) < SILENCE_FLOOR * cqt.max()] = 0.0
    beat_times = librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP)
    return beat_times, beat_sync, cqt
