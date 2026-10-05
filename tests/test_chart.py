import pytest

from chordotomy.chart import Chart, ChartError, align, parse, parse_chord
from chordotomy.chords import inversion


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("C", ("C:maj", None)),
        ("Am", ("A:min", None)),
        ("C#m7", ("C#:min7", None)),
        ("F#m7-5", ("F#:hdim7", None)),
        ("Bm7(b5)", ("B:hdim7", None)),
        ("Bø", ("B:hdim7", None)),
        ("EM7", ("E:maj7", None)),
        ("E△7", ("E:maj7", None)),
        ("Aadd9", ("A:maj(9)", None)),
        ("A(9)", ("A:maj(9)", None)),
        ("Am(9)", ("A:min(9)", None)),
        ("A7sus4", ("A:sus4(b7)", None)),
        ("Bdim7", ("B:dim7", None)),
        ("B°", ("B:dim", None)),
        ("C+", ("C:aug", None)),
        ("D/F#", ("D:maj", "F#")),
        ("Gm7/F", ("G:min7", "F")),
        ("B♭", ("A#:maj", None)),
        ("E♭m", ("D#:min", None)),
        ("Db7", ("C#:7", None)),
        ("Cb", ("B:maj", None)),
        ("N.C.", ("N", None)),
        # Past the vocabulary, as the model engine reduces: the tensions go, a sixth is its triad.
        ("E7(b9)", ("E:7", None)),
        ("AM7(9)", ("A:maj7", None)),
        ("F#m11", ("F#:min7", None)),
        ("A6", ("A:maj", None)),
        ("C6/9", ("C:maj", None)),
        ("Am6", ("A:min6", None)),
    ],
)
def test_a_chart_chord_reads_as_a_vocabulary_label(token, expected) -> None:
    assert parse_chord(token) == expected


@pytest.mark.parametrize("token", ["X", "H", "C7(9", "Cfoo", "D/H", "x2"])
def test_anything_else_is_refused(token) -> None:
    with pytest.raises(ValueError):
        parse_chord(token)


def test_a_chart_file_skips_comments_and_bar_lines() -> None:
    text = "# Verse\n| E  B | A  B |\nC#m G#m/B  A  B\n"
    assert parse(text).capo == 0
    assert [label for label, _ in parse(text).chords] == [
        "E:maj", "B:maj", "A:maj", "B:maj", "C#:min", "G#:min", "A:maj", "B:maj"
    ]  # fmt: skip
    with pytest.raises(ChartError, match="line 2: 'Verse' is not a chord"):
        parse("E B\nVerse A B\n")


def _segment(start: int, end: int, chord: str, bass: str | None = "root") -> dict:
    bass = (chord.split(":")[0] if chord != "N" else None) if bass == "root" else bass
    return {
        "start_beat": start,
        "end_beat": end,
        "start_time": start * 0.5,
        "end_time": end * 0.5,
        "chord": chord,
        "candidates": [chord, "C:maj", "G:maj"],
        "bass": bass,
        "inversion": inversion(chord, bass),
        "numeral": None,
        "role": None,
        "function": None,
        "target": None,
        "edited": False,
    }


def _timeline(*spans: tuple[str, int] | tuple[str, int, str | None]) -> dict:
    segments, beat = [], 0
    for chord, beats, *bass in spans:
        segments.append(_segment(beat, beat + beats, chord, *bass))
        beat += beats
    key = {"label": "C:maj", "source": "estimated", "candidates": ["C:maj"]}
    return {
        "schema_version": 11,
        "global_key": key,
        "key_regions": [{"start_beat": 0, "end_beat": beat, "label": "C:maj"}],
        "beats": [i * 0.5 for i in range(beat)],
        "segments": segments,
    }


def _chords(timeline: dict) -> list[tuple[str, str | None]]:
    return [(s["chord"], s["bass"]) for s in timeline["segments"]]


def test_a_capo_line_gives_the_capo() -> None:
    assert parse("Capo 2\nC G\n") == Chart([("C:maj", None), ("G:maj", None)], 2)
    assert parse("capo: 14\nC\n").capo == 2


