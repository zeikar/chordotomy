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


def test_a_bass_held_two_beats_under_one_chord_cuts_and_is_reported(synth, tmp_path) -> None:
    result = analyze(_write(tmp_path, synth([("C:maj", 4, 36), ("C:maj", 4, 40)])))
    segments = result["segments"]

    assert [(s["start_beat"], s["end_beat"]) for s in segments] == [(0, 4), (4, 8)]
    assert [s["chord"] for s in segments] == ["C:maj", "C:maj"]
    assert [s["bass"] for s in segments] == ["C", "E"]
    assert [s["inversion"] for s in segments] == ["root", "first"]
    assert [s["numeral"] for s in segments] == ["I", "I"]


def test_a_shorter_bass_move_under_an_unchanged_chord_is_not_reported(synth, tmp_path) -> None:
    progression = [("C:maj", 3, 36), ("C:maj", 1, 40), ("C:maj", 4, 36)]

    (only,) = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert only["bass"] == "C"


def test_an_alternating_bass_under_one_chord_is_one_root_position_segment(synth, tmp_path) -> None:
    progression = [("C:maj", 1, 36), ("C:maj", 1, 40)] * 4

    (only,) = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert only["bass"] == "C"
    assert only["inversion"] == "root"


def test_a_bass_change_on_a_chord_change_adds_no_cut(synth, tmp_path) -> None:
    result = analyze(_write(tmp_path, synth([("C:maj", 4, 36), ("F:maj", 4, 45)])))

    assert len(result["segments"]) == 2


def test_a_one_beat_slash_chord_with_a_chord_change_is_its_own_segment(synth, tmp_path) -> None:
    progression = [("C:maj", 4, 36), ("G:maj", 1, 47), ("A:min", 3, 45)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [(s["start_beat"], s["end_beat"]) for s in segments] == [(0, 4), (4, 5), (5, 8)]
    assert [s["chord"] for s in segments] == ["C:maj", "G:maj", "A:min"]
    assert [s["bass"] for s in segments] == ["C", "B", "A"]
    assert [s["inversion"] for s in segments] == ["root", "first", "root"]
    assert [s["numeral"] for s in segments] == ["I", "V", "vi"]


def test_a_chord_split_on_the_bass_looks_ahead_to_the_next_chord(synth, tmp_path) -> None:
    progression = [
        ("A:min", 4, 45),
        ("A:maj", 2, 37),
        ("A:maj", 2, 40),
        ("D:min", 4, 38),
        ("A:min", 4, 45),
    ]

    segments = analyze(_write(tmp_path, synth(progression)), key="A:min")["segments"]

    assert [s["chord"] for s in segments] == ["A:min", "A:maj", "A:maj", "D:min", "A:min"]
    assert [s["bass"] for s in segments] == ["A", "C#", "E", "D", "A"]
    assert [s["inversion"] for s in segments] == ["root", "first", "second", "root", "root"]
    # Both halves of the split A:maj resolve to the D:min that follows the run.
    assert [s["numeral"] for s in segments] == ["i", "V/iv", "V/iv", "iv", "i"]


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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "a flat chroma matches the N template; "
        "the whitened front end removes N from the template race"
    ),
)
def test_a_mix_like_clip_keeps_its_chords(mix, chord_at, tmp_path) -> None:
    progression = [("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4)]

    result = analyze(_write(tmp_path, mix(progression)))

    segments = result["segments"]
    beats = result["beats"]
    assert "N" not in [s["chord"] for s in segments], [s["chord"] for s in segments]
    correct = total = 0
    for s in segments:
        for i in range(s["start_beat"], s["end_beat"]):
            end = beats[i + 1] if i + 1 < len(beats) else result["source"]["duration"]
            midpoint = (beats[i] + end) / 2
            if midpoint >= 8.0:
                continue
            total += 1
            correct += s["chord"].split(":")[0] == chord_at(progression, midpoint).split(":")[0]
    assert correct >= 15, (correct, total)
