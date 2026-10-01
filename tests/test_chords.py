import json
from itertools import pairwise

import numpy as np
import pytest

from chordotomy.chords import (
    LABELS,
    N_SCORE,
    QUALITY_OFFSET,
    inversion,
    match,
    pick_bass,
    resolve_twins,
    segment,
    smooth,
)

# Literal music-theory ground truth, deliberately not imported from the module.
ROOT_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
INTERVALS = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "min6": (0, 3, 7, 9),
    "hdim7": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "sus4": (0, 5, 7),
}


def test_vocabulary() -> None:
    assert len(LABELS) == 109
    # Quality-major: the order is the tie-break between pitch-set twins.
    assert LABELS[0] == "C:maj"
    assert LABELS[12] == "C:min"
    assert LABELS[-1] == "N"
    for label in ("F#:7", "A#:min", "G:min6", "F#:hdim7", "C#:dim7", "G:sus4"):
        assert label in LABELS
    assert len(set(LABELS)) == len(LABELS)


def _pitch_set(label: str) -> set[int]:
    root, quality = label.split(":")
    return {(ROOT_NAMES.index(root) + i) % 12 for i in INTERVALS[quality]}


def _chroma(*notes: str) -> np.ndarray:
    """A (12, 1) binary chroma, 1.0 on each named pitch class."""
    column = np.zeros((12, 1))
    column[[ROOT_NAMES.index(note) for note in notes]] = 1.0
    return column


@pytest.fixture
def no_offsets(monkeypatch) -> None:
    """Every QUALITY_OFFSET entry 0, for tests that feed hand-built binary chromas.

    The offsets are sized for chromas that carry partials, as audio does. A binary chroma has
    none: against the templates a binary Cmaj7 beats C:maj by only 0.099, under the maj7 offset.
    """
    for quality in QUALITY_OFFSET:
        monkeypatch.setitem(QUALITY_OFFSET, quality, 0.0)


def test_match_ranks_ideal_chroma_first(no_offsets) -> None:
    names = [f"{root}:{quality}" for quality in INTERVALS for root in ROOT_NAMES]
    chroma = np.zeros((12, len(names)))
    for column, name in enumerate(names):
        chroma[list(_pitch_set(name)), column] = 1.0

    scores = match(chroma, np.zeros_like(chroma))

    assert scores.shape == (109, 108)
    assert np.all(scores[LABELS.index("N")] == N_SCORE)
    top = [LABELS[i] for i in scores.argmax(axis=0)]
    for name, label in zip(names, top, strict=True):
        assert _pitch_set(label) == _pitch_set(name), (name, label)
        # A twin's pitch set goes to the earlier twin without a bass; see the tie-break test.
        if name.split(":")[1] not in ("min6", "hdim7", "dim7"):
            assert label == name


def test_silent_and_flat_columns_are_no_chord() -> None:
    chroma = np.stack([np.zeros(12), np.ones(12)], axis=1)

    scores = match(chroma, chroma)

    assert list(scores.argmax(axis=0)) == [LABELS.index("N")] * 2


def test_twins_tie_break_on_label_order(no_offsets) -> None:
    # G Bb D E is G:min6 or E:hdim7.
    scores = match(_chroma("G", "A#", "D", "E"), np.zeros((12, 1)))[:, 0]
    first, second = np.argsort(-scores, kind="stable")[:2]

    assert (LABELS[first], LABELS[second]) == ("G:min6", "E:hdim7")
    assert scores[first] == scores[second]
    # The decode takes the first argmax too.
    assert _labels(np.repeat(scores[:, None], 4, axis=1)) == ["G:min6"] * 4

    # C Eb Gb A is the dim7 on any of its four tones.
    scores = match(_chroma("C", "D#", "F#", "A"), np.zeros((12, 1)))[:, 0]

    assert LABELS[scores.argmax()] == "C:dim7"
    for label in ("D#:dim7", "F#:dim7", "A:dim7"):
        assert scores[LABELS.index(label)] == scores[LABELS.index("C:dim7")]


@pytest.mark.parametrize(
    ("notes", "bass", "expected"),
    [
        (("G", "A#", "D", "E"), "E", "E:hdim7"),
        (("G", "A#", "D", "E"), "G", "G:min6"),
        (("C", "D#", "F#", "A"), "A", "A:dim7"),
        (("C", "D#", "F#", "A"), "F#", "F#:dim7"),
    ],
)
def test_bass_tells_the_twins_apart(no_offsets, notes, bass, expected) -> None:
    assert LABELS[match(_chroma(*notes), _chroma(bass)).argmax()] == expected


