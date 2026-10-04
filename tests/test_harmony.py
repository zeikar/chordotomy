import json

import pytest

from chordotomy.chords import QUALITIES
from chordotomy.harmony import analyze, analyze_chord, estimate_key, key_regions, parse_key


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("C:maj", "C:maj"),
        ("A:min", "A:min"),
        ("Bb:maj", "A#:maj"),
        ("Db:min", "C#:min"),
        ("Cb:maj", "B:maj"),
        ("Fb:maj", "E:maj"),
    ],
)
def test_parse_key(text: str, expected: str) -> None:
    assert parse_key(text) == expected


@pytest.mark.parametrize("text", ["C", "Cm", "C:major", "H:maj", ""])
def test_parse_key_rejects(text: str) -> None:
    with pytest.raises(ValueError, match="not a key"):
        parse_key(text)


def test_estimate_key_major() -> None:
    ranked = estimate_key([("C:maj", 1), ("F:maj", 1), ("G:maj", 1), ("C:maj", 1)])
    assert ranked[0] == "C:maj"


def test_estimate_key_minor() -> None:
    ranked = estimate_key([("A:min", 1), ("D:min", 1), ("E:maj", 1), ("A:min", 1)])
    assert ranked[0] == "A:min"


def test_relative_keys_are_settled_by_duration() -> None:
    loop = [("A:min", 1), ("F:maj", 1), ("C:maj", 1), ("G:maj", 1)]
    assert estimate_key(loop)[:2] == ["C:maj", "A:min"]
    assert estimate_key([("A:min", 2), *loop[1:]])[0] == "A:min"


def test_tonic_sevenths_break_ties_like_triads() -> None:
    triads = estimate_key([("A:min", 2), ("C:maj", 2)])
    sevenths = estimate_key([("A:min7", 2), ("C:maj7", 2)])
    assert triads[0] == sevenths[0] == "A:min"


def test_tonic_added_ninths_break_ties_like_triads() -> None:
    added = estimate_key([("A:min(9)", 2), ("C:maj(9)", 2)])
    assert added[0] == "A:min"


def test_tonic_seventh_counts_toward_duration_tie_break() -> None:
    loop = [("A:min7", 2), ("F:maj", 1), ("C:maj", 1), ("G:maj", 1)]
    assert estimate_key(loop)[0] == "A:min"


def test_first_chord_breaks_ties() -> None:
    assert estimate_key([("C:maj", 1), ("G:maj", 1)] * 2)[0] == "C:maj"
    assert estimate_key([("G:maj", 1), ("C:maj", 1)] * 2)[0] == "G:maj"


def test_estimate_key_ignores_n() -> None:
    assert estimate_key([("N", 4), ("C:maj", 2), ("N", 1), ("G:7", 2)])[0] == "C:maj"


def test_estimate_key_all_n_is_empty() -> None:
    assert estimate_key([("N", 8)]) == []


def test_estimate_key_ranks_all_keys() -> None:
    ranked = estimate_key([("C:maj", 8)])
    assert len(ranked) == 24
    assert len(set(ranked)) == 24
    assert all(key.split(":")[1] in ("maj", "min") for key in ranked)


def test_a_diatonic_maj7_votes_for_its_key() -> None:
    # Without C:maj7's vote, G:maj and D:min make G major (6 against C major's 5).
    assert estimate_key([("C:maj7", 4), ("G:maj", 2), ("D:min", 1)])[0] == "C:maj"


def test_estimate_key_takes_every_quality() -> None:
    ranked = estimate_key([(f"C:{quality}", 1) for quality in QUALITIES])
    assert len(set(ranked)) == 24


