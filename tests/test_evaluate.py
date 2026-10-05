import warnings
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mir_eval")

from chordotomy import evaluate  # noqa: E402
from chordotomy.chords import inversion  # noqa: E402

METRICS = ("root", "majmin", "sevenths", "tetrads", "majmin_inv")
# Half-second beats over 10 s, past BEAT_MIN_TIME, so mir_eval has beats left to score.
BEATS = np.arange(0.0, 10.0, 0.5)


def _score(ref, est, est_bass_missing=None):
    ref_i = np.array([[a, b] for a, b, _ in ref], dtype=float)
    est_i = np.array([[a, b] for a, b, _ in est], dtype=float)
    track = evaluate.score(
        ref_i, [c for *_, c in ref], est_i, [c for *_, c in est], est_bass_missing
    )
    # run() merges the beat and bass columns into every track, and summarise reads them.
    labels = [next((c for lo, hi, c in est if lo <= t + 0.25 < hi), "N") for t in BEATS]
    result = {
        "beats": BEATS.tolist(),
        "source": {"duration": 10.0},
        "segments": [
            {
                "start_beat": i,
                "end_beat": i + 1,
                "start_time": t,
                "end_time": t + 0.5,
                "chord": c,
                "bass": None if c == "N" else c.split(":")[0],
                "inversion": None if c == "N" else "root",
            }
            for i, (t, c) in enumerate(zip(BEATS, labels, strict=True))
        ],
    }
    reference = evaluate.Reference(ref_i, [c for *_, c in ref], BEATS)
    return {
        **track,
        **evaluate.beat_metrics(BEATS, BEATS),
        **evaluate.bass_metrics(result, reference),
    }


def test_timeline_to_intervals() -> None:
    result = {
        "segments": [
            {"start_time": 0.0, "end_time": 1.0, "chord": "C:maj", "bass": "C"},
            {"start_time": 1.0, "end_time": 2.0, "chord": "C:maj", "bass": "E"},
            {"start_time": 2.0, "end_time": 3.5, "chord": "N", "bass": None},
            {"start_time": 3.5, "end_time": 4.5, "chord": "A:sus4(b7)", "bass": "G"},
        ]
    }

    intervals, labels = evaluate.timeline_to_intervals(result)

    assert intervals.tolist() == [[0.0, 1.0], [1.0, 2.0], [2.0, 3.5], [3.5, 4.5]]
    assert labels == ["C:maj", "C:maj/3", "N", "A:sus4(b7)/b7"]


ARFF = (
    "@RELATION beatinfo\n"
    "@ATTRIBUTE start NUMERIC\n"
    "% comment\n"
    "\n"
    "0.5,1,1,'C#maj'\n"
    "1.0,1,2,'N.C.'\n"
    "1.5,1,3,'Amin'\n"
    "2.0,1,4,'Amin'\n"
)


def test_tiny_aam_reference() -> None:
    reference = evaluate.tiny_aam_reference(ARFF, 3.0)

    assert reference.intervals.tolist() == [
        [0.5, 1.0],
        [1.0, 1.5],
        [1.5, 2.0],
        [2.0, 2.5],
        [2.5, 3.0],
    ]
    assert reference.labels == ["C#:maj", "N", "A:min", "A:min", "N"]
    assert reference.beats.tolist() == [0.5, 1.0, 1.5, 2.0]


def test_tiny_aam_reference_caps_the_last_beat_at_the_duration() -> None:
    reference = evaluate.tiny_aam_reference(ARFF, 2.3)

    assert reference.intervals.tolist()[-1] == [2.0, 2.3]
    assert reference.labels[-1] == "A:min"


def test_tiny_aam_reference_ends_the_last_beat_after_the_final_gap() -> None:
    arff = "0.0,1,1,'Cmaj'\n1.0,1,2,'Cmaj'\n2.0,1,3,'Cmaj'\n2.25,1,4,'Cmaj'\n"
    reference = evaluate.tiny_aam_reference(arff, 5.0)

    assert reference.intervals.tolist()[-2:] == [[2.25, 2.5], [2.5, 5.0]]
    assert reference.labels[-1] == "N"


def test_tiny_aam_reference_with_one_beat_runs_it_to_the_end() -> None:
    reference = evaluate.tiny_aam_reference("0.5,1,1,'Cmaj'\n", 3.0)

    assert reference.intervals.tolist() == [[0.5, 3.0]]
    assert reference.labels == ["C:maj"]