@pytest.mark.parametrize("bass", ["A", "C"])
def test_a_seventh_over_its_third_is_an_inversion(no_offsets, bass) -> None:
    # C E G A is Am7 or C6; C6 is not in the vocabulary, so a C bass makes Am7/C, not C6.
    assert LABELS[match(_chroma("C", "E", "G", "A"), _chroma(bass)).argmax()] == "A:min7"
    assert inversion("A:min7", bass) == {"A": "root", "C": "first"}[bass]


def test_offsets_apply_per_quality(monkeypatch) -> None:
    treble, bass = _chroma("C", "E", "G", "B"), np.zeros((12, 1))
    monkeypatch.setitem(QUALITY_OFFSET, "maj7", 0.0)
    free = match(treble, bass)[:, 0]
    monkeypatch.setitem(QUALITY_OFFSET, "maj7", -1.0)
    penalised = match(treble, bass)[:, 0]

    assert LABELS[free.argmax()] == "C:maj7"
    assert LABELS[penalised.argmax()] == "C:maj"
    # Its rank moves as the maj7 rows drop past it, but the entry does not touch its score.
    assert penalised[LABELS.index("C:min7")] == free[LABELS.index("C:min7")]


def test_twins_share_one_offset() -> None:
    # Otherwise the offset, not the bass, would tell G:min6 from E:hdim7.
    assert QUALITY_OFFSET["min6"] == QUALITY_OFFSET["hdim7"]


def _scores(overrides: dict[int, dict[str, float]], n: int = 6) -> np.ndarray:
    """(109, n) scores: 0.0 everywhere, C:maj 0.8 / C:7 0.6 unless overridden, N N_SCORE."""
    scores = np.zeros((len(LABELS), n))
    scores[LABELS.index("C:maj")] = 0.8
    scores[LABELS.index("C:7")] = 0.6
    scores[LABELS.index("N")] = N_SCORE
    for beat, values in overrides.items():
        for label, value in values.items():
            scores[LABELS.index(label), beat] = value
    return scores


def _labels(scores: np.ndarray, level: np.ndarray | None = None, period: float = 0.5) -> list[str]:
    if level is None:
        level = np.zeros(scores.shape[1])
    return [LABELS[i] for i in smooth(scores, level, period)]


# At period 0.5 the self-loop is about 0.84 and the rest is spread over 108 other labels, so a
# switch costs about 6.31 nats and leaving a chord and coming back about 12.6; a score gap of g
# on one beat is worth g / TEMPERATURE = 33.3 g nats. The gaps below hold the verdict by at least
# 2 nats.


def test_smooth_suppresses_one_beat_sibling_change() -> None:
    scores = _scores({2: {"C:maj": 0.6, "C:7": 0.8}})

    assert _labels(scores) == ["C:maj"] * 6


def test_smooth_keeps_two_beat_sibling_change() -> None:
    scores = _scores({2: {"C:maj": 0.4, "C:7": 0.8}, 3: {"C:maj": 0.4, "C:7": 0.8}})

    assert _labels(scores) == ["C:maj", "C:maj", "C:7", "C:7", "C:maj", "C:maj"]


def test_smooth_keeps_one_beat_distant_change() -> None:
    scores = _scores({2: {"C:maj": 0.2, "F:maj": 0.8}})

    assert _labels(scores) == ["C:maj", "C:maj", "F:maj", "C:maj", "C:maj", "C:maj"]


def test_a_gated_beat_is_n() -> None:
    level = np.zeros(6)
    level[2:4] = -60.0

    assert _labels(_scores({}), level) == ["C:maj", "C:maj", "N", "N", "C:maj", "C:maj"]


def test_no_chord_above_the_n_score_is_n() -> None:
    below = np.zeros((len(LABELS), 6))
    below[LABELS.index("C:maj")] = N_SCORE - 0.1
    below[LABELS.index("N")] = N_SCORE
    above = below.copy()
    above[LABELS.index("C:maj")] = N_SCORE + 0.1

    assert _labels(below) == ["N"] * 6
    assert _labels(above) == ["C:maj"] * 6


def test_the_self_loop_follows_seconds_not_beats() -> None:
    # 10.3 nats against a round trip of about 12.6 at period 0.5 and about 8.1 at period 3.0.
    scores = _scores({2: {"C:maj": 0.49, "C:7": 0.8}})

    assert _labels(scores, period=0.5) == ["C:maj"] * 6
    assert _labels(scores, period=3.0) == ["C:maj", "C:maj", "C:7", "C:maj", "C:maj", "C:maj"]


def _states(*labels: str) -> np.ndarray:
    # uint16, as librosa.sequence.viterbi returns it.
    return np.array([LABELS.index(label) for label in labels], dtype=np.uint16)


