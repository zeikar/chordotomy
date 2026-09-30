import json
from itertools import pairwise

import numpy as np
import pytest

from chordotomy.chords import LABELS, inversion, match, pick_bass, segment, smooth

# Literal music-theory ground truth, deliberately not imported from the module.
ROOT_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
INTERVALS = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10)}


def test_vocabulary() -> None:
    assert len(LABELS) == 37
    assert LABELS[0] == "C:maj"
    assert LABELS[-1] == "N"
    assert "F#:7" in LABELS
    assert "A#:min" in LABELS
    assert len(set(LABELS)) == len(LABELS)


def test_match_ranks_ideal_chroma_first() -> None:
    names = []
    columns = []
    for root, root_name in enumerate(ROOT_NAMES):
        for quality, intervals in INTERVALS.items():
            column = np.zeros(12)
            column[[(root + i) % 12 for i in intervals]] = 1.0
            names.append(f"{root_name}:{quality}")
            columns.append(column)
    chroma = np.stack(columns, axis=1)

    sims = match(chroma)

    assert sims.shape == (37, 36)
    assert sims.min() >= 0.0
    assert sims.max() <= 1.0
    assert [LABELS[i] for i in sims.argmax(axis=0)] == names


def test_silent_and_flat_columns_are_no_chord() -> None:
    chroma = np.stack([np.zeros(12), np.ones(12)], axis=1)

    sims = match(chroma)

    assert list(sims.argmax(axis=0)) == [LABELS.index("N")] * 2


def _sims(overrides: dict[int, dict[str, float]], n: int = 6) -> np.ndarray:
    """(37, n) similarities: 0.6 everywhere, C:maj 0.95 / C:7 0.85 unless overridden per beat."""
    sims = np.full((len(LABELS), n), 0.6)
    sims[LABELS.index("C:maj")] = 0.95
    sims[LABELS.index("C:7")] = 0.85
    for beat, values in overrides.items():
        for label, value in values.items():
            sims[LABELS.index(label), beat] = value
    return sims


def _labels(sims: np.ndarray) -> list[str]:
    return [LABELS[i] for i in smooth(sims)]


def test_smooth_suppresses_one_beat_flicker_to_sibling() -> None:
    sims = _sims({1: {"C:maj": 0.88, "C:7": 0.90}})

    assert _labels(sims) == ["C:maj"] * 6


def test_smooth_suppresses_one_beat_sibling_change() -> None:
    sims = _sims({2: {"C:maj": 0.85, "C:7": 0.95}})

    assert _labels(sims) == ["C:maj"] * 6


def test_smooth_keeps_two_beat_sibling_change() -> None:
    sims = _sims({2: {"C:maj": 0.85, "C:7": 0.95}, 3: {"C:maj": 0.85, "C:7": 0.95}})

    assert _labels(sims) == ["C:maj", "C:maj", "C:7", "C:7", "C:maj", "C:maj"]


def test_smooth_keeps_one_beat_distant_change() -> None:
    sims = _sims({2: {"C:maj": 0.65, "F:maj": 0.95}})

    assert _labels(sims) == ["C:maj", "C:maj", "F:maj", "C:maj", "C:maj", "C:maj"]


def _states(*labels: str) -> np.ndarray:
    # uint16, as librosa.sequence.viterbi returns it.
    return np.array([LABELS.index(label) for label in labels], dtype=np.uint16)


def test_segment_merges_runs_and_tiles_beats() -> None:
    states = _states("C:maj", "C:maj", "C:min", "C:min", "C:min", "N")

    segments = segment(states, _sims({}), np.zeros((84, 6)))

    assert [(s["start_beat"], s["end_beat"], s["chord"]) for s in segments] == [
        (0, 2, "C:maj"),
        (2, 5, "C:min"),
        (5, 6, "N"),
    ]
    assert segments[0]["start_beat"] == 0
    for current, following in pairwise(segments):
        assert current["end_beat"] == following["start_beat"]
    assert segments[-1]["end_beat"] == len(states)


def test_segment_candidates_lead_with_chosen_label_then_best_means() -> None:
    # C:7 has the higher mean over the segment, but the smoothed state is C:maj.
    sims = _sims({1: {"C:7": 0.99, "C:maj": 0.7}, 2: {"C:7": 0.99, "C:maj": 0.7}})
    sims[LABELS.index("F:maj")] = 0.8  # clear third place, below both C chords
    states = _states(*["C:maj"] * 6)

    (only,) = segment(states, sims, np.zeros((84, 6)))

    assert only["candidates"] == ["C:maj", "C:7", "F:maj"]
    assert set(only) == {"start_beat", "end_beat", "chord", "candidates", "bass"}
    json.dumps(only)
    assert type(only["start_beat"]) is int
    assert type(only["end_beat"]) is int
    assert type(only["chord"]) is str
    assert all(type(c) is str for c in only["candidates"])


def _cqt(beats: list) -> np.ndarray:
    """(84, n) matrix: per beat None (zero column), a bin, or a (bin, amplitude) pair."""
    cqt = np.zeros((84, len(beats)))
    for beat, entry in enumerate(beats):
        if entry is not None:
            bin_, amplitude = entry if isinstance(entry, tuple) else (entry, 1.0)
            cqt[bin_, beat] = amplitude
    return cqt