def test_tiny_aam_reference_rejects_an_unknown_quality() -> None:
    with pytest.raises(ValueError, match="Cdim"):
        evaluate.tiny_aam_reference("0.0,1,1,'Cdim'\n", 1.0)


def _jams(*annotations, beats=(0.0, 0.5, 1.0, 1.5)):
    chords = [
        {
            "namespace": "chord",
            "annotation_metadata": {"data_source": source},
            "data": [{"time": t, "duration": d, "value": v} for t, d, v in data],
        }
        for source, data in annotations
    ]
    if beats is None:
        return {"annotations": chords}
    beat = {
        "namespace": "beat_position",
        "annotation_metadata": {"data_source": ""},
        "data": [
            {"time": t, "duration": 0.0, "value": {"position": i % 4 + 1}}
            for i, t in enumerate(beats)
        ],
    }
    return {"annotations": [*chords, beat]}


def test_guitarset_reference_picks_the_performed_annotation() -> None:
    jams = _jams(
        ("", [(0.0, 2.0, "C:maj")]),
        ("Semi-automatic (v2)", [(0.0, 1.0, "C:maj/1"), (1.0, 1.5, "G:7")]),
        beats=(0.0, 0.6, 1.2, 1.8),
    )

    reference = evaluate.guitarset_reference(jams)

    assert reference.intervals.tolist() == [[0.0, 1.0], [1.0, 2.5]]
    assert reference.labels == ["C:maj/1", "G:7"]
    assert reference.beats.tolist() == [0.0, 0.6, 1.2, 1.8]


def test_guitarset_reference_needs_exactly_one_performed_annotation() -> None:
    with pytest.raises(ValueError, match="Semi-automatic"):
        evaluate.guitarset_reference(_jams(("", [(0.0, 2.0, "C:maj")])))


def test_guitarset_reference_needs_exactly_one_beat_annotation() -> None:
    jams = _jams(("Semi-automatic", [(0.0, 2.0, "C:maj")]), beats=None)

    with pytest.raises(ValueError, match="beat_position"):
        evaluate.guitarset_reference(jams)


def test_beat_metrics() -> None:
    # Ends on the reference's last beat, where mir_eval's doubled reference ends too.
    double = evaluate.beat_metrics(BEATS, np.arange(0.0, BEATS[-1] + 0.25, 0.25))
    early = np.where(BEATS < evaluate.BEAT_MIN_TIME, BEATS + 0.2, BEATS)

    assert evaluate.beat_metrics(BEATS, BEATS) == {
        "beat_f": 1.0,
        "cmlt": 1.0,
        "amlt": 1.0,
        "period_ratio": 1.0,
    }
    assert double["period_ratio"] == 0.5
    assert double["amlt"] == 1.0
    assert double["cmlt"] == 0.0
    assert evaluate.beat_metrics(BEATS, early)["beat_f"] == 1.0


def test_a_clip_shorter_than_the_beat_trim_has_no_beat_scores() -> None:
    beats = np.arange(0.0, 4.0, 0.5)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        scores = evaluate.beat_metrics(beats, beats)

    assert np.isnan([scores["beat_f"], scores["cmlt"], scores["amlt"]]).all()
    assert scores["period_ratio"] == 1.0
    assert np.isnan(evaluate.beat_metrics(np.array([1.0]), beats)["period_ratio"])


def test_identical_inputs_score_one() -> None:
    track = _score([(0, 1, "C:maj"), (1, 2, "G:7")], [(0, 1, "C:maj"), (1, 2, "G:7")])

    for metric in METRICS:
        comparisons, durations = track[metric]
        assert comparisons.tolist() == [1.0, 1.0]
        assert durations.tolist() == [1.0, 1.0]
    assert track["duration"] == 2.0
    assert track["n_est"] == track["n_ref"] == track["n_hit"] == 0.0


def test_power_chord_reference_is_excluded_from_majmin() -> None:
    track = _score([(0, 1, "C:(1,5)")], [(0, 1, "C:maj")])

    assert track["majmin"][0].tolist() == [-1.0]
    assert track["root"][0].tolist() == [1.0]