@pytest.mark.parametrize(
    ("label", "key", "numeral", "function"),
    [
        ("C:maj", "C:maj", "I", "tonic"),
        ("D:min", "C:maj", "ii", "predominant"),
        ("E:min", "C:maj", "iii", "tonic"),
        ("F:maj", "C:maj", "IV", "predominant"),
        ("G:maj", "C:maj", "V", "dominant"),
        ("G:7", "C:maj", "V7", "dominant"),
        ("A:min", "C:maj", "vi", "tonic"),
        ("A:min", "A:min", "i", "tonic"),
        ("C:maj", "A:min", "III", "tonic"),
        ("D:min", "A:min", "iv", "predominant"),
        ("E:min", "A:min", "v", "dominant"),
        ("E:maj", "A:min", "V", "dominant"),
        ("E:7", "A:min", "V7", "dominant"),
        ("F:maj", "A:min", "VI", "tonic"),
        ("G:maj", "A:min", "VII", "dominant"),
        ("G:7", "A:min", "VII7", "dominant"),
        ("F#:maj", "B:maj", "V", "dominant"),
        ("C:maj7", "C:maj", "Imaj7", "tonic"),
        ("D:min7", "C:maj", "ii7", "predominant"),
        ("E:min7", "C:maj", "iii7", "tonic"),
        ("F:maj7", "C:maj", "IVmaj7", "predominant"),
        ("A:min7", "C:maj", "vi7", "tonic"),
        ("B:hdim7", "C:maj", "viiø7", "dominant"),
        ("G:sus4", "C:maj", "Vsus4", "dominant"),
        ("D:min6", "C:maj", "iiadd6", "predominant"),
        # On a secondary dominant's root, but a sus4 never counts as one.
        ("D:sus4", "C:maj", "IIsus4", "predominant"),
        ("A:sus4", "C:maj", "VIsus4", "tonic"),
        ("A:min7", "A:min", "i7", "tonic"),
        ("B:hdim7", "A:min", "iiø7", "predominant"),
        ("C:maj7", "A:min", "IIImaj7", "tonic"),
        ("D:min7", "A:min", "iv7", "predominant"),
        ("F:maj7", "A:min", "VImaj7", "tonic"),
        ("G#:dim7", "A:min", "#vii°7", "dominant"),
        # Harmonic minor's raised leading tone, admitted in these two as in V and #vii°7.
        ("G#:dim", "A:min", "#vii°", "dominant"),
        ("C:aug", "A:min", "III+", "tonic"),
        # The scale test admits the diminished triads as they are.
        ("B:dim", "C:maj", "vii°", "dominant"),
        ("B:dim", "A:min", "ii°", "predominant"),
        ("C:sus2", "C:maj", "Isus2", "tonic"),
        ("G:sus2", "C:maj", "Vsus2", "dominant"),
        ("D:sus2", "C:maj", "IIsus2", "predominant"),
        ("G:sus4(b7)", "C:maj", "V7sus4", "dominant"),
        ("D:sus4(b7)", "C:maj", "II7sus4", "predominant"),
        ("A:sus4(b7)", "C:maj", "VI7sus4", "tonic"),
        ("E:sus4(b7)", "C:maj", "III7sus4", "tonic"),
        ("E:sus4(b7)", "A:min", "V7sus4", "dominant"),
        ("A:sus4(b7)", "A:min", "I7sus4", "tonic"),
        ("D:sus4(b7)", "A:min", "IV7sus4", "predominant"),
        ("G:sus4(b7)", "A:min", "VII7sus4", "dominant"),
        ("C:maj(9)", "C:maj", "Iadd9", "tonic"),
        ("F:maj(9)", "C:maj", "IVadd9", "predominant"),
        ("G:maj(9)", "C:maj", "Vadd9", "dominant"),
        ("D:min(9)", "C:maj", "iiadd9", "predominant"),
        ("A:min(9)", "C:maj", "viadd9", "tonic"),
        ("A:min(9)", "A:min", "iadd9", "tonic"),
        ("D:min(9)", "A:min", "ivadd9", "predominant"),
        ("C:maj(9)", "A:min", "IIIadd9", "tonic"),
        ("F:maj(9)", "A:min", "VIadd9", "tonic"),
        ("G:maj(9)", "A:min", "VIIadd9", "dominant"),
    ],
)
def test_analyze_chord_diatonic(label: str, key: str, numeral: str, function: str) -> None:
    assert analyze_chord(label, key) == {
        "numeral": numeral,
        "role": "diatonic",
        "function": function,
        "target": None,
    }


def test_analyze_chord_n() -> None:
    assert analyze_chord("N", "C:maj") == {
        "numeral": None,
        "role": None,
        "function": None,
        "target": None,
    }


