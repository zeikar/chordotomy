from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mir_eval")

from chordotomy import evaluate  # noqa: E402

METRICS = ("root", "majmin", "sevenths", "tetrads", "majmin_inv")


def _score(ref, est, est_bass_missing=None):
    ref_i = np.array([[a, b] for a, b, _ in ref], dtype=float)
    est_i = np.array([[a, b] for a, b, _ in est], dtype=float)
    return evaluate.score(
        ref_i, [c for *_, c in ref], est_i, [c for *_, c in est], est_bass_missing
    )


def test_timeline_to_intervals() -> None:
    result = {
        "segments": [
            {"start_time": 0.0, "end_time": 1.0, "chord": "C:maj", "bass": "C"},
            {"start_time": 1.0, "end_time": 2.0, "chord": "C:maj", "bass": "E"},
            {"start_time": 2.0, "end_time": 3.5, "chord": "N", "bass": None},
        ]
    }

    intervals, labels = evaluate.timeline_to_intervals(result)

    assert intervals.tolist() == [[0.0, 1.0], [1.0, 2.0], [2.0, 3.5]]
    assert labels == ["C:maj", "C:maj/3", "N"]


def test_tiny_aam_reference() -> None:
    text = (
        "@RELATION beatinfo\n"
        "@ATTRIBUTE start NUMERIC\n"
        "% comment\n"
        "\n"
        "0.5,1,1,'C#maj'\n"
        "1.0,1,2,'N.C.'\n"
        "1.5,1,3,'Amin'\n"
        "2.0,1,4,'Amin'\n"
    )

    intervals, labels = evaluate.tiny_aam_reference(text, 3.0)

    assert intervals.tolist() == [[0.5, 1.0], [1.0, 1.5], [1.5, 2.0], [2.0, 3.0]]
    assert labels == ["C#:maj", "N", "A:min", "A:min"]


def test_tiny_aam_reference_rejects_an_unknown_quality() -> None:
    with pytest.raises(ValueError, match="Cdim"):
        evaluate.tiny_aam_reference("0.0,1,1,'Cdim'\n", 1.0)


def _jams(*annotations):
    return {
        "annotations": [
            {
                "namespace": "chord",
                "annotation_metadata": {"data_source": source},
                "data": [{"time": t, "duration": d, "value": v} for t, d, v in data],
            }
            for source, data in annotations
        ]
    }


def test_guitarset_reference_picks_the_performed_annotation() -> None:
    jams = _jams(
        ("", [(0.0, 2.0, "C:maj")]),
        ("Semi-automatic (v2)", [(0.0, 1.0, "C:maj/1"), (1.0, 1.5, "G:7")]),
    )

    intervals, labels = evaluate.guitarset_reference(jams)

    assert intervals.tolist() == [[0.0, 1.0], [1.0, 2.5]]
    assert labels == ["C:maj/1", "G:7"]


def test_guitarset_reference_needs_exactly_one_performed_annotation() -> None:
    with pytest.raises(ValueError, match="Semi-automatic"):
        evaluate.guitarset_reference(_jams(("", [(0.0, 2.0, "C:maj")])))


def test_identical_inputs_score_one() -> None:
    track = _score([(0, 1, "C:maj"), (1, 2, "G:7")], [(0, 1, "C:maj"), (1, 2, "G:7")])

    for metric in METRICS:
        comparisons, durations = track[metric]
        assert comparisons.tolist() == [1.0, 1.0]
        assert durations.tolist() == [1.0, 1.0]
    assert track["duration"] == 2.0
    assert track["n_est"] == track["n_ref"] == 0.0


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

    rows = evaluate.summarise({"short": short, "long": long})

    assert rows["short"]["majmin"] == 1.0
    assert rows["long"]["majmin"] == 0.0
    assert rows["overall"]["majmin"] == pytest.approx(0.25)
    assert rows["overall"]["duration"] == 4.0
    assert rows["overall"]["n_est"] == 0.0


def test_a_checkout_downloads_into_its_gitignored_datasets_dir(monkeypatch) -> None:
    monkeypatch.setattr(evaluate, "CACHE_DIR", None)

    path = evaluate.cache_dir()

    assert path == Path(__file__).resolve().parents[1] / "datasets"