def test_tetrads_needs_the_full_pitch_set() -> None:
    def scores(ref, est):
        track = _score([(0, 1, ref)], [(0, 1, est)])
        return [track[m][0].tolist() for m in ("root", "majmin", "sevenths", "tetrads")]

    assert scores("C:min", "C:hdim7") == [[1.0], [0.0], [0.0], [0.0]]
    assert scores("C:hdim7", "C:min") == [[1.0], [-1.0], [-1.0], [0.0]]
    assert scores("C:sus4", "C:sus4") == [[1.0], [-1.0], [-1.0], [1.0]]
    assert scores("A:sus4(b7)", "A:sus4(b7)") == [[1.0], [-1.0], [-1.0], [1.0]]
    assert scores("A:7", "A:sus4(b7)") == [[1.0], [0.0], [0.0], [0.0]]
    assert scores("C:maj7", "C:maj7") == [[1.0], [1.0], [1.0], [1.0]]
    assert scores("C:min6", "C:min") == [[1.0], [1.0], [-1.0], [0.0]]


def test_seventh_reference_counts_in_majmin_but_not_sevenths() -> None:
    track = _score([(0, 1, "C:maj7")], [(0, 1, "C:maj")])

    assert track["majmin"][0].tolist() == [1.0]
    assert track["sevenths"][0].tolist() == [0.0]


def test_inversion_fails_only_majmin_inv() -> None:
    track = _score([(0, 1, "C:maj/3")], [(0, 1, "C:maj")])

    assert [track[m][0].tolist() for m in METRICS] == [[1.0], [1.0], [1.0], [1.0], [0.0]]


def test_missing_bass_flags_follow_the_segments() -> None:
    result = {
        "segments": [
            {"start_time": 0.0, "end_time": 1.0, "chord": "C:maj", "bass": None},
            {"start_time": 1.0, "end_time": 2.0, "chord": "C:maj", "bass": "C"},
            {"start_time": 2.0, "end_time": 3.0, "chord": "N", "bass": None},
        ]
    }

    assert evaluate.bass_missing(result) == [True, False, False]


def test_missing_bass_misses_an_inverted_reference_only_in_majmin_inv() -> None:
    track = _score([(0, 1, "C:maj/3")], [(0, 1, "C:maj")], [True])

    assert [track[m][0].tolist() for m in METRICS] == [[1.0], [1.0], [1.0], [1.0], [0.0]]


def test_root_bass_and_correct_bass_against_an_inverted_reference() -> None:
    root = _score([(0, 1, "C:maj/3")], [(0, 1, "C:maj")], [False])
    third = _score([(0, 1, "C:maj/3")], [(0, 1, "C:maj/3")], [False])

    assert root["majmin_inv"][0].tolist() == [0.0]
    assert third["majmin_inv"][0].tolist() == [1.0]


def test_missing_bass_misses_a_root_position_reference_too() -> None:
    track = _score([(0, 1, "C:maj")], [(0, 1, "C:maj")], [True])

    assert [track[m][0].tolist() for m in METRICS] == [[1.0], [1.0], [1.0], [1.0], [0.0]]


def test_missing_bass_keeps_an_excluded_interval_excluded() -> None:
    track = _score([(0, 1, "C:(1,5)/5")], [(0, 1, "C:maj")], [True])

    assert track["majmin_inv"][0].tolist() == [-1.0]


def test_missing_bass_survives_padding_and_merging() -> None:
    track = _score(
        [(0, 1, "C:maj"), (1, 2, "C:maj/5"), (2, 3, "C:maj/5")],
        [(0.5, 2.5, "C:maj")],
        [True],
    )

    assert track["majmin_inv"][0].tolist() == [0.0, 0.0, 0.0, 0.0, 0.0]
    assert track["majmin"][0].tolist() == [0.0, 1.0, 1.0, 1.0, 0.0]


def test_estimate_is_padded_with_n_to_the_reference_span() -> None:
    track = _score([(0, 2, "C:maj"), (2, 4, "N")], [(0, 1, "C:maj")])

    assert track["duration"] == 4.0
    assert track["n_est"] == 0.75
    assert track["n_ref"] == 0.5


