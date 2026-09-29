"""Beat tracking and beat-synchronous chroma."""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

SR = 22050
HOP = 512
SILENCE_FLOOR = 0.01


class NoBeatsError(Exception):
    """The beat tracker found no beats, as in silence or a clip shorter than one beat."""


def load_audio(path: Path) -> np.ndarray:
    """Decode an audio file to a mono signal at SR."""
    y, _ = librosa.load(path, sr=SR, mono=True)
    return y


def beat_chroma(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Beat times in seconds (n,) and median chroma per beat (12, n).

    Beat i spans [beat i, beat i + 1); the last beat runs to the end of the audio.
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

    beat_sync = librosa.util.sync(
        chroma, list(beat_frames) + [n_frames], aggregate=np.median, pad=False
    )
    # Beats whose energy sits far below 1 % of the loudest bin end up close to flat, so digital
    # silence and faint noise rank N first. It is a bias: a quiet chord well above the floor
    # keeps its shape.
    beat_sync = beat_sync + SILENCE_FLOOR * beat_sync.max()
    beat_times = librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP)
    return beat_times, beat_sync
