import json
from itertools import pairwise

import numpy as np
import pytest
import soundfile

from chordotomy import __version__
from chordotomy.features import SR, NoBeatsError
from chordotomy.timeline import analyze


def _write(tmp_path, y):
    path = tmp_path / "clip.wav"
    soundfile.write(path, y, SR)
    return path


def test_analyze_builds_the_schema(synth, chord_at, tmp_path) -> None:
    progression = [
        ("C:maj", 2),
        ("C:7", 2),
        ("F:maj", 2),
        ("G:7", 2),
        ("A:min", 2),
        ("C:maj", 2),
    ]
    path = _write(tmp_path, synth(progression))

    result = analyze(path)

    json.dumps(result)
    assert result["schema_version"] == 3
    assert result["generator"] == {"name": "chordotomy", "version": __version__}
    assert result["source"]["path"] == str(path)
    duration = result["source"]["duration"]
    assert abs(duration - 6.0) <= 0.01
    beats = result["beats"]
    assert len(beats) >= 10
    assert abs(np.median(np.diff(beats)) - 0.5) <= 0.025

    segments = result["segments"]
    assert segments[0]["start_beat"] == 0
    assert segments[-1]["end_beat"] == len(beats)
    for previous, current in pairwise(segments):
        assert previous["end_beat"] == current["start_beat"]
    for s in segments:
        assert s["start_beat"] < s["end_beat"]
        assert s["start_time"] == beats[s["start_beat"]]
        end = duration if s["end_beat"] == len(beats) else beats[s["end_beat"]]
        assert s["end_time"] == end
        assert len(set(s["candidates"])) == 3
        assert s["candidates"][0] == s["chord"]
        assert {"bass", "inversion", "numeral", "role", "function", "target"} <= s.keys()
    assert [s["chord"] for s in segments] == ["C:maj", "C:7", "F:maj", "G:7", "A:min", "C:maj"]

    labels = [s["chord"] for s in segments for _ in range(s["start_beat"], s["end_beat"])]
    assert len(labels) == len(beats)
    for i, label in enumerate(labels):
        end = beats[i + 1] if i + 1 < len(beats) else duration
        assert label == chord_at(progression, (beats[i] + end) / 2)


def test_silence_between_chords_is_n(synth, tmp_path) -> None:
    result = analyze(_write(tmp_path, synth([("C:maj", 4), ("N", 4), ("F:maj", 4)])))
    segments = result["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "N", "F:maj"]
    assert abs(segments[1]["start_time"] - 2.0) <= 0.3
    assert abs(segments[1]["end_time"] - 4.0) <= 0.3
    assert segments[-1]["end_time"] == result["source"]["duration"]
    fields = ("numeral", "role", "function", "target", "bass", "inversion")
    assert all(segments[1][f] is None for f in fields)
    assert [segments[i]["bass"] for i in (0, 2)] == ["C", "F"]
    assert all(segments[i]["inversion"] == "root" for i in (0, 2))
    assert all(segments[i][f] is not None for i in (0, 2) for f in ("numeral", "role"))


def test_analyze_labels_the_progression(synth, tmp_path) -> None:
    progression = [("C:maj", 2), ("A:min", 2), ("D:7", 2), ("G:7", 2), ("C:maj", 2)]

    result = analyze(_write(tmp_path, synth(progression)))

    json.dumps(result)
    key = result["key"]
    assert key["label"] == "C:maj"
    assert key["source"] == "estimated"
    assert key["candidates"][0] == "C:maj"
    assert len(set(key["candidates"])) == 3
    segments = result["segments"]
    assert [s["numeral"] for s in segments] == ["I", "vi", "V7/V", "V7", "I"]
    assert segments[2]["role"] == "secondary_dominant"
    assert segments[2]["target"] == "V"
    assert segments[3]["function"] == "dominant"


def test_bass_and_inversion_follow_the_bass_line(synth, tmp_path) -> None:
    progression = [
        ("C:maj", 2, 36),
        ("F:maj", 2, 45),
        ("G:7", 2, 41),
        ("C:maj", 2, 43),
        ("A:min", 2, 36),
        ("C:maj", 2, 38),
    ]

    result = analyze(_write(tmp_path, synth(progression)))

    json.dumps(result)
    segments = result["segments"]
    assert [s["chord"] for s in segments] == ["C:maj", "F:maj", "G:7", "C:maj", "A:min", "C:maj"]
    assert [s["bass"] for s in segments] == ["C", "A", "F", "G", "C", "D"]
    assert [s["inversion"] for s in segments] == [
        "root",
        "first",
        "third",
        "second",
        "first",
        "non_chord",
    ]
    assert [s["numeral"] for s in segments] == ["I", "IV", "V7", "I", "vi", "I"]


def test_bass_is_none_without_a_bass_note(synth, tmp_path) -> None:
    result = analyze(_write(tmp_path, synth([("N", 4), ("C:7", 4, 46), ("N", 4)])))
    segments = result["segments"]

    assert [s["bass"] for s in segments] == [None, "A#", None]
    assert [s["inversion"] for s in segments] == [None, "third", None]

    result = analyze(_write(tmp_path, synth([("C:maj", 8)], chord_midi=60)))
    (only,) = result["segments"]

    assert only["chord"] == "C:maj"
    assert only["bass"] is None
    assert only["inversion"] is None


def test_edge_silence_is_n(synth, tmp_path) -> None:
    result = analyze(_write(tmp_path, synth([("C:maj", 4), ("N", 6)])))
    segments = result["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "N"]
    assert abs(segments[1]["start_time"] - 2.0) <= 0.3
    assert segments[1]["end_time"] == result["source"]["duration"]

    result = analyze(_write(tmp_path, synth([("N", 4), ("C:maj", 4)])))
    segments = result["segments"]

    assert [s["chord"] for s in segments] == ["N", "C:maj"]
    assert segments[0]["start_time"] == result["beats"][0]
    assert segments[0]["start_time"] < 0.5
    assert abs(segments[1]["start_time"] - 2.0) <= 0.3


def test_all_silent_audio_has_no_beats(tmp_path) -> None:
    with pytest.raises(NoBeatsError):
        analyze(_write(tmp_path, np.zeros(4 * SR, dtype=np.float32)))