def test_summarise_weights_overall_by_duration() -> None:
    short = _score([(0, 1, "C:maj")], [(0, 1, "C:maj")])
    long = _score([(0, 3, "C:maj")], [(0, 3, "G:maj")])
    # N in both: estimated on [0, 1) and [3.5, 4), referenced on [2, 4); they share [3.5, 4).
    gaps = _score(
        [(0, 2, "C:maj"), (2, 4, "N")],
        [(0, 1, "N"), (1, 3.5, "C:maj"), (3.5, 4, "N")],
    )
    for track, beat_f, ratio in ((short, 1.0, 1.0), (long, 0.0, 2.0), (gaps, 0.5, 0.5)):
        track.update(beat_f=beat_f, period_ratio=ratio)

    rows = evaluate.summarise({"short": short, "long": long, "gaps": gaps})

    assert rows["short"]["majmin"] == 1.0
    assert rows["long"]["majmin"] == 0.0
    assert rows["gaps"]["majmin"] == pytest.approx(0.375)
    assert rows["overall"]["majmin"] == pytest.approx(0.3125)
    assert rows["overall"]["duration"] == 8.0
    assert rows["overall"]["n_est"] == pytest.approx(0.1875)
    assert rows["overall"]["n_precision"] == pytest.approx(1 / 3)
    assert rows["overall"]["n_recall"] == pytest.approx(0.25)
    assert np.isnan(rows["short"]["n_precision"])
    assert np.isnan(rows["short"]["n_recall"])
    assert rows["overall"]["beat_f"] == pytest.approx(0.375)
    assert rows["overall"]["period_ratio"] == 1.0


def _bass_result(*segments):
    """A timeline of half-second beats over 5 s from (start_beat, end_beat, chord, bass)."""
    beats = np.arange(0.0, 5.0, 0.5)
    return {
        "beats": beats.tolist(),
        "source": {"duration": 5.0},
        "segments": [
            {
                "start_beat": a,
                "end_beat": b,
                "start_time": a / 2,
                "end_time": b / 2,
                "chord": chord,
                "bass": bass,
                "inversion": None if chord == "N" or bass is None else inversion(chord, bass),
            }
            for a, b, chord, bass in segments
        ],
    }


def _bass_reference(*spans):
    """A reference from (start, end, label) spans."""
    return evaluate.Reference(
        np.array([[a, b] for a, b, _ in spans], dtype=float),
        [label for *_, label in spans],
        np.arange(0.0, 5.0, 0.5),
    )


def test_bass_metrics_scores_each_beat_against_the_reference_bass() -> None:
    result = _bass_result(
        (0, 1, "C:maj", "C"),
        (1, 3, "C:maj", "E"),
        (3, 5, "G:7", "D"),
        (5, 7, "N", None),
        (7, 8, "C:maj", None),
        (8, 10, "C:maj", "E"),
    )
    reference = _bass_reference(
        (0.0, 1.0, "C:maj"),
        (1.0, 1.5, "C:maj/3"),
        (1.5, 2.0, "C:maj/2"),
        (2.0, 2.5, "G:7/5"),
        (2.5, 3.0, "C:maj/5"),
        (3.0, 3.5, "N"),
        (3.5, 4.0, "C:maj/5"),
        (4.0, 4.5, "N"),
        (4.5, 5.0, "C:maj/5"),
    )

    bass = evaluate.bass_metrics(result, reference)

    # Beats 0 to 4 and 7 and 9 have an estimate chord over a reference chord; the E over the
    # root-position C, the missing bass and the E over a G miss, the D over C:maj/2's D hits.
    assert bass["bass_ref"] == (2.0, 3.5)
    # The estimate inverts beats 1 to 4, 8 and 9. Only the E over C:maj/3 and the D over G:7/5
    # hit: the E over a root-position C and the D over C:maj/2 (off the chord) miss, as do the
    # E over a reference N and over a reference G.
    assert bass["inv_prec"] == (1.0, 3.0)
    # The reference inverts beats 2, 4, 5, 7 and 9. The estimate N at beat 5, the missing bass
    # at 7 and the wrong bass at 9 are misses; C:maj/2's D is not an inversion, so beat 3 is out.
    assert bass["inv_rec"] == (1.0, 2.5)
    assert bass["nonchord"] == 0.0


def test_bass_metrics_without_a_reference_inversion() -> None:
    result = _bass_result(
        (0, 4, "C:maj", "C"),
        (4, 7, "C:maj", "E"),
        (7, 10, "C:maj", "D"),
    )

    bass = evaluate.bass_metrics(result, _bass_reference((0.0, 5.0, "C:maj")))

    assert bass["bass_ref"] == (2.0, 5.0)
    assert bass["inv_rec"] == (0.0, 0.0)
    # Only the E is a chord-tone inversion; the D is outside the chord and not counted.
    assert bass["inv_prec"] == (0.0, 1.5)
    assert bass["nonchord"] == pytest.approx(0.3)


