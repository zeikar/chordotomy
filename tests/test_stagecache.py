import sys

import numpy as np
import soundfile

from chordotomy import chords, features, stagecache, timeline
from chordotomy.features import SR
from chordotomy.stagecache import StageCache, fingerprint

# The stages below read these, so a test can change what decides their output. Each counts its
# runs on an attribute of its own: a global it read to count them would be part of its key.
FACTOR = 2.0
OFFSETS = {"a": 1.0}


def doubled(y: np.ndarray) -> np.ndarray:
    doubled.runs += 1
    return y * FACTOR


def _offset() -> float:
    return OFFSETS["a"]


def shifted(y: np.ndarray, by: float | None = None) -> np.ndarray:
    shifted.runs += 1
    return y + _offset() + (by or 0.0)


def scored(y: np.ndarray) -> np.ndarray:
    scored.runs += 1
    return y * chords.N_SCORE


def _cache(tmp_path) -> StageCache:
    doubled.runs = shifted.runs = scored.runs = 0
    return StageCache(tmp_path / "stages")


def test_a_stage_runs_once_per_input(tmp_path) -> None:
    cache = _cache(tmp_path)
    y = np.arange(4.0)

    first = cache.run(doubled, y)
    second = cache.run(doubled, y)
    other = cache.run(doubled, y + 1)

    assert doubled.runs == 2
    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(other, (y + 1) * 2)
    assert len(list((tmp_path / "stages").glob("*.pkl"))) == 2


def test_keyword_arguments_are_part_of_the_input(tmp_path) -> None:
    cache = _cache(tmp_path)
    y = np.zeros(3)

    cache.run(shifted, y, by=None)
    cache.run(shifted, y, by=None)
    cache.run(shifted, y, by=1.0)

    assert shifted.runs == 2


def test_a_constant_the_stage_reads_is_part_of_the_key(tmp_path, monkeypatch) -> None:
    cache = _cache(tmp_path)
    y = np.ones(3)
    cache.run(doubled, y)

    # A sweep reassigning a constant: a stale result would come back as 2.
    monkeypatch.setattr(sys.modules[__name__], "FACTOR", 3.0)

    np.testing.assert_array_equal(cache.run(doubled, y), y * 3)
    assert doubled.runs == 2


def test_a_value_read_by_a_helper_is_part_of_the_key(tmp_path, monkeypatch) -> None:
    cache = _cache(tmp_path)
    y = np.zeros(2)
    cache.run(shifted, y)

    monkeypatch.setitem(OFFSETS, "a", 5.0)

    np.testing.assert_array_equal(cache.run(shifted, y), y + 5)


def test_an_attribute_of_a_package_module_is_part_of_the_key(tmp_path, monkeypatch) -> None:
    cache = _cache(tmp_path)
    y = np.ones(2)
    cache.run(scored, y)

    monkeypatch.setattr(chords, "N_SCORE", 0.5)

    np.testing.assert_array_equal(cache.run(scored, y), y * 0.5)


def test_the_package_versions_are_part_of_the_key(tmp_path, monkeypatch) -> None:
    cache = _cache(tmp_path)
    y = np.ones(2)
    cache.run(doubled, y)

    monkeypatch.setattr(stagecache, "_version", lambda name: "9.9" if name == "librosa" else "1")

    cache.run(doubled, y)
    assert doubled.runs == 2


def test_what_the_stage_does_not_reach_is_not_part_of_the_key(monkeypatch) -> None:
    # The bass rules run after the cached stages, so sweeping them keeps the cache.
    before = fingerprint(features.beat_features)
    monkeypatch.setattr(chords, "BASS_HOLD", 5)
    assert fingerprint(features.beat_features) == before
    monkeypatch.setitem(chords.QUALITY_OFFSET, "sus4", -0.3)
    assert fingerprint(features.beat_features) != before


def test_a_damaged_entry_is_computed_again(tmp_path) -> None:
    cache = _cache(tmp_path)
    y = np.ones(2)
    cache.run(doubled, y)
    cache.path(doubled, y).write_bytes(b"\x80\x05cut sh")

    np.testing.assert_array_equal(cache.run(doubled, y), y * 2)
    assert doubled.runs == 2
    np.testing.assert_array_equal(cache.run(doubled, y), y * 2)
    assert doubled.runs == 2


def test_analyze_is_the_same_with_the_cache(synth, tmp_path, monkeypatch) -> None:
    path = tmp_path / "clip.wav"
    soundfile.write(path, synth([("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4)]), SR)
    cache = StageCache(tmp_path / "stages")
    plain = timeline.analyze(path)

    cold = timeline.analyze(path, cache=cache)
    entries = sorted((tmp_path / "stages").glob("*.pkl"))
    # A warm run reads the features back instead of computing them.
    monkeypatch.setattr(features.librosa.effects, "harmonic", lambda y: 1 / 0)
    warm = timeline.analyze(path, cache=cache)

    assert cold == plain
    assert warm == plain
    assert [p.name.partition("-")[0] for p in entries] == ["chordotomy.features.beat_features"]
    assert sorted((tmp_path / "stages").glob("*.pkl")) == entries