@pytest.mark.parametrize(
    ("label", "key", "numeral", "target"),
    [
        ("D:7", "C:maj", "V7/V", "V"),
        ("D:maj", "C:maj", "V/V", "V"),
        ("E:7", "C:maj", "V7/vi", "vi"),
        ("A:7", "C:maj", "V7/ii", "ii"),
        ("B:7", "C:maj", "V7/iii", "iii"),
        ("C:7", "C:maj", "V7/IV", "IV"),
        ("C:7", "A:min", "V7/VI", "VI"),
        ("B:7", "A:min", "V7/V", "V"),
        # An added ninth keeps the triad's leading tone, whether the ninth is the key's (B over A)
        # or not (F# over E).
        ("D:maj(9)", "C:maj", "Vadd9/V", "V"),
        ("A:maj(9)", "C:maj", "Vadd9/ii", "ii"),
        ("E:maj(9)", "C:maj", "Vadd9/vi", "vi"),
    ],
)
def test_analyze_chord_secondary_dominant(label: str, key: str, numeral: str, target: str) -> None:
    assert analyze_chord(label, key) == {
        "numeral": numeral,
        "role": "secondary_dominant",
        "function": None,
        "target": target,
    }


@pytest.mark.parametrize(
    ("label", "following", "numeral", "role", "target"),
    [
        ("A:maj", "D:min", "V/iv", "secondary_dominant", "iv"),
        *[("A:maj", f, "I", "borrowed", None) for f in ("D:7", "D:maj", "N", "E:maj", None)],
        *[("D:maj", f, "V/VII", "secondary_dominant", "VII") for f in ("G:maj", "G:7")],
        *[("D:maj", f, "IV", "borrowed", None) for f in ("G:min", "A:min", "N", None)],
        # Their dominant sevenths are no part of the overlap: rule 2 claims them wherever they go.
        *[("A:7", f, "V7/iv", "secondary_dominant", "iv") for f in ("D:min", "D:7", "N", None)],
        *[("D:7", f, "V7/VII", "secondary_dominant", "VII") for f in ("G:maj", "G:min", "N", None)],
        # With an added ninth they are still chords of A major, so the overlap holds.
        ("A:maj(9)", "D:min", "Vadd9/iv", "secondary_dominant", "iv"),
        *[("A:maj(9)", f, "Iadd9", "borrowed", None) for f in ("D:maj", "N", None)],
        ("D:maj(9)", "G:maj", "Vadd9/VII", "secondary_dominant", "VII"),
        ("D:maj(9)", None, "IVadd9", "borrowed", None),
    ],
)
def test_overlap_resolves_only_on_a_diatonic_chord_on_the_target_root(
    label: str, following: str | None, numeral: str, role: str, target: str | None
) -> None:
    assert analyze_chord(label, "A:min", following) == {
        "numeral": numeral,
        "role": role,
        "function": None,
        "target": target,
    }


@pytest.mark.parametrize(
    ("label", "key", "following", "numeral", "role"),
    [
        ("D:maj", "C:maj", "A:min", "V/V", "secondary_dominant"),
        ("A#:maj", "C:maj", "D#:maj", "bVII", "borrowed"),
        ("D:maj7", "A:min", "G:maj", "IVmaj7", "borrowed"),
        ("B:hdim7", "A:min", "C:maj", "iiø7", "diatonic"),
        # Diatonic first: a diminished triad on a leading tone of the key's own is its degree.
        ("B:dim", "C:maj", "C:maj", "vii°", "diatonic"),
        ("B:dim", "A:min", "C:maj", "ii°", "diatonic"),
        # An augmented triad is never a secondary dominant: its root is the bass's or
        # resolve_twins's spelling of a symmetric chord, not a fifth relation.
        ("G:aug", "C:maj", "C:maj", "V+", "chromatic"),
        ("C:aug", "C:maj", "F:maj", "I+", "chromatic"),
        # As a 7 this would be V7/IV; a 7sus4 never is.
        ("C:sus4(b7)", "C:maj", "F:maj", "I7sus4", "borrowed"),
        ("D:sus4(b7)", "C:maj", "G:maj", "II7sus4", "diatonic"),
    ],
)
def test_following_is_ignored_outside_the_overlap(
    label: str, key: str, following: str, numeral: str, role: str
) -> None:
    result = analyze_chord(label, key, following)
    assert result == analyze_chord(label, key)
    assert (result["numeral"], result["role"]) == (numeral, role)


