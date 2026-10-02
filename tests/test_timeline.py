import json
from itertools import pairwise

import librosa
import numpy as np
import pytest
import soundfile

from chordotomy import __version__, features, model, timeline
from chordotomy.chords import LABELS
from chordotomy.features import HOP, SR, NoBeatsError
from chordotomy.timeline import analyze


def _write(tmp_path, y):
    path = tmp_path / "clip.wav"
    soundfile.write(path, y, SR)
    return path


def test_chord_runs_join_a_chord_split_by_the_bass() -> None:
    segments = [
        {"chord": "A:maj", "start_beat": 0, "end_beat": 2},
        {"chord": "A:maj", "start_beat": 2, "end_beat": 4},
        {"chord": "N", "start_beat": 4, "end_beat": 5},
        {"chord": "D:min", "start_beat": 5, "end_beat": 8},
    ]

    runs = timeline.chord_runs(segments)

    assert [len(run) for run in runs] == [2, 1, 1]
    assert timeline.progression(runs) == [("A:maj", 4), ("N", 1), ("D:min", 3)]


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
    assert result["schema_version"] == 8
    assert result["generator"] == {
        "name": "chordotomy",
        "version": __version__,
        "engine": {"name": "dsp", "version": __version__},
    }
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
        assert {"bass", "inversion", "numeral", "role", "function", "target", "edited"} <= s.keys()
        assert s["edited"] is False
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


def test_a_passing_bass_on_the_first_beat_of_a_two_beat_chord_is_not_a_slash(
    synth, tmp_path
) -> None:
    progression = [("G:maj", 6, 43), ("C:maj", 1, 39), ("C:maj", 1, 36)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["G:maj", "C:maj"]
    assert [s["bass"] for s in segments] == ["G", "C"]
    assert segments[1]["inversion"] == "root"


def test_a_held_non_chord_slash_survives(synth, tmp_path) -> None:
    segments = analyze(_write(tmp_path, synth([("D:maj", 4, 38), ("D:maj", 4, 40)])))["segments"]

    assert [(s["start_beat"], s["end_beat"]) for s in segments] == [(0, 4), (4, 8)]
    assert [s["bass"] for s in segments] == ["D", "E"]
    assert [s["inversion"] for s in segments] == ["root", "non_chord"]
    assert [s["numeral"] for s in segments] == ["I", "I"]


def test_a_weak_non_chord_bass_reads_root_position(synth, tmp_path) -> None:
    # A D1 struck as loud as the C2 above it is the lowest salient note but not the loudest
    # (0.85 of the register's strongest): a leak below the root, not a bass line.
    (only,) = analyze(_write(tmp_path, synth([("C:maj", 8, 36, 26)])))["segments"]

    assert only["chord"] == "C:maj"
    assert only["bass"] == "C"
    assert only["inversion"] == "root"


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


@pytest.mark.parametrize(("quality", "numeral"), [("dim7", "vii°7/V"), ("hdim7", "viiø7/V")])
def test_a_diminished_chord_without_a_bass_is_spelled_by_where_it_leads(
    synth, tmp_path, quality, numeral
) -> None:
    # Voiced above the bass register, the twins tie and decode as C:dim7 and A:min6.
    progression = [("C:maj", 4), (f"F#:{quality}", 4), ("G:maj", 4), ("C:maj", 4)]

    segments = analyze(_write(tmp_path, synth(progression, chord_midi=60)))["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", f"F#:{quality}", "G:maj", "C:maj"]
    assert segments[1]["numeral"] == numeral
    assert segments[1]["bass"] is None


@pytest.mark.parametrize(
    ("bass", "note", "position"),
    [(37, "C#", "root"), (40, "E", "first"), (43, "G", "second"), (46, "A#", "third")],
)
def test_a_diminished_seventh_is_spelled_by_where_it_leads_over_any_bass(
    synth, tmp_path, bass, note, position
) -> None:
    # The bass roots the recognizer's reading on itself (E:dim7 over E); the resolution to D:min7
    # respells it C#:dim7 in first inversion.
    progression = [
        ("C:maj", 4, 36),
        ("C#:dim7", 4, bass),
        ("D:min7", 4, 38),
        ("G:7", 4, 43),
        ("C:maj", 4, 36),
    ]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "C#:dim7", "D:min7", "G:7", "C:maj"]
    assert [s["numeral"] for s in segments] == ["I", "vii°7/ii", "ii7", "V7", "I"]
    assert (segments[1]["role"], segments[1]["target"]) == ("secondary_dominant", "ii")
    assert (segments[1]["bass"], segments[1]["inversion"]) == (note, position)


