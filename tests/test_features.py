import numpy as np
import pytest
import soundfile

from chordotomy.chords import LABELS, match, pick_bass
from chordotomy.features import SR, NoBeatsError, beat_chroma, load_audio


def _labels(chroma: np.ndarray) -> list[str]:
    return [LABELS[i] for i in match(chroma).argmax(axis=0)]


def test_load_and_beat_chroma_on_a_repeated_chord(synth, tmp_path) -> None:
    y = synth([("C:maj", 8)])
    path = tmp_path / "clip.wav"
    soundfile.write(path, y, SR)

    loaded = load_audio(path)

    assert abs(len(loaded) - len(y)) <= 1

    beat_times, chroma, cqt = beat_chroma(loaded)

    assert len(beat_times) >= 6
    assert abs(np.median(np.diff(beat_times)) - 0.5) <= 0.025
    assert chroma.shape == (12, len(beat_times))
    assert cqt.shape == (84, len(beat_times))
    for column in chroma.T:
        assert set(np.argsort(column)[-3:]) == {0, 4, 7}


def test_silent_beats_mid_track_match_no_chord(synth) -> None:
    beat_times, chroma, _ = beat_chroma(synth([("C:maj", 4), ("N", 4), ("F:maj", 4)]))

    # The window starts before 2.0 s to take in the first silent beat: it carries the previous
    # chord's CQT ringing, which is what the floor exists for.
    silent = (beat_times >= 1.75) & (beat_times < 3.75)

    assert silent.any()
    # Compare labels, not bins: the floor makes silence match N, it does not make bins equal.
    assert _labels(chroma[:, silent]) == ["N"] * silent.sum()


def test_grid_extends_through_edge_silence(synth) -> None:
    y = synth([("C:maj", 4), ("N", 6)])
    beat_times, _, _ = beat_chroma(y)

    assert beat_times[-1] >= len(y) / SR - 0.75
    assert abs(np.median(np.diff(beat_times)) - 0.5) <= 0.025

    beat_times, chroma, _ = beat_chroma(synth([("N", 4), ("C:maj", 4)]))
    lead = beat_times < 1.75

    assert beat_times[0] < 0.5
    assert lead.any()
    assert _labels(chroma[:, lead]) == ["N"] * lead.sum()


def test_all_silent_audio_has_no_beats() -> None:
    with pytest.raises(NoBeatsError):
        beat_chroma(np.zeros(4 * SR, dtype=np.float32))


def test_a_single_beat_extends_the_grid_at_the_tempo_period(synth, monkeypatch) -> None:
    y = synth([("C:maj", 16)])
    frame = int(4 * SR / 512)
    monkeypatch.setattr(
        "chordotomy.features.librosa.beat.beat_track", lambda **_: (120.0, np.array([frame]))
    )

    beat_times, chroma, cqt = beat_chroma(y)

    assert chroma.shape[1] == len(beat_times)
    assert cqt.shape[1] == len(beat_times)
    assert np.allclose(np.diff(beat_times), 0.5, atol=0.02)
    assert beat_times[0] < 0.5
    assert len(y) / SR - beat_times[-1] <= 1.0


def _basses(cqt: np.ndarray) -> list[str | None]:
    return [pick_bass(column) for column in cqt.T]


@pytest.mark.parametrize(("bass_midi", "expected"), [(36, "C"), (40, "E"), (38, "D")])
def test_the_cqt_names_the_bass_tone_under_a_chord(synth, bass_midi, expected) -> None:
    _, _, cqt = beat_chroma(synth([("C:maj", 8, bass_midi)]))

    assert _basses(cqt) == [expected] * cqt.shape[1]


def test_silent_beats_mid_track_have_an_all_zero_cqt(synth) -> None:
    beat_times, _, cqt = beat_chroma(synth([("C:maj", 4, 40), ("N", 4), ("F:maj", 4, 36)]))

    # The same window as the chroma's silence test, so the first silent beat's ringing is in it.
    silent = (beat_times >= 1.75) & (beat_times < 3.75)
    before = beat_times < 1.75
    after = beat_times >= 4.25

    assert silent.any() and before.any() and after.any()
    assert np.all(cqt[:, silent] == 0)
    assert _basses(cqt[:, silent]) == [None] * silent.sum()
    assert _basses(cqt[:, before]) == ["E"] * before.sum()
    assert _basses(cqt[:, after]) == ["C"] * after.sum()


def test_a_chord_above_the_register_has_no_bass_until_one_sounds(synth) -> None:
    _, chroma, cqt = beat_chroma(synth([("C:maj", 8)], chord_midi=60))

    # The chord path is octave-invariant, so the same chord still reads C:maj an octave up.
    assert _labels(chroma) == ["C:maj"] * chroma.shape[1]
    # Nothing sounds in the register; C4's leakage into B3 is a slope, not a peak.
    assert _basses(cqt) == [None] * cqt.shape[1]

    _, _, cqt = beat_chroma(synth([("C:maj", 8, 40)], chord_midi=60))

    assert _basses(cqt) == ["E"] * cqt.shape[1]