@pytest.mark.parametrize(
    ("label", "key", "following", "numeral", "role", "target"),
    [
        *[("F#:hdim7", "C:maj", f, "viiø7/V", "secondary_dominant", "V") for f in ("G:maj", "G:7")],
        *[("F#:hdim7", "C:maj", f, "#ivø7", "chromatic", None) for f in ("F:maj", "N", None)],
        *[
            ("C#:dim7", "C:maj", f, "vii°7/ii", "secondary_dominant", "ii")
            for f in ("D:min", "D:min7")
        ],
        ("C#:dim7", "C:maj", "D:maj", "#i°7", "chromatic", None),
        ("D#:dim7", "C:maj", "E:min", "vii°7/iii", "secondary_dominant", "iii"),
        ("G#:dim7", "C:maj", "A:min", "vii°7/vi", "secondary_dominant", "vi"),
        ("E:dim7", "C:maj", "F:maj", "vii°7/IV", "secondary_dominant", "IV"),
        # The tonic is never a target.
        ("B:dim7", "C:maj", "C:maj", "vii°7", "borrowed", None),
        ("D#:dim7", "A:min", "E:maj", "vii°7/V", "secondary_dominant", "V"),
        ("C#:dim7", "A:min", "D:min", "vii°7/iv", "secondary_dominant", "iv"),
        ("B:dim7", "A:min", "C:maj", "vii°7/III", "secondary_dominant", "III"),
        # The diminished triad leads up a semitone as its sevenths do.
        *[
            ("C#:dim", "C:maj", f, "vii°/ii", "secondary_dominant", "ii")
            for f in ("D:min", "D:min7")
        ],
        ("C#:dim", "C:maj", "D:maj", "#i°", "chromatic", None),
        ("F#:dim", "C:maj", "G:maj", "vii°/V", "secondary_dominant", "V"),
        ("F#:dim", "C:maj", "F:maj", "#iv°", "chromatic", None),
        ("D#:dim", "A:min", "E:maj", "vii°/V", "secondary_dominant", "V"),
    ],
)
def test_leading_tone_chord_resolves_only_on_a_diatonic_chord_on_the_target_root(
    label: str, key: str, following: str | None, numeral: str, role: str, target: str | None
) -> None:
    assert analyze_chord(label, key, following) == {
        "numeral": numeral,
        "role": role,
        "function": None,
        "target": target,
    }


@pytest.mark.parametrize(
    ("label", "key", "numeral"),
    [
        ("A#:maj", "C:maj", "bVII"),
        ("F:min", "C:maj", "iv"),
        ("G#:maj", "C:maj", "bVI"),
        ("D#:maj", "C:maj", "bIII"),
        ("C:min", "C:maj", "i"),
        ("G:min", "C:maj", "v"),
        ("A#:7", "C:maj", "bVII7"),
        ("B:min", "A:min", "ii"),
        ("C#:min", "A:min", "#iii"),
        ("F:min6", "C:maj", "ivadd6"),
        # C minor's harmonic vii°7.
        ("B:dim7", "C:maj", "vii°7"),
        ("D#:maj7", "C:maj", "bIIImaj7"),
        ("G:min7", "C:maj", "v7"),
        ("D:hdim7", "C:maj", "iiø7"),
        ("D:maj7", "A:min", "IVmaj7"),
        ("G#:hdim7", "A:min", "#viiø7"),
        # D F Ab lies in C minor as it is.
        ("D:dim", "C:maj", "ii°"),
        ("A#:sus2", "C:maj", "bVIIsus2"),
        # The 7sus4 of a parallel-mode sus4 has its seventh in that mode too.
        ("C:sus4(b7)", "C:maj", "I7sus4"),
        ("F:sus4(b7)", "C:maj", "IV7sus4"),
        ("A#:sus4(b7)", "C:maj", "bVII7sus4"),
        ("B:sus4(b7)", "A:min", "II7sus4"),
        ("F#:sus4(b7)", "A:min", "#VI7sus4"),
        # C minor's harmonic III+.
        ("D#:aug", "C:maj", "bIII+"),
        # A tetrad on a C minor triad, its fourth tone in either mode of C: D:dim7 has the notes
        # of the borrowed vii°7.
        ("A#:maj7", "C:maj", "bVIImaj7"),
        ("D:dim7", "C:maj", "ii°7"),
        ("C:min6", "C:maj", "iadd6"),
        ("G:min6", "C:maj", "vadd6"),
        # An added ninth on a C minor triad, from either mode of C: Ab Bb, and A over G minor.
        ("G#:maj(9)", "C:maj", "bVIadd9"),
        ("G:min(9)", "C:maj", "vadd9"),
        # The raised leading tone counts in V and V7 only; with its F#, E(add9) is A major's.
        ("E:maj(9)", "A:min", "Vadd9"),
    ],
)
def test_analyze_chord_borrowed(label: str, key: str, numeral: str) -> None:
    assert analyze_chord(label, key) == {
        "numeral": numeral,
        "role": "borrowed",
        "function": None,
        "target": None,
    }