def test_a_chart_that_agrees_changes_nothing() -> None:
    heard = _timeline(("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4))
    aligned = align(heard, parse("C Am F G7"))
    assert (aligned.differ, aligned.passed, aligned.fits) == (0, 0, 0)
    assert aligned.timeline["segments"] == [{**s, **a} for s, a in zip(heard["segments"], [
        {"numeral": "I", "role": "diatonic", "function": "tonic", "target": None},
        {"numeral": "vi", "role": "diatonic", "function": "tonic", "target": None},
        {"numeral": "IV", "role": "diatonic", "function": "predominant", "target": None},
        {"numeral": "V7", "role": "diatonic", "function": "dominant", "target": None},
    ], strict=True)]  # fmt: skip


def test_the_chart_names_what_the_analysis_simplified() -> None:
    heard = _timeline(("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:maj", 4))
    aligned = align(heard, parse("Cadd9 Am7 F G7"))
    segments = aligned.timeline["segments"]
    assert _chords(aligned.timeline) == [
        ("C:maj(9)", "C"), ("A:min7", "A"), ("F:maj", "F"), ("G:7", "G")
    ]  # fmt: skip
    assert aligned.differ == 3
    assert [s["edited"] for s in segments] == [True, True, False, True]
    # The analyzer's reading stays on offer, first among the candidates.
    assert segments[0]["candidates"][0] == "C:maj"
    assert [s["numeral"] for s in segments] == ["Iadd9", "vi7", "IV", "V7"]


def test_a_chart_chord_may_span_runs_the_analysis_split() -> None:
    # The analysis hears the chart's Am7 as Am, then as C without its A.
    heard = _timeline(("C:maj", 4), ("A:min", 2), ("C:maj", 2), ("F:maj", 4), ("G:maj", 4))
    aligned = align(heard, parse("C Am7 F G"))
    assert _chords(aligned.timeline) == [
        ("C:maj", "C"), ("A:min7", "A"), ("A:min7", "C"), ("F:maj", "F"), ("G:maj", "G")
    ]  # fmt: skip
    # C is the third of Am7, so the chart, silent on the bass, keeps it: Am7/C.
    assert (aligned.differ, aligned.passed) == (2, 0)


def test_a_chart_chord_the_analysis_merged_is_passed_over() -> None:
    # A quick Dm the analysis did not hear: passing it costs less than calling the G a Dm.
    heard = _timeline(("C:maj", 4), ("G:maj", 4))
    aligned = align(heard, parse("C Dm G"))
    assert _chords(aligned.timeline) == [("C:maj", "C"), ("G:maj", "G")]
    assert (aligned.differ, aligned.passed) == (0, 1)


def test_a_chart_without_a_slash_puts_no_added_tone_in_the_bass() -> None:
    # The analyzer's A under a chart's Gadd9 would be the added ninth: the chart says G.
    heard = _timeline(("G:maj", 4), ("A:maj", 4), ("C:maj", 4, "E"))
    aligned = align(heard, parse("G Gadd9 C7"))
    assert _chords(aligned.timeline) == [("G:maj", "G"), ("G:maj(9)", "G"), ("C:7", "E")]


def test_the_chart_bass_and_the_analyzers() -> None:
    heard = _timeline(("G:maj", 4), ("D:maj", 4, "D"), ("E:min", 4), ("D:maj", 4, "D"))
    aligned = align(heard, parse("G D/F# Em G")).timeline
    # A slash is the chart's word on the bass; a chord without one keeps a bass it holds (D under
    # G), so the chart's G over the analysis's D reads as G/D.
    assert _chords(aligned) == [("G:maj", "G"), ("D:maj", "F#"), ("E:min", "E"), ("G:maj", "D")]
    assert [s["inversion"] for s in aligned["segments"]] == ["root", "first", "root", "second"]


def test_a_chart_for_a_capo_is_moved_up_by_its_capo() -> None:
    # Written for a capo on 2: the chords sound two semitones above the chart.
    heard = _timeline(("D:maj", 4), ("B:min", 4), ("G:maj", 4), ("A:maj", 4))
    aligned = align(heard, parse("capo 2\nC Am F G/B"))
    assert _chords(aligned.timeline)[3] == ("A:maj", "C#")
    assert (aligned.differ, aligned.fits) == (1, 2)


def test_without_its_capo_line_a_chart_is_not_moved_but_says_where_it_fits() -> None:
    # An analysis two semitones off throughout would match a moved chart and hide its error, so
    # the chart is taken as written and only the fit is reported.
    heard = _timeline(("D:maj", 4), ("B:min", 4), ("G:maj", 4), ("A:maj", 4))
    aligned = align(heard, parse("C Am F G"))
    # As written, only the chart's G meets the recording's G: the F is passed over, the rest differ.
    assert (aligned.differ, aligned.passed, aligned.fits) == (3, 1, 2)


def test_silence_takes_a_charted_break_and_is_otherwise_left_unaligned() -> None:
    heard = _timeline(("N", 2, None), ("C:maj", 4), ("N", 2, None), ("G:maj", 4))
    aligned = align(heard, parse("C N.C. G"))
    assert _chords(aligned.timeline) == [("N", None), ("C:maj", "C"), ("N", None), ("G:maj", "G")]
    assert (aligned.differ, aligned.passed) == (0, 0)


def test_a_chord_in_a_charted_break_shows() -> None:
    # The chart rests where the analysis hears a chord: the N.C. is not passed over for free.
    heard = _timeline(("C:maj", 4), ("A:min", 4), ("G:maj", 4))
    aligned = align(heard, parse("C N.C. G"))
    assert _chords(aligned.timeline) == [("C:maj", "C"), ("N", None), ("G:maj", "G")]
    assert aligned.differ == 1


def test_an_empty_chart_is_refused() -> None:
    with pytest.raises(ChartError, match="no chords"):
        align(_timeline(("C:maj", 4)), Chart([], 0))
