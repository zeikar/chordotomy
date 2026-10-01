import librosa
import numpy as np
import pytest
import soundfile

from chordotomy import features
from chordotomy.chords import LABELS, N_GATE_DB, ONSET_FRACTION, match, pick_bass
from chordotomy.features import (
    HOP,
    SR,
    Features,
    NoBeatsError,
    _changes_between,
    beat_features,
    load_audio,
)


def _labels(f: Features) -> list[str]:
    return [LABELS[i] for i in match(f.treble, f.bass).argmax(axis=0)]


def test_load_and_beat_features_on_a_repeated_chord(synth, tmp_path) -> None:
    y = synth([("C:maj", 8, 36)])
    path = tmp_path / "clip.wav"
    soundfile.write(path, y, SR)

    loaded = load_audio(path)

    assert abs(len(loaded) - len(y)) <= 1

    f = beat_features(loaded)
    n = len(f.times)

    assert n >= 6
    np.testing.assert_array_equal(f.times, librosa.frames_to_time(f.frames, sr=SR, hop_length=HOP))
    assert np.all(np.diff(f.frames) > 0)
    assert abs(np.median(np.diff(f.times)) - 0.5) <= 0.025
    assert f.treble.shape == (12, n)
    assert f.bass.shape == (12, n)
    assert f.cqt.shape == (84, n)
    assert f.level.shape == (n,)
    for column in f.treble.T:
        assert set(np.argsort(column)[-3:]) == {0, 4, 7}
    assert list(f.bass.argmax(axis=0)) == [0] * n


def test_silent_beats_mid_track_fall_below_the_n_gate(synth) -> None:
    f = beat_features(synth([("C:maj", 4), ("N", 4), ("F:maj", 4)]))
    n = len(f.times)

    # The window starts before 2.0 s to take in the first silent beat: it carries the previous
    # chord's CQT ringing, which whitening would turn into a chord shape.
    silent = (f.times >= 1.75) & (f.times < 3.75)

    assert silent.any()
    assert f.treble.shape == f.bass.shape == (12, n)
    assert f.level.shape == (n,)
    assert np.all(f.level[silent] < -N_GATE_DB)
    assert np.all(f.level[~silent] > -N_GATE_DB)


def test_the_n_evidence_tells_silence_and_drums_from_chords(synth, drums) -> None:
    f = beat_features(synth([("C:maj", 4), ("N", 4), ("F:maj", 4)]))
    # The same window as the level's silence test. Its first beat carries the cut-off chord's last
    # frames and its last the next strike's first, which the per-frame median outvotes.
    silent = (f.times >= 1.75) & (f.times < 3.75)

    assert f.onset.shape == f.flatness.shape == f.harmonic.shape == (len(f.times),)
    assert np.all(f.flatness[silent] > 0.9)
    assert np.all(f.harmonic[silent] == 0)
    assert np.all(f.flatness[~silent] < 0.01)
    assert np.all(f.harmonic[~silent] > 0.5)
    assert np.all(f.onset[~silent] > ONSET_FRACTION)

    burst = drums(8)
    f = beat_features(burst)

    # Measured: a share of 0.002 at most. Flatness does not tell these beats: the kick's harmonic
    # residue is low and narrow, 0.002-0.04.
    assert np.all(f.harmonic < 0.1), f.harmonic

    f = beat_features(np.concatenate([synth([("C:maj", 4)]), burst, synth([("F:maj", 4)])]))
    between = (f.times >= 1.75) & (f.times < 5.75)

    # Beside chords the drum beats are quiet, which is what makes them N even where HPSS lends
    # the first and last of them the chords' tones (flatness 0.0004-0.001). Measured: -45 to -61 dB.
    assert between.sum() == 8
    assert np.all(f.level[between] < -N_GATE_DB), f.level[between]
    assert np.all(f.harmonic[between] < 0.1), f.harmonic[between]


def test_grid_extends_through_edge_silence(synth) -> None:
    y = synth([("C:maj", 4), ("N", 6)])
    f = beat_features(y)

    assert f.times[-1] >= len(y) / SR - 0.75
    assert abs(np.median(np.diff(f.times)) - 0.5) <= 0.025

    f = beat_features(synth([("N", 4), ("C:maj", 4)]))
    n = len(f.times)
    lead = f.times < 1.75

    assert f.times[0] < 0.5
    assert lead.any()
    assert f.treble.shape == f.bass.shape == (12, n)
    assert f.level.shape == (n,)
    assert np.all(f.level[lead] < -N_GATE_DB)


def test_all_silent_audio_has_no_beats() -> None:
    with pytest.raises(NoBeatsError):
        beat_features(np.zeros(4 * SR, dtype=np.float32))