@pytest.mark.parametrize(
    ("label", "key", "numeral"),
    [
        ("C#:maj", "C:maj", "bII"),
        ("F#:maj", "C:maj", "#IV"),
        # A triad of the key's own mode with a foreign seventh or sixth is not borrowed: F A C is
        # not in C minor, G B D and A C E are not in A major.
        ("F:7", "C:maj", "IV7"),
        ("G:maj7", "A:min", "VIImaj7"),
        ("A:min6", "A:min", "iadd6"),
        # The seventh is outside both modes of C, so these are not borrowed.
        ("D#:7", "C:maj", "bIII7"),
        ("G#:7", "C:maj", "bVI7"),
        ("G:maj7", "C:maj", "Vmaj7"),
        ("G#:min", "C:maj", "bvi"),
        ("B:min", "C:maj", "vii"),
        # The leading tone counts only in V, V7, #vii°, #vii°7 and III+: not in these.
        ("F:min", "A:min", "vi"),
        ("E:aug", "A:min", "V+"),
        # With no chord to lead into, a leading-tone chord is only its degree.
        ("F#:hdim7", "C:maj", "#ivø7"),
        ("F#:dim", "C:maj", "#iv°"),
        # D F Ab is in neither mode of A.
        ("D:dim", "A:min", "iv°"),
        # maj7 and sus4 are never secondary dominants: not V/V, not V/iii.
        ("D:maj7", "C:maj", "IImaj7"),
        ("B:sus4", "C:maj", "VIIsus4"),
        # A diminished or half-diminished seventh's root is raised, never flattened; C#:maj above
        # stays bII.
        ("C#:dim7", "C:maj", "#i°7"),
        ("D#:dim7", "C:maj", "#ii°7"),
        ("G#:dim7", "C:maj", "#v°7"),
        ("A#:dim7", "C:maj", "#vi°7"),
        ("D#:hdim7", "C:maj", "#iiø7"),
        ("A#:dim7", "A:min", "#i°7"),
        ("G:dim7", "A:min", "vii°7"),
        ("D#:dim7", "A:min", "#iv°7"),
        # The parallel minor's III+ is the one borrowed augmented triad; any other is chromatic,
        # and never a secondary dominant.
        ("G:aug", "C:maj", "V+"),
        ("C:aug", "C:maj", "I+"),
        # A diminished triad's root is raised too.
        ("C#:dim", "C:maj", "#i°"),
        ("D#:dim", "C:maj", "#ii°"),
        ("E:sus2", "C:maj", "IIIsus2"),
        # The seventh or the fifth is outside both modes of C: D#'s seventh Db, B's fifth F#.
        ("D#:sus4(b7)", "C:maj", "bIII7sus4"),
        ("B:sus4(b7)", "C:maj", "VII7sus4"),
        # E minor's ninth F# is in neither mode of C, and a min(9) is never a secondary dominant.
        ("E:min(9)", "C:maj", "iiiadd9"),
    ],
)
def test_analyze_chord_chromatic(label: str, key: str, numeral: str) -> None:
    assert analyze_chord(label, key) == {
        "numeral": numeral,
        "role": "chromatic",
        "function": None,
        "target": None,
    }