def test_segment_bass_is_none_for_no_chord() -> None:
    states = _states("C:maj", "C:maj", "C:maj", "N", "N", "N")

    chord, no_chord = segment(states, _sims({}), _cqt([12] * 6))

    assert chord["bass"] == "C"
    assert no_chord["bass"] is None


@pytest.mark.parametrize(
    ("bins", "expected"),
    [
        ([12, 16, 12], "C"),
        ([16, 12], "E"),
        ([None, 12], "C"),
        ([None] * 3, None),
    ],
)
def test_segment_bass_is_a_vote_over_beats(bins: list, expected: str | None) -> None:
    states = _states(*["C:maj"] * len(bins))
    sims = _sims({})[:, : len(bins)]

    (only,) = segment(states, sims, _cqt(bins))

    assert only["bass"] == expected


@pytest.mark.parametrize(
    ("labels", "bins", "expected"),
    [
        # A bass held two beats under one chord cuts and is reported.
        (["C:maj"] * 8, [12] * 4 + [16] * 4, [(0, 4, "C:maj", "C"), (4, 8, "C:maj", "E")]),
        # A one-beat move under an unchanged chord neither cuts nor is reported,
        (["C:maj"] * 8, [12] * 3 + [16] + [12] * 4, [(0, 8, "C:maj", "C")]),
        # however loud it is,
        (["C:maj"] * 4, [12] * 3 + [(16, 10.0)], [(0, 4, "C:maj", "C")]),
        # nor at the start of the run.
        (["C:maj"] * 8, [16] + [12] * 7, [(0, 8, "C:maj", "C")]),
        # No value holds two beats: the most frequent, ties to the earliest.
        (["C:maj"] * 8, [12, 16] * 4, [(0, 8, "C:maj", "C")]),
        # A held silence cuts too.
        (
            ["C:maj"] * 6,
            [12, 12, None, None, 16, 16],
            [(0, 2, "C:maj", "C"), (2, 4, "C:maj", None), (4, 6, "C:maj", "E")],
        ),
        # A bass change on a chord change adds no cut.
        (
            ["C:maj"] * 4 + ["F:maj"] * 4,
            [12] * 4 + [21] * 4,
            [(0, 4, "C:maj", "C"), (4, 8, "F:maj", "A")],
        ),
        # An N run is never cut.
        (["N"] * 8, [12] * 4 + [16] * 4, [(0, 8, "N", None)]),
        # A one-beat chord run keeps its own bass, whatever the beats around it hold.
        (
            ["N"] * 3 + ["C:maj"] + ["N"] * 4,
            [12] * 3 + [16] + [12] * 4,
            [(0, 3, "N", None), (3, 4, "C:maj", "E"), (4, 8, "N", None)],
        ),
    ],
)
def test_segment_cuts_where_a_held_bass_changes(
    labels: list[str], bins: list, expected: list[tuple]
) -> None:
    segments = segment(_states(*labels), _sims({}, len(labels)), _cqt(bins))

    assert [(s["start_beat"], s["end_beat"], s["chord"], s["bass"]) for s in segments] == expected
    json.dumps(segments)
    for s in segments:
        assert type(s["start_beat"]) is int
        assert type(s["end_beat"]) is int
        assert s["candidates"][0] == s["chord"]


def test_segments_cut_on_the_bass_rank_candidates_over_their_own_beats() -> None:
    sims = _sims({beat: {"E:min": 0.9} for beat in range(4, 8)}, 8)

    first, second = segment(_states(*["C:maj"] * 8), sims, _cqt([12] * 4 + [16] * 4))

    assert first["candidates"] == ["C:maj", "C:7", "C:min"]
    assert second["candidates"] == ["C:maj", "E:min", "C:7"]


@pytest.mark.parametrize(
    ("label", "bass", "expected"),
    [
        ("C:maj", "C", "root"),
        ("C:maj", "E", "first"),
        ("C:maj", "G", "second"),
        ("C:7", "A#", "third"),
        ("A:min", "C", "first"),
        ("F#:7", "E", "third"),
        ("C:maj", "D", "non_chord"),
        ("C:maj", "A#", "non_chord"),
        ("N", "C", None),
        ("C:maj", None, None),
    ],
)
def test_inversion(label: str, bass: str | None, expected: str | None) -> None:
    assert inversion(label, bass) == expected


def _profile(**bins: float) -> np.ndarray:
    profile = np.zeros(84)
    for name, value in bins.items():
        profile[int(name.removeprefix("b"))] = value
    return profile


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (_profile(), None),
        (_profile(b15=0.55, b16=1.0, b17=0.55), "E"),
        (_profile(b12=1.0, b4=0.4), "C"),
        (_profile(b14=0.6, b24=1.0), "D"),
        (_profile(b0=1.0), "C"),
        (_profile(b36=1.0, b35=0.5, b34=0.1), None),
        (_profile(b16=1.0, b40=3.0), "E"),
        (_profile(b35=1.0), "B"),
    ],
)
def test_pick_bass(profile: np.ndarray, expected: str | None) -> None:
    result = pick_bass(profile)
    assert result == expected
    assert result is None or isinstance(result, str)