def test_a_single_beat_extends_the_grid_at_the_tempo_period(synth, monkeypatch) -> None:
    y = synth([("C:maj", 16)])
    frame = int(4 * SR / 512)
    monkeypatch.setattr(
        "chordotomy.features.librosa.beat.beat_track", lambda **_: (120.0, np.array([frame]))
    )

    f = beat_features(y)

    assert f.treble.shape[1] == len(f.times)
    assert f.bass.shape[1] == len(f.times)
    assert f.cqt.shape[1] == len(f.times)
    assert f.level.shape == (len(f.times),)
    assert f.onset.shape == f.flatness.shape == f.harmonic.shape == (len(f.times),)
    assert np.allclose(np.diff(f.times), 0.5, atol=0.02)
    assert f.times[0] < 0.5
    assert len(y) / SR - f.times[-1] <= 1.0


def test_the_grid_extends_at_the_edge_gaps(synth, monkeypatch) -> None:
    # Known frames, because the tracker keeps one tempo per file and bends it only slowly, so this
    # proves the extension and nothing else.
    silence = np.zeros(2 * SR, dtype=np.float32)
    y = np.concatenate([silence, synth([("C:maj", 16)]), silence])
    fast, slow = round(0.5 * SR / HOP), round(0.75 * SR / HOP)
    # From 2.0 s, 8 gaps of 0.5 s, then 4 of 0.75 s ending at 9.0 s, 3 s before the end.
    frames = round(2.0 * SR / HOP) + np.cumsum([0] + [fast] * 8 + [slow] * 4)
    monkeypatch.setattr("chordotomy.features.librosa.beat.beat_track", lambda **_: (120.0, frames))

    f = beat_features(y)

    first, last = np.searchsorted(f.frames, frames[[0, -1]])
    np.testing.assert_array_equal(f.frames[first : last + 1], frames)
    head = np.diff(f.times[: first + 1])
    tail = np.diff(f.times[last:])
    assert len(head) == 3 and len(tail) == 3
    assert np.allclose(head, 0.5, atol=HOP / SR)
    assert np.allclose(tail, 0.75, atol=HOP / SR)


def _changes_at(starts) -> np.ndarray:
    """States over 100 doubled-grid beats whose chord changes start at the given beats."""
    return np.cumsum(np.isin(np.arange(100), list(starts)))


def test_too_slow_reads_the_change_positions() -> None:
    # Read when the test runs, so a margin run that assigns the constant is tested at its value.
    end = 2 * features.OCTAVE_MIN_CHANGES + 1
    # Parity 0: the tracker's beats are the even ones, the inserted ones odd.
    assert _changes_between(_changes_at(range(1, end, 2)), 0)
    # The same changes on the tracker's beats.
    assert not _changes_between(_changes_at(range(1, end, 2)), 1)
    # One change short of OCTAVE_MIN_CHANGES.
    assert not _changes_between(_changes_at(range(1, end - 2, 2)), 0)
    # Twice as many changes, half of them on inserted beats.
    assert not _changes_between(_changes_at(range(1, end)), 0)
    assert not _changes_between(_changes_at([]), 0)


def _basses(cqt: np.ndarray) -> list[str | None]:
    return [pick_bass(column) for column in cqt.T]


@pytest.mark.parametrize(("bass_midi", "expected"), [(36, "C"), (40, "E"), (38, "D")])
def test_the_cqt_names_the_bass_tone_under_a_chord(synth, bass_midi, expected) -> None:
    cqt = beat_features(synth([("C:maj", 8, bass_midi)])).cqt

    assert _basses(cqt) == [expected] * cqt.shape[1]


def test_silent_beats_mid_track_have_an_all_zero_cqt(synth) -> None:
    f = beat_features(synth([("C:maj", 4, 40), ("N", 4), ("F:maj", 4, 36)]))
    beat_times, cqt = f.times, f.cqt

    # The same window as the level's silence test, so the first silent beat's ringing is in it.
    silent = (beat_times >= 1.75) & (beat_times < 3.75)
    before = beat_times < 1.75
    after = beat_times >= 4.25

    assert silent.any() and before.any() and after.any()
    assert np.all(cqt[:, silent] == 0)
    assert _basses(cqt[:, silent]) == [None] * silent.sum()
    assert _basses(cqt[:, before]) == ["E"] * before.sum()
    assert _basses(cqt[:, after]) == ["C"] * after.sum()


def test_a_chord_above_the_register_has_no_bass_until_one_sounds(synth) -> None:
    f = beat_features(synth([("C:maj", 8)], chord_midi=60))

    # The chord path is octave-invariant, so the same chord still reads C:maj an octave up.
    assert _labels(f) == ["C:maj"] * len(f.times)
    # Nothing sounds in the register; C4's leakage into B3 is a slope, not a peak.
    assert _basses(f.cqt) == [None] * f.cqt.shape[1]
    # So the leakage casts no bass vote either.
    assert np.all(f.bass == 0)

    f = beat_features(synth([("C:maj", 8, 40)], chord_midi=60))

    assert _basses(f.cqt) == ["E"] * f.cqt.shape[1]
    assert np.all(f.bass.any(axis=0))