PROGRESSION = [("C:maj", 2), ("A:min", 2), ("D:7", 2), ("G:7", 2), ("N", 1), ("C:maj", 2)]
NO_ANALYSIS = {"numeral": None, "role": None, "function": None, "target": None}


def test_analyze_estimates_the_key() -> None:
    key, keys, analyses = analyze(PROGRESSION)
    assert key is not None
    assert key["label"] == "C:maj"
    assert key["source"] == "estimated"
    assert len(key["candidates"]) == 3
    assert len(set(key["candidates"])) == 3
    assert key["candidates"][0] == key["label"]
    assert keys == [{"start_beat": 0, "end_beat": 11, "label": "C:maj"}]
    assert [a["numeral"] for a in analyses] == ["I", "vi", "V7/V", "V7", None, "I"]
    json.dumps((key, keys, analyses))


def test_analyze_given_key_keeps_the_estimated_candidates() -> None:
    estimated, _, _ = analyze(PROGRESSION)
    key, _, analyses = analyze(PROGRESSION, key="A:min")
    assert estimated is not None
    assert key == {
        "label": "A:min",
        "source": "given",
        "candidates": estimated["candidates"],
    }
    assert [a["numeral"] for a in analyses] == ["III", "i", "V7/VII", "VII7", None, "III"]


def test_analyze_without_a_chord() -> None:
    assert analyze([("N", 4)]) == (None, [], [NO_ANALYSIS])
    assert analyze([("N", 4)], key="C:maj") == (
        {"label": "C:maj", "source": "given", "candidates": []},
        [{"start_beat": 0, "end_beat": 4, "label": "C:maj"}],
        [NO_ANALYSIS],
    )


def test_analyze_labels_a_leading_tone_chord_by_the_next_segment() -> None:
    progression = [("C:maj", 2), ("C#:dim7", 1), ("D:min7", 1), ("G:7", 2), ("C:maj", 2)]
    key, _, analyses = analyze(progression)
    assert key is not None
    assert key["label"] == "C:maj"
    assert [a["numeral"] for a in analyses] == ["I", "vii°7/ii", "ii7", "V7", "I"]
    assert (analyses[1]["role"], analyses[1]["target"]) == ("secondary_dominant", "ii")


def test_analyze_looks_ahead_to_the_next_segment() -> None:
    progression = [
        ("A:min", 2),
        ("A:maj", 1),
        ("D:min", 1),
        ("A:maj", 1),
        ("N", 1),
        ("D:min", 1),
        ("D:maj", 1),
        ("A:min", 1),
        ("A:maj", 2),
        ("D:maj", 1),
        ("G:7", 1),
    ]
    _, _, analyses = analyze(progression, key="A:min")
    assert [a["numeral"] for a in analyses] == [
        "i", "V/iv", "iv", "I", None, "iv", "IV", "i", "I", "V/VII", "VII7"
    ]  # fmt: skip
    assert [a["role"] for a in analyses] == [
        "diatonic",
        "secondary_dominant",
        "diatonic",
        "borrowed",
        None,
        "diatonic",
        "borrowed",
        "diatonic",
        "borrowed",
        "secondary_dominant",
        "diatonic",
    ]


def _two_beats(*labels: str) -> list[tuple[str, int]]:
    return [(label, 2) for label in labels]


def _spans(regions: list[dict]) -> list[tuple[int, int, str]]:
    return [(r["start_beat"], r["end_beat"], r["label"]) for r in regions]


VERSE = _two_beats("C:maj", "F:maj", "G:maj", "C:maj") * 4
# The issue's ending: E major's I–V–IV–V, then F major's for the last 20 beats.
HALF_STEP_UP = (
    _two_beats("E:maj", "B:maj", "A:maj", "B:maj") * 8
    + _two_beats("F:maj", "C:maj", "A#:maj", "C:maj") * 2
    + [("F:maj", 4)]
)


