import json

import pytest

from chordotomy.chords import QUALITIES
from chordotomy.harmony import analyze, analyze_chord, estimate_key, parse_key


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
        # The scale test admits the diminished triads as they are.
        ("B:dim", "C:maj", "vii°", "dominant"),
        ("B:dim", "A:min", "ii°", "predominant"),
        ("C:sus2", "C:maj", "Isus2", "tonic"),
        ("G:sus2", "C:maj", "Vsus2", "dominant"),
        ("D:sus2", "C:maj", "IIsus2", "predominant"),
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
        ("A:7", "A:min", "V7/iv", "iv"),
        ("D:7", "A:min", "V7/VII", "VII"),
        ("C:7", "A:min", "V7/VI", "VI"),
        ("B:7", "A:min", "V7/V", "V"),
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
        ("D:7", "A:min", "N", "V7/VII", "secondary_dominant"),
        ("A#:maj", "C:maj", "D#:maj", "bVII", "borrowed"),
        ("D:maj7", "A:min", "G:maj", "IVmaj7", "borrowed"),
        ("B:hdim7", "A:min", "C:maj", "iiø7", "diatonic"),
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
        ("F:7", "C:maj", "IV7"),
        # The seventh is outside C minor, so these are not borrowed.
        ("D#:7", "C:maj", "bIII7"),
        ("G#:7", "C:maj", "bVI7"),
        ("A#:maj7", "C:maj", "bVIImaj7"),
        ("G#:min", "C:maj", "bvi"),
        ("B:min", "C:maj", "vii"),
        # The leading tone counts only in the dominant and the diminished seventh on it.
        ("F:min", "A:min", "vi"),
        # With no chord to lead into, a leading-tone chord is only its degree.
        ("F#:hdim7", "C:maj", "#ivø7"),
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
        # An augmented triad is in neither mode of C, on any root.
        ("G:aug", "C:maj", "V+"),
        ("C:aug", "C:maj", "I+"),
        # A diminished triad's root is raised too.
        ("C#:dim", "C:maj", "#i°"),
        ("D#:dim", "C:maj", "#ii°"),
        ("E:sus2", "C:maj", "IIIsus2"),
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
    key, analyses = analyze(PROGRESSION)
    assert key is not None
    assert key["label"] == "C:maj"
    assert key["source"] == "estimated"
    assert len(key["candidates"]) == 3
    assert len(set(key["candidates"])) == 3
    assert key["candidates"][0] == key["label"]
    assert [a["numeral"] for a in analyses] == ["I", "vi", "V7/V", "V7", None, "I"]
    json.dumps((key, analyses))


def test_analyze_given_key_keeps_the_estimated_candidates() -> None:
    estimated, _ = analyze(PROGRESSION)
    key, analyses = analyze(PROGRESSION, key="A:min")
    assert estimated is not None
    assert key == {
        "label": "A:min",
        "source": "given",
        "candidates": estimated["candidates"],
    }
    assert [a["numeral"] for a in analyses] == ["III", "i", "V7/VII", "VII7", None, "III"]


def test_analyze_without_a_chord() -> None:
    assert analyze([("N", 4)]) == (None, [NO_ANALYSIS])
    assert analyze([("N", 4)], key="C:maj") == (
        {"label": "C:maj", "source": "given", "candidates": []},
        [NO_ANALYSIS],
    )


def test_analyze_labels_a_leading_tone_chord_by_the_next_segment() -> None:
    progression = [("C:maj", 2), ("C#:dim7", 1), ("D:min7", 1), ("G:7", 2), ("C:maj", 2)]
    key, analyses = analyze(progression)
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
    _, analyses = analyze(progression, key="A:min")
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