def test_a_diminished_seventh_over_a_moving_bass_is_one_chord(synth, tmp_path) -> None:
    # Held four beats each, A and F# decode as A:dim7 and F#:dim7 before the respelling.
    progression = [
        ("C:maj", 4, 36),
        ("D#:dim7", 4, 45),
        ("D#:dim7", 4, 42),
        ("E:min", 4, 40),
        ("C:maj", 4, 36),
    ]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "D#:dim7", "D#:dim7", "E:min", "C:maj"]
    assert [s["inversion"] for s in segments[1:3]] == ["second", "first"]
    assert [s["numeral"] for s in segments[1:3]] == ["vii°7/iii", "vii°7/iii"]


def test_a_ii_v_i_of_sevenths_keeps_its_sevenths(synth, tmp_path) -> None:
    progression = [("D:min7", 4, 38), ("G:7", 4, 43), ("C:maj7", 4, 36)]

    result = analyze(_write(tmp_path, synth(progression)))

    segments = result["segments"]
    assert result["key"]["label"] == "C:maj"
    assert [s["chord"] for s in segments] == ["D:min7", "G:7", "C:maj7"]
    assert [s["numeral"] for s in segments] == ["ii7", "V7", "Imaj7"]
    assert [s["inversion"] for s in segments] == ["root", "root", "root"]


def test_a_suspension_resolves_to_its_triad(synth, tmp_path) -> None:
    progression = [("C:maj", 4, 36), ("G:sus4", 4, 43), ("G:maj", 4, 43), ("C:maj", 4, 36)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "G:sus4", "G:maj", "C:maj"]
    assert [s["numeral"] for s in segments] == ["I", "Vsus4", "V", "I"]
    assert [(s["bass"], s["inversion"]) for s in segments[1:3]] == [("G", "root"), ("G", "root")]


