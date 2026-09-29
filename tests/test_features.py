import numpy as np
import pytest
import soundfile

from chordotomy.chords import LABELS, match
from chordotomy.features import SR, NoBeatsError, beat_chroma, load_audio


def _labels(chroma: np.ndarray) -> list[str]:
    return [LABELS[i] for i in match(chroma).argmax(axis=0)]


def test_load_and_beat_chroma_on_a_repeated_chord(synth, tmp_path) -> None:
    y = synth([("C:maj", 8)])
    path = tmp_path / "clip.wav"
    soundfile.write(path, y, SR)

    loaded = load_audio(path)

    assert abs(len(loaded) - len(y)) <= 1

    beat_times, chroma = beat_chroma(loaded)

    assert len(beat_times) >= 6
    assert abs(np.median(np.diff(beat_times)) - 0.5) <= 0.025
    assert chroma.shape == (12, len(beat_times))
    for column in chroma.T:
        assert set(np.argsort(column)[-3:]) == {0, 4, 7}


def test_silent_beats_mid_track_match_no_chord(synth) -> None:
    beat_times, chroma = beat_chroma(synth([("C:maj", 4), ("N", 4), ("F:maj", 4)]))

    # The window starts before 2.0 s to take in the first silent beat: it carries the previous
    # chord's CQT ringing, which is what the floor exists for.
    silent = (beat_times >= 1.75) & (beat_times < 3.75)

    assert silent.any()
    # Compare labels, not bins: the floor makes silence match N, it does not make bins equal.
    assert _labels(chroma[:, silent]) == ["N"] * silent.sum()


def test_grid_extends_through_edge_silence(synth) -> None:
    y = synth([("C:maj", 4), ("N", 6)])
    beat_times, _ = beat_chroma(y)

    assert beat_times[-1] >= len(y) / SR - 0.75
    assert abs(np.median(np.diff(beat_times)) - 0.5) <= 0.025

    beat_times, chroma = beat_chroma(synth([("N", 4), ("C:maj", 4)]))
    lead = beat_times < 1.75

    assert beat_times[0] < 0.5
    assert lead.any()
    assert _labels(chroma[:, lead]) == ["N"] * lead.sum()


def test_all_silent_audio_has_no_beats() -> None:
    with pytest.raises(NoBeatsError):
        beat_chroma(np.zeros(4 * SR, dtype=np.float32))