def test_a_short_tonicization_stays_in_the_key() -> None:
    # The ii–V7/ii vamp and Fm–Bb read 36 better in D minor than in C: less than the two changes
    # cost at 24, more than at 16.
    progression = VERSE + [("D:min", 4), ("A:7", 4)] * 2 + [("F:min", 4), ("A#:maj", 4)] + VERSE
    assert _spans(key_regions(progression)) == [(0, 88, "C:maj")]
    assert _spans(key_regions(progression, penalty=16)) == [
        (0, 32, "C:maj"),
        (32, 56, "D:min"),
        (56, 88, "C:maj"),
    ]


def test_a_half_step_ending_is_its_own_region() -> None:
    # The ending reads 48 in F and 0 in E: kept while the change costs less, and at 48, where it
    # gains only what it costs, not split.
    for penalty in (24, 44):
        assert _spans(key_regions(HALF_STEP_UP, penalty=penalty)) == [
            (0, 64, "E:maj"),
            (64, 84, "F:maj"),
        ]
    assert _spans(key_regions(HALF_STEP_UP, penalty=48)) == [(0, 84, "E:maj")]


E_CYCLE = _two_beats("E:maj", "B:maj", "A:maj", "B:maj")
G_CHORUS = _two_beats("G:maj", "D:maj", "E:min", "G:maj", "C:maj", "B:min", "E:min", "A:min") + [
    ("D:maj", 4)
]
# The issue's song, adrenaline!!!, shortened: E → G → E → G → E → F, on its chords. Each change
# lands where the next key's chords start: on the C–D into the first G (bVI–bVII in E, IV–V in G),
# on the E after a G-major D, and on the F after a B.
ADRENALINE = (
    E_CYCLE * 4
    + _two_beats("C#:min", "G#:min", "A:maj", "B:maj") * 2
    + [("F#:min", 4), *_two_beats("A:maj", "B:maj")]
    + _two_beats("C:maj", "D:maj")
    + [("G:maj", 4), *G_CHORUS * 2]
    + E_CYCLE * 4
    + _two_beats("C:maj", "D:maj")
    + [("G:maj", 4), *G_CHORUS * 4]
    + E_CYCLE * 2
    + _two_beats("F:maj", "C:maj", "A#:maj", "C:maj") * 2
    + [("F:maj", 4)]
)


def test_a_song_through_six_key_regions() -> None:
    _, keys, analyses = analyze(ADRENALINE)
    assert _spans(keys) == [
        (0, 56, "E:maj"),
        (56, 104, "G:maj"),
        (104, 136, "E:maj"),
        (136, 224, "G:maj"),
        (224, 240, "E:maj"),
        (240, 260, "F:maj"),
    ]
    # Every chord is diatonic in its region's key.
    numerals: dict[str, dict[str, str | None]] = {}
    beat = 0
    for (chord, beats), analysis in zip(ADRENALINE, analyses, strict=True):
        region = next(r["label"] for r in keys if r["start_beat"] <= beat < r["end_beat"])
        numerals.setdefault(region, {})[chord] = analysis["numeral"]
        assert analysis["role"] == "diatonic"
        beat += beats
    assert numerals == {
        "E:maj": {
            "E:maj": "I", "B:maj": "V", "A:maj": "IV",
            "C#:min": "vi", "G#:min": "iii", "F#:min": "ii",
        },
        "G:maj": {
            "C:maj": "IV", "D:maj": "V", "G:maj": "I",
            "E:min": "vi", "B:min": "iii", "A:min": "ii",
        },
        "F:maj": {"F:maj": "I", "C:maj": "V", "A#:maj": "IV"},
    }  # fmt: skip


def test_a_change_that_gains_only_the_penalty_never_splits() -> None:
    # 8 beats of a tonic read 24 in its key and 0 in the section's, the penalty exactly. The path
    # with fewer changes wins the tie, at either end and whichever key comes first in KEYS.
    e_section = _two_beats("E:maj", "B:maj", "A:maj", "B:maj") * 8
    f_section = _two_beats("F:maj", "C:maj", "A#:maj", "C:maj") * 8
    assert _spans(key_regions([("E:maj", 8), *f_section])) == [(0, 72, "F:maj")]
    assert _spans(key_regions([*e_section, ("F:maj", 8)])) == [(0, 72, "E:maj")]
    assert _spans(key_regions([*f_section, ("E:maj", 8)])) == [(0, 72, "F:maj")]
    assert _spans(key_regions([*VERSE, ("B:maj", 8)])) == [(0, 40, "C:maj")]