def test_the_dsp_never_calls_a_seventh_sus4(synth, tmp_path) -> None:
    # A played V7sus4 needs sus4(b7) at -0.23 or higher; Tiny AAM's floors need -0.2375 or lower
    # (see QUALITY_OFFSET), so the decoder leaves it to the model engine and the editor.
    progression = [("D:maj", 4, 38), ("A:sus4(b7)", 4, 45), ("A:7", 4, 45), ("D:maj", 4, 38)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert not any(
        label.endswith(":sus4(b7)") for s in segments for label in [s["chord"], *s["candidates"]]
    )
    assert [s["numeral"] for s in segments if s["chord"] == "D:maj"] == ["I", "I"]


def test_a_plain_suspension_is_not_a_seventh_suspension(synth, tmp_path) -> None:
    progression = [("D:maj", 4, 38), ("A:sus4", 4, 45), ("A:maj", 4, 45), ("D:maj", 4, 38)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["D:maj", "A:sus4", "A:maj", "D:maj"]
    assert [s["numeral"] for s in segments] == ["I", "Vsus4", "V", "I"]


def test_a_dominant_seventh_is_not_a_seventh_suspension(synth, tmp_path) -> None:
    progression = [("D:maj", 4, 38), ("A:7", 4, 45), ("D:maj", 4, 38)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["D:maj", "A:7", "D:maj"]
    assert [s["numeral"] for s in segments] == ["I", "V7", "I"]


def test_a_diminished_triad_on_the_leading_tone_is_diatonic(synth, tmp_path) -> None:
    progression = [("C:maj", 4, 36), ("B:dim", 2, 38), ("C:maj", 4, 40)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "B:dim", "C:maj"]
    assert [s["numeral"] for s in segments] == ["I", "vii°", "I"]
    assert [s["inversion"] for s in segments] == ["root", "first", "first"]
    assert (segments[1]["role"], segments[1]["function"]) == ("diatonic", "dominant")


@pytest.mark.parametrize(
    ("progression", "chord_midi"),
    [
        ([("C:maj", 4, 36), ("G:aug", 4, 43), ("C:maj", 4, 36)], 48),
        ([("C:maj", 4), ("G:aug", 4), ("C:maj", 4)], 60),
    ],
    ids=["bass", "no-bass"],
)
def test_an_augmented_dominant_is_spelled_by_where_it_leads(
    synth, tmp_path, progression, chord_midi
) -> None:
    # Over a G bass the recognizer decodes G:aug on the bass. Without one, the lowest root
    # D#:aug wins the tie and resolve_twins respells it a fifth above the C.
    segments = analyze(_write(tmp_path, synth(progression, chord_midi=chord_midi)))["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "G:aug", "C:maj"]
    assert (segments[1]["numeral"], segments[1]["role"]) == ("V+", "chromatic")
    if chord_midi == 60:
        assert segments[1]["candidates"][1] == "D#:aug"


def test_the_dsp_never_calls_a_suspended_second(synth, tmp_path) -> None:
    # A played Csus2 and a triad with an added ninth cannot both be told from the triad, so the
    # decoder leaves sus2 to the model engine and the editor.
    progression = [("C:maj", 4, 36), ("C:sus2", 4, 36), ("C:maj", 4, 36)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert not any(
        label.endswith(":sus2") for s in segments for label in [s["chord"], *s["candidates"]]
    )


def test_an_added_ninth_is_not_a_suspended_second(synth, tmp_path) -> None:
    # A D an octave above the triad, then inside it, is C:sus2's second; the third still sounds,
    # so it is C:maj.
    progression = [("C:maj", 4, 36, 74), ("C:maj", 4, 36, 62)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert {(s["chord"], s["numeral"]) for s in segments} == {("C:maj", "I")}


@pytest.mark.parametrize(
    ("following", "bass", "numeral", "role"),
    [("G:maj", 43, "viiø7/V", "secondary_dominant"), ("F:maj", 41, "#ivø7", "chromatic")],
)
def test_a_half_diminished_is_secondary_only_when_it_resolves(
    synth, tmp_path, following, bass, numeral, role
) -> None:
    progression = [("C:maj", 4, 36), ("F#:hdim7", 2, 42), (following, 4, bass), ("C:maj", 4, 36)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "F#:hdim7", following, "C:maj"]
    assert (segments[1]["numeral"], segments[1]["role"]) == (numeral, role)


def test_a_minor_sixth_on_the_subdominant_is_borrowed(synth, tmp_path) -> None:
    progression = [("C:maj", 4, 36), ("F:maj", 2, 41), ("F:min6", 2, 41), ("C:maj", 4, 36)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert [s["chord"] for s in segments] == ["C:maj", "F:maj", "F:min6", "C:maj"]
    assert (segments[2]["numeral"], segments[2]["role"]) == ("ivadd6", "borrowed")
    assert (segments[2]["bass"], segments[2]["inversion"]) == ("F", "root")


def test_a_melody_over_a_triad_is_not_a_seventh(synth, tmp_path) -> None:
    # One entry per beat is one eight-beat C:maj, as synth strikes every beat anew. B is
    # C:maj7's seventh, and A turns the chord into A:min7's pitch set.
    progression = [("C:maj", 1, 36, melody) for melody in (71, 69, 67, 65, 64, 62, 60, 71)]

    segments = analyze(_write(tmp_path, synth(progression)))["segments"]

    assert {(s["chord"], s["numeral"]) for s in segments} == {("C:maj", "I")}


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


def _runs(result: dict) -> list[tuple[str, float, float]]:
    """(chord, start time, end time) of each chord run: a bass cut does not split a chord here."""
    return [
        (run[0]["chord"], run[0]["start_time"], run[-1]["end_time"])
        for run in timeline.chord_runs(result["segments"])
    ]


QUIET = 10 ** (-50 / 20)


def test_a_quiet_struck_passage_keeps_its_chords(synth, tmp_path) -> None:
    y = np.concatenate(
        [synth([("C:maj", 4), ("F:maj", 4)]), synth([("G:maj", 4), ("A:min", 4)]) * QUIET]
    )

    runs = _runs(analyze(_write(tmp_path, y)))

    # The quiet chords' bass may be None: their register is under SILENCE_FLOOR.
    assert [chord for chord, _, _ in runs] == ["C:maj", "F:maj", "G:maj", "A:min"]


def test_a_quiet_held_chord_keeps_its_chord(synth, tmp_path) -> None:
    # One strike held 4 s, from -43 to -54 dB: no onset after its first beat, but tonal throughout.
    held = synth([("G:maj", 1)], bpm=15, decay=3.0) * QUIET
    y = np.concatenate([synth([("C:maj", 4), ("F:maj", 4)]), held, synth([("N", 4)])])

    runs = _runs(analyze(_write(tmp_path, y)))

    assert [chord for chord, _, _ in runs] == ["C:maj", "F:maj", "G:maj", "N"]
    _, start, end = runs[2]
    # Measured: G:maj on all eight quiet beats.
    assert end - start >= 3.5, (start, end)
    assert abs(runs[3][1] - 8.0) <= 0.3, runs[3]


def test_drum_bursts_without_harmony_are_n(synth, drums, tmp_path) -> None:
    y = np.concatenate([synth([("C:maj", 4)]), drums(8), synth([("F:maj", 4)])])

    runs = _runs(analyze(_write(tmp_path, y)))

    assert [chord for chord, _, _ in runs] == ["C:maj", "N", "F:maj"]
    _, start, end = runs[1]
    assert abs(start - 2.0) <= 0.3, start
    assert abs(end - 6.0) <= 0.3, end


def test_a_decaying_chord_tail_ends_as_n(synth, tmp_path) -> None:
    # Four strikes, one more left to ring 3 s, then 3 s of digital silence.
    ring = synth([("C:maj", 1)], bpm=20)
    y = np.concatenate([synth([("C:maj", 4)]), ring, synth([("N", 6)])])

    result = analyze(_write(tmp_path, y))
    runs = _runs(result)

    assert [chord for chord, _, _ in runs] == ["C:maj", "N"]
    # Measured for the plan: the ring stays tonal to -73 dB at 4.1 s and turns N at 4.6 s; the
    # silence from 5.0 s is N whatever the floor.
    _, start, end = runs[1]
    assert 4.0 <= start <= 5.3, start
    assert end == result["source"]["duration"]


CYCLE = ("C:maj", "F:maj", "G:maj", "A:min", "D:min", "E:min")


def _two_beat_chords(render, bpm: float, n: int):
    """n two-beat chords cycling through CYCLE at bpm, rendered by `synth` or `half_locked`, and
    every strike's time and chord."""
    progression = [(CYCLE[i % len(CYCLE)], 2) for i in range(n)]
    strikes = np.arange(2 * n) * 60 / bpm
    struck = [label for label, n_beats in progression for _ in range(n_beats)]
    return render(progression, bpm=bpm), strikes, struck


def _nearest(beats: np.ndarray, times: np.ndarray) -> np.ndarray:
    """The index of each time's nearest beat."""
    i = np.clip(np.searchsorted(beats, times), 1, len(beats) - 1)
    return np.where(times - beats[i - 1] < beats[i] - times, i - 1, i)


def _matched(result: dict, strikes: np.ndarray, struck: list[str]) -> tuple[float, float]:
    """The share of strikes with a beat within 70 ms, and the share of those beats that carry the
    chord struck on them."""
    beats = np.array(result["beats"])
    nearest = _nearest(beats, strikes)
    hit = np.abs(beats[nearest] - strikes) <= 0.07
    labels = [s["chord"] for s in result["segments"] for _ in range(s["start_beat"], s["end_beat"])]
    correct = [labels[i] == chord for i, chord, h in zip(nearest, struck, hit, strict=True) if h]
    return float(hit.mean()), float(np.mean(correct))


def test_a_constant_tempo_keeps_the_global_grid(synth, tmp_path) -> None:
    y, strikes, struck = _two_beat_chords(synth, 120, 48)

    result = analyze(_write(tmp_path, y))

    hit, _ = _matched(result, strikes, struck)
    # Measured: all 96 strikes hit, on 96 beats.
    assert hit >= 0.95, hit
    # The octave check's negative case too: two-beat changes on the tracker's beats keep its grid.
    assert abs(len(result["beats"]) - len(strikes)) <= 2, (len(result["beats"]), len(strikes))


def test_a_syncopated_constant_tempo_keeps_the_global_grid(synth, syncopated, tmp_path) -> None:
    # 86 BPM throughout: 8 bars of hats on the eighths, then 8 of syncopated hats.
    chords, strikes, struck = _two_beat_chords(synth, 86, 32)
    y = chords + syncopated(8, 8, 86)
    y = y / np.abs(y).max() * 0.5

    result = analyze(_write(tmp_path, y))

    hit, _ = _matched(result, strikes, struck)
    assert hit >= 0.95, hit
    gaps = np.diff(result["beats"])
    # Measured: the tracker counts eighths, 128 beats of 0.33 to 0.37 s. The removed tempo switch
    # followed the local tempo here: 113 beats of 0.35 to 0.53 s, eighths and wider beats by turns.
    assert gaps.max() < 1.2 * gaps.min(), (gaps.min(), gaps.max())

    flux = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    local = librosa.feature.tempo(onset_envelope=flux, sr=SR, hop_length=HOP, aggregate=None)
    # The premise: a local tempo flickers between metrical levels here (measured: 172, 129 and 112
    # BPM on 53, 28 and 19 % of the frames), which a tempo-following rule takes for a change.
    _, counts = np.unique(np.round(local), return_counts=True)
    assert np.sum(counts >= 0.1 * len(local)) >= 3, counts


def test_a_half_tempo_lock_is_doubled(half_locked, tmp_path, monkeypatch) -> None:
    # 72 beats of 0.333 s, 24 s, 35 chord changes: above OCTAVE_MIN_CHANGES.
    y, strikes, struck = _two_beat_chords(half_locked, 180, 36)
    path = _write(tmp_path, y)

    hit, correct = _matched(analyze(path), strikes, struck)

    # Measured: 71 of 72 strikes hit, on 71 beats of a median 0.325 s, and every matched beat
    # carries the chord struck on it.
    assert hit >= 0.9, hit
    assert correct >= 0.9, correct

    monkeypatch.setattr(features, "OCTAVE_MIN_CHANGES", 10_000)
    hit, _ = _matched(analyze(path), strikes, struck)

    # Measured with the check off: librosa's half lock, 36 beats of 0.673 s on the drummed beats,
    # so 50 % of the strikes hit and 6 % of the matched beats carry their chord.
    assert hit <= 0.6, hit


def test_all_silent_audio_has_no_beats(tmp_path) -> None:
    with pytest.raises(NoBeatsError):
        analyze(_write(tmp_path, np.zeros(4 * SR, dtype=np.float32)))


def test_an_unknown_engine_is_rejected_before_the_audio_is_read(tmp_path) -> None:
    with pytest.raises(ValueError, match="cnn"):
        analyze(tmp_path / "missing.wav", engine="cnn")


NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _head(heard: list[tuple[str | None, int]], n_frames: int, weight: float = 0.97) -> np.ndarray:
    """A fake bass head, (n_frames, 13): per frame the bass heard at that time (a note or None for
    "no bass") at weight, the rest spread evenly. heard is (note, beats) at the default 120 BPM."""
    head = np.full((n_frames, 13), (1 - weight) / 12)
    end, k = 0.0, 0
    for note, n_beats in heard:
        end += n_beats * 0.5
        index = 0 if note is None else 1 + NOTES.index(note)
        while k < n_frames and k * HOP / SR < end:
            head[k, index] = weight
            k += 1
    return head


def _stub_model(monkeypatch, chord: str, heard: list[tuple[str | None, int]], weight: float):
    """The fake model hears one chord throughout and the bass head `heard`."""

    def recognize(y):
        n = 1 + len(y) // HOP
        scores = np.full((len(LABELS), n), -5.0)
        scores[LABELS.index(chord)] = 0.0
        return np.full(n, LABELS.index(chord)), scores, _head(heard, n, weight)

    monkeypatch.setattr(model, "recognize", recognize)
    monkeypatch.setattr(model, "version", lambda: "9.9")
    monkeypatch.setattr(model, "BASS_SUPPORT", 0.5)


def test_the_model_engine_runs_on_the_dsp_grid(synth, chord_at, tmp_path, monkeypatch) -> None:
    # The fake model hears other chords than the audio holds, so the chords come from it, the
    # grid from the DSP and the bass from the head (which says what the register holds).
    heard = [("A:min", 4), ("D:min", 4), ("G:7", 4), ("C:maj", 4)]
    runner_up = LABELS.index("E:min")

    def recognize(y):
        times = np.arange(1 + len(y) // HOP) * HOP / SR
        states = np.array([LABELS.index(chord_at(heard, t)) for t in times])
        scores = np.full((len(LABELS), len(times)), -5.0)
        scores[runner_up] = -1.0
        scores[states, np.arange(len(times))] = 0.0
        return states, scores, _head([("E", 4), ("F", 4), ("G", 4), ("C", 4)], len(times))

    monkeypatch.setattr(model, "recognize", recognize)
    monkeypatch.setattr(model, "version", lambda: "9.9")
    progression = [("C:maj", 4, 40), ("F:maj", 4, 41), ("G:maj", 4, 43), ("C:maj", 4, 36)]

    result = analyze(_write(tmp_path, synth(progression)), engine="model")

    json.dumps(result)
    segments = result["segments"]
    assert [s["chord"] for s in segments] == ["A:min", "D:min", "G:7", "C:maj"]
    assert [s["candidates"][1] for s in segments] == ["E:min"] * 4
    assert [s["bass"] for s in segments] == ["E", "F", "G", "C"]
    assert [s["inversion"] for s in segments] == ["second", "first", "root", "root"]
    assert result["generator"]["engine"] == {"name": "lv-chordia", "version": "9.9"}


def test_a_heard_7sus4_gets_its_numeral_and_inversion(
    synth, chord_at, tmp_path, monkeypatch
) -> None:
    # Whatever the DSP decides about calling a sus4(b7), the label reaches the timeline with its
    # harmony and its inversion: the fake model hears it, the DSP grid and bass place it.
    heard = [("D:maj", 4), ("A:sus4(b7)", 4), ("A:7", 4), ("D:maj", 4)]

    def recognize(y):
        times = np.arange(1 + len(y) // HOP) * HOP / SR
        states = np.array([LABELS.index(chord_at(heard, t)) for t in times])
        scores = np.full((len(LABELS), len(times)), -5.0)
        scores[states, np.arange(len(times))] = 0.0
        return states, scores, _head([("D", 4), ("G", 4), ("A", 4), ("D", 4)], len(times))

    monkeypatch.setattr(model, "recognize", recognize)
    monkeypatch.setattr(model, "version", lambda: "9.9")
    progression = [("D:maj", 4, 38), ("D:maj", 4, 43), ("D:maj", 4, 45), ("D:maj", 4, 38)]

    result = analyze(_write(tmp_path, synth(progression)), engine="model")

    segments = result["segments"]
    assert result["key"]["label"] == "D:maj"
    assert [s["chord"] for s in segments] == ["D:maj", "A:sus4(b7)", "A:7", "D:maj"]
    assert [s["bass"] for s in segments] == ["D", "G", "A", "D"]
    assert [s["inversion"] for s in segments] == ["root", "third", "root", "root"]
    assert [s["numeral"] for s in segments] == ["I", "V7sus4", "V7", "I"]
    assert (segments[1]["role"], segments[1]["function"]) == ("diatonic", "dominant")


def test_the_model_engine_keeps_a_held_slash_the_head_hears(synth, tmp_path, monkeypatch) -> None:
    _stub_model(monkeypatch, "D:maj", [("D", 4), ("E", 4)], 0.97)

    segments = analyze(
        _write(tmp_path, synth([("D:maj", 4, 38), ("D:maj", 4, 40)])), engine="model"
    )["segments"]

    assert [s["bass"] for s in segments] == ["D", "E"]
    assert [s["inversion"] for s in segments] == ["root", "non_chord"]


def test_the_model_engine_writes_the_root_over_a_non_chord_pick_the_head_rejects(
    synth, tmp_path, monkeypatch
) -> None:
    # The DSP picks D#2 under Bm7 (the recording's Bm7/D#); the head hears B.
    _stub_model(monkeypatch, "B:min7", [("B", 8)], 0.97)

    (only,) = analyze(_write(tmp_path, synth([("B:min7", 8, 39)])), engine="model")["segments"]

    assert only["bass"] == "B"
    assert only["inversion"] == "root"


def test_an_unreliable_non_chord_head_note_reads_root_position(
    synth, tmp_path, monkeypatch
) -> None:
    # Chord voiced above the register: no pick, so the head is the only candidate.
    clip = _write(tmp_path, synth([("B:min7", 8)], chord_midi=60))
    _stub_model(monkeypatch, "B:min7", [("D#", 8)], 0.4)

    (weak,) = analyze(clip, engine="model")["segments"]

    assert (weak["bass"], weak["inversion"]) == ("B", "root")

    _stub_model(monkeypatch, "B:min7", [("D#", 8)], 0.6)

    (strong,) = analyze(clip, engine="model")["segments"]

    assert (strong["bass"], strong["inversion"]) == ("D#", "non_chord")


def test_the_model_engine_writes_no_bass_when_the_head_hears_none(
    synth, tmp_path, monkeypatch
) -> None:
    _stub_model(monkeypatch, "B:min7", [(None, 8)], 0.97)

    clip = _write(tmp_path, synth([("B:min7", 8)], chord_midi=60))

    (only,) = analyze(clip, engine="model")["segments"]

    assert only["bass"] is None
    assert only["inversion"] is None


def test_no_beats_fails_before_the_model_loads(tmp_path, monkeypatch) -> None:
    def recognize(y):
        pytest.fail("the model ran on audio without beats")

    monkeypatch.setattr(model, "recognize", recognize)

    with pytest.raises(NoBeatsError):
        analyze(_write(tmp_path, np.zeros(4 * SR, dtype=np.float32)), engine="model")


def test_a_mix_like_clip_keeps_its_chords(mix, chord_at, tmp_path) -> None:
    progression = [("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4)]

    result = analyze(_write(tmp_path, mix(progression)))

    segments = result["segments"]
    beats = result["beats"]
    # Measured: the octave check decodes 3 changes here, none between the tracker's beats, so the
    # grid stays at 120 BPM (17 beats).
    assert abs(len(beats) - 16) <= 2, len(beats)
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