def test_segment_merges_runs_and_tiles_beats() -> None:
    states = _states("C:maj", "C:maj", "C:min", "C:min", "C:min", "N")

    segments = segment(states, _scores({}), np.zeros((84, 6)))

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
    scores = _scores({beat: {"C:7": 1.0, "C:maj": 0.6} for beat in range(1, 4)})
    scores[LABELS.index("F:maj")] = 0.5  # clear third place, below both C chords
    states = _states(*["C:maj"] * 6)

    (only,) = segment(states, scores, np.zeros((84, 6)))

    assert only["candidates"] == ["C:maj", "C:7", "F:maj"]
    assert set(only) == {"start_beat", "end_beat", "chord", "candidates", "bass"}
    json.dumps(only)
    assert type(only["start_beat"]) is int
    assert type(only["end_beat"]) is int
    assert type(only["chord"]) is str
    assert all(type(c) is str for c in only["candidates"])


def _runs(*entries: tuple[str, str | None]) -> list[dict]:
    """Two-beat segments from (chord, bass) pairs, each with candidates led by its chord."""
    return [
        {
            "start_beat": 2 * i,
            "end_beat": 2 * i + 2,
            "chord": chord,
            "candidates": [chord, "C:maj", "A:min"],
            "bass": bass,
        }
        for i, (chord, bass) in enumerate(entries)
    ]


@pytest.mark.parametrize(
    ("label", "bass", "following", "expected"),
    [
        ("C:dim7", None, "G:maj", "F#:dim7"),
        ("C:dim7", None, "E:min", "D#:dim7"),
        ("D:dim7", None, "A:min", "G#:dim7"),
        ("C#:dim7", None, "F:maj", "E:dim7"),
        # Already the leading-tone spelling.
        ("C#:dim7", None, "D:min", "C#:dim7"),
        # C# is not a tone of C:dim7, so no twin leads into D.
        ("C:dim7", None, "D:min", "C:dim7"),
        # A bass off the pitch set is no evidence either.
        ("C:dim7", "D", "G:maj", "F#:dim7"),
        # A dim7's bass is its inversion, not its root: F#°7 over C.
        ("C:dim7", "C", "G:maj", "F#:dim7"),
        # No twin leads into C, so the common-tone diminished keeps the recognizer's reading.
        ("C:dim7", "C", "C:maj", "C:dim7"),
        ("A:min6", None, "G:maj", "F#:hdim7"),
        # A bass on a min6's root is evidence for the m6 reading; on its third it is none.
        ("A:min6", "A", "G:maj", "A:min6"),
        ("A:min6", "C", "G:maj", "F#:hdim7"),
        # The twins E:hdim7 and D:hdim7 do not lead into C: vi add6 and a borrowed iv add6 stay.
        ("G:min6", None, "C:maj", "G:min6"),
        ("F:min6", None, "C:maj", "F:min6"),
        # Nor does D:hdim7 lead into G: IVm6 before V stays.
        ("F:min6", None, "G:maj", "F:min6"),
        # An hdim7's only twin is a min6.
        ("F#:hdim7", None, "G:maj", "F#:hdim7"),
        ("C:maj", None, "C#:maj", "C:maj"),
        ("C:dim7", None, "N", "C:dim7"),
        ("C:dim7", None, None, "C:dim7"),
    ],
)
def test_resolve_twins_spells_a_diminished_chord_by_where_it_leads(
    label: str, bass: str | None, following: str | None, expected: str
) -> None:
    entries = [(label, bass)] + ([] if following is None else [(following, None)])

    resolved = resolve_twins(_runs(*entries))

    assert [s["chord"] for s in resolved] == [expected] + ([] if following is None else [following])


def test_resolve_twins_relabels_a_run_split_by_the_bass_as_a_whole() -> None:
    segments = _runs(("C:dim7", None), ("C:dim7", "D"), ("G:maj", "G"))
    resolved = resolve_twins(segments)

    assert [s["chord"] for s in resolved] == ["F#:dim7", "F#:dim7", "G:maj"]
    assert [s["bass"] for s in resolved] == [None, "D", "G"]
    assert [(s["start_beat"], s["end_beat"]) for s in resolved] == [(0, 2), (2, 4), (4, 6)]
    # A pure function: the decoder's segments are left as they were.
    assert [s["chord"] for s in segments] == ["C:dim7", "C:dim7", "G:maj"]

    # A bass on a min6's root anywhere in the run keeps the whole run.
    resolved = resolve_twins(_runs(("A:min6", None), ("A:min6", "A"), ("G:maj", "G")))

    assert [s["chord"] for s in resolved] == ["A:min6", "A:min6", "G:maj"]