def test_a_relative_minor_chorus_stays_in_the_key() -> None:
    # Am–Dm–E7 reads 56 better in A minor, more than two changes cost, but C major never switches
    # straight to its relative, and D minor reads it only 32 better, less than the two changes there
    # and back.
    progression = VERSE + [("A:min", 4), ("D:min", 2), ("E:7", 2)] * 4 + VERSE
    assert _spans(key_regions(progression)) == [(0, 96, "C:maj")]


def test_an_n_at_a_change_stays_with_the_key_before_it() -> None:
    progression = (
        _two_beats("C:maj", "F:maj", "G:maj", "C:maj") * 6
        + [("N", 4)]
        + _two_beats("D:maj", "G:maj", "A:maj", "D:maj") * 6
    )
    assert _spans(key_regions(progression)) == [(0, 52, "C:maj"), (52, 100, "D:maj")]


def test_a_change_goes_as_late_as_the_weights_allow() -> None:
    # The N and the pivot Em weigh the same in C and G, and so does G–C on either side of them (V–I
    # in C, I–IV in G), so the change scores the same at beat 44, 48, 52, 54 or 58. A tie goes to
    # the latest, the first D.
    progression = (
        _two_beats("C:maj", "F:maj", "G:maj", "C:maj") * 6
        + [("N", 4), ("E:min", 2)]
        + _two_beats("G:maj", "C:maj", "D:maj", "G:maj") * 6
    )
    assert _spans(key_regions(progression)) == [(0, 58, "C:maj"), (58, 102, "G:maj")]


def test_leading_and_trailing_n_join_the_first_and_last_regions() -> None:
    regions = key_regions([("N", 4), *HALF_STEP_UP, ("N", 4)])
    assert _spans(regions) == [(0, 68, "E:maj"), (68, 92, "F:maj")]


def test_an_n_alone_between_relative_keys_stays_with_the_key_before_it() -> None:
    # An N lets the path reach the relative key for two changes (48) and no lost weight: C, the N in
    # a third key, then A minor scores 212, against 210 through D minor, 190 all in C and 164 all in
    # A minor. A G-major bridge over the verse's last G–C also scores 212 with two changes; the
    # later change wins the tie. The estimator cannot name the N's key, so the N stays with C.
    progression = VERSE * 2 + [("N", 4)] + [("A:min", 4), ("D:min", 2), ("E:7", 2)] * 5
    assert _spans(key_regions(progression)) == [(0, 68, "C:maj"), (68, 108, "A:min")]


def test_key_regions_without_a_chord() -> None:
    assert key_regions([("N", 4), ("N", 2)]) == []


def test_a_region_is_named_by_the_estimator() -> None:
    # The path stays in C major, the earlier of two keys that score the same; the estimator's
    # tie-breaks name the region A minor, as they name the whole song.
    progression = [("A:min7", 4), ("C:maj7", 4)] * 4
    key, keys, _ = analyze(progression)
    assert key is not None
    assert key["label"] == estimate_key(progression)[0] == "A:min"
    assert keys == key_regions(progression) == [{"start_beat": 0, "end_beat": 32, "label": "A:min"}]


def test_a_given_key_is_one_region() -> None:
    _, keys, analyses = analyze(HALF_STEP_UP, key="C:maj")
    assert keys == [{"start_beat": 0, "end_beat": 84, "label": "C:maj"}]
    assert [a["numeral"] for a in analyses[-5:]] == ["IV", "I", "bVII", "I", "IV"]


def test_each_chord_is_analyzed_in_its_region_key() -> None:
    key, _, analyses = analyze(HALF_STEP_UP)
    numerals = [a["numeral"] for a in analyses]
    assert numerals[:-9] == ["I", "V", "IV", "V"] * 8
    # In E these would read bII bVI #IV bVI.
    assert numerals[-9:] == ["I", "V", "IV", "V", "I", "V", "IV", "V", "I"]
    assert key == {
        "label": "E:maj",
        "source": "estimated",
        "candidates": estimate_key(HALF_STEP_UP)[:3],
    }