def test_bass_metrics_skips_an_x_or_a_gap_and_runs_the_last_beat_to_the_end() -> None:
    result = {
        "beats": [0.0, 1.0, 1.5, 2.0],
        "source": {"duration": 4.0},
        "segments": [
            {
                "start_beat": 0,
                "end_beat": 4,
                "start_time": 0.0,
                "end_time": 4.0,
                "chord": "C:maj",
                "bass": "C",
                "inversion": "root",
            }
        ],
    }
    # Midpoints 0.5 (X), 1.25 (C), 1.75 (in the gap) and 3.0 (C, the last beat lasting 2.0 s).
    reference = _bass_reference((0.0, 1.0, "X"), (1.0, 1.4, "C:maj"), (2.5, 4.0, "C:maj"))

    bass = evaluate.bass_metrics(result, reference)

    assert bass["bass_ref"] == (2.5, 2.5)


def test_summarise_weights_the_bass_columns_by_their_denominators() -> None:
    short = _score([(0, 2, "C:maj")], [(0, 2, "C:maj")])
    long = _score([(0, 8, "C:maj")], [(0, 8, "C:maj")])
    short.update(bass_ref=(1.0, 1.0), inv_prec=(0.0, 0.0), inv_rec=(1.0, 2.0), nonchord=0.5)
    long.update(bass_ref=(1.0, 4.0), inv_prec=(0.0, 0.0), inv_rec=(0.0, 0.0), nonchord=0.0)

    rows = evaluate.summarise({"short": short, "long": long})

    assert rows["short"]["bass_ref"] == 1.0
    assert rows["long"]["bass_ref"] == 0.25
    assert rows["overall"]["bass_ref"] == pytest.approx(2 / 5)
    assert rows["overall"]["inv_rec"] == 0.5
    assert np.isnan(rows["overall"]["inv_prec"])
    assert np.isnan(rows["long"]["inv_rec"])
    # Weighted by duration like n_est: (0.5 * 2 + 0 * 8) / 10.
    assert rows["overall"]["nonchord"] == pytest.approx(0.1)


def test_summarise_leaves_tracks_without_beat_scores_out_of_the_beat_overall() -> None:
    short = evaluate.beat_metrics(np.arange(0.0, 4.0, 0.5), np.arange(0.0, 4.0, 0.25))
    short = {**_score([(0, 1, "C:maj")], [(0, 1, "C:maj")]), **short}
    short["period_ratio"] = float("nan")
    scored = _score([(0, 3, "C:maj")], [(0, 3, "C:maj")])
    scored.update(beat_f=0.5, cmlt=0.25, amlt=0.75, period_ratio=1.5)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        overall = evaluate.summarise({"short": short, "scored": scored})["overall"]
        nothing = evaluate.summarise({"short": short})["overall"]

    assert np.isnan(short["beat_f"])
    assert (overall["beat_f"], overall["cmlt"], overall["amlt"]) == (0.5, 0.25, 0.75)
    assert overall["period_ratio"] == 1.5
    assert np.isnan([nothing[k] for k in ("beat_f", "cmlt", "amlt", "period_ratio")]).all()


def test_a_checkout_downloads_into_its_gitignored_datasets_dir(monkeypatch) -> None:
    monkeypatch.setattr(evaluate, "CACHE_DIR", None)

    path = evaluate.cache_dir()

    assert path == Path(__file__).resolve().parents[1] / "datasets"


def test_a_chart_reference_holds_chords_only_and_an_unwritten_silence_is_unknown() -> None:
    def segment(start, end, chord, bass, edited):
        return {
            "start_time": start,
            "end_time": end,
            "chord": chord,
            "bass": bass,
            "edited": edited,
        }

    reference = evaluate._chord_reference(
        {
            "segments": [
                segment(0.0, 1.0, "N", None, False),  # the analyzer's, unaligned or agreed
                segment(1.0, 2.0, "C:maj", "E", False),  # its bass is not a chart's word
                segment(2.0, 3.0, "N", None, True),  # someone wrote this rest
            ]
        }
    )
    assert reference.labels == ["X", "C:maj", "N"]
    np.testing.assert_array_equal(reference.intervals, [[0, 1], [1, 2], [2, 3]])
    assert len(reference.beats) == 0