def test_resolve_twins_spells_a_dim7_over_a_moving_bass_as_one_chord() -> None:
    # D#°7 over A, then over F#, decodes as two dim7 runs on one pitch set.
    resolved = resolve_twins(_runs(("A:dim7", "A"), ("F#:dim7", "F#"), ("E:min", "E")))

    assert [s["chord"] for s in resolved] == ["D#:dim7", "D#:dim7", "E:min"]
    assert resolved[0]["candidates"][:2] == ["D#:dim7", "A:dim7"]

    # Already spelled as the part after it, which leads on: left as it is.
    resolved = resolve_twins(_runs(("F#:dim7", "F#"), ("A:dim7", "A"), ("G:maj", "G")))

    assert [s["chord"] for s in resolved] == ["F#:dim7", "F#:dim7", "G:maj"]
    assert resolved[0]["candidates"] == ["F#:dim7", "C:maj", "A:min"]

    # With no twin leading on, the whole chord keeps the reading of its last part.
    resolved = resolve_twins(_runs(("A:dim7", "A"), ("C:dim7", "C"), ("C:maj", "C")))

    assert [s["chord"] for s in resolved] == ["C:dim7", "C:dim7", "C:maj"]


def test_resolve_twins_reads_a_chain_against_the_next_chord_as_written() -> None:
    # C#°7 D°7 D#°7 Em without a bass decodes as C#:dim7 D:dim7 C:dim7 E:min. D:dim7 leads into
    # the D#:dim7 it is followed by, not into C:dim7's B.
    runs = _runs(("C#:dim7", None), ("D:dim7", None), ("C:dim7", None), ("E:min", None))

    resolved = resolve_twins(runs)

    assert [s["chord"] for s in resolved] == ["C#:dim7", "D:dim7", "D#:dim7", "E:min"]


def test_resolve_twins_reorders_the_tie_in_the_candidates() -> None:
    dim7, following = _runs(("C:dim7", None), ("G:maj", "G"))
    dim7["candidates"] = ["C:dim7", "D#:dim7", "F#:dim7"]
    min6, _ = _runs(("A:min6", None), ("G:maj", "G"))
    min6["candidates"] = ["A:min6", "F#:hdim7", "A:min7"]

    assert resolve_twins([dim7, following])[0]["candidates"] == ["F#:dim7", "C:dim7", "D#:dim7"]
    assert resolve_twins([min6, following])[0]["candidates"] == ["F#:hdim7", "A:min6", "A:min7"]


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

    chord, no_chord = segment(states, _scores({}), _cqt([12] * 6))

    assert chord["bass"] == "C"
    assert no_chord["bass"] is None


@pytest.mark.parametrize(
    ("bins", "expected"),
    [
        ([12, 16, 12], "C"),
        ([16, 12], "E"),
        ([None, 12], "C"),
        ([None] * 3, None),
        # Silence votes too: a lone note among rests does not label the segment.
        ([None, 16, None, 7, None], None),
        ([None, 16, 16, None, 7], "E"),
    ],
)
def test_segment_bass_is_a_vote_over_beats(bins: list, expected: str | None) -> None:
    states = _states(*["C:maj"] * len(bins))
    scores = _scores({})[:, : len(bins)]

    (only,) = segment(states, scores, _cqt(bins))

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
        # The first held value cuts at its own start when two or more beats precede it,
        (
            ["C:maj"] * 6,
            [12, 16, 12, 16, 7, 7],
            [(0, 4, "C:maj", "C"), (4, 6, "C:maj", "G")],
        ),
        # but a one-beat leading blip is absorbed rather than made a one-beat segment.
        (["C:maj"] * 4, [16, 12, 12, 12], [(0, 4, "C:maj", "C")]),
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
    segments = segment(_states(*labels), _scores({}, len(labels)), _cqt(bins))

    assert [(s["start_beat"], s["end_beat"], s["chord"], s["bass"]) for s in segments] == expected
    json.dumps(segments)
    for s in segments:
        assert type(s["start_beat"]) is int
        assert type(s["end_beat"]) is int
        assert s["candidates"][0] == s["chord"]


def test_segments_cut_on_the_bass_rank_candidates_over_their_own_beats() -> None:
    scores = _scores({beat: {"E:min": 0.9} for beat in range(4, 8)}, 8)

    first, second = segment(_states(*["C:maj"] * 8), scores, _cqt([12] * 4 + [16] * 4))

    assert first["candidates"] == ["C:maj", "C:7", "N"]
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
        ("C:maj7", "B", "third"),
        ("D:min7", "C", "third"),
        # The added sixth of a min6 is its third position.
        ("G:min6", "E", "third"),
        ("F#:hdim7", "E", "third"),
        ("C#:dim7", "A#", "third"),
        ("G:sus4", "C", "first"),
        ("G:sus4", "D", "second"),
        ("G:sus4", "B", "non_chord"),
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
