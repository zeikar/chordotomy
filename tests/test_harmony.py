import pytest

from chordotomy.harmony import analyze_chord, estimate_key, parse_key


@pytest.mark.parametrize(
    ("text", "expected"),
    [("C:maj", "C:maj"), ("A:min", "A:min"), ("Bb:maj", "A#:maj"), ("Db:min", "C#:min")],
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
        ("D:maj", "G:maj", "V/VII", "secondary_dominant", "VII"),
        *[("D:maj", f, "IV", "borrowed", None) for f in ("G:7", "A:min", "N", None)],
    ],
)
def test_overlap_resolves_only_on_the_target_triad(
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
    ],
)
def test_following_is_ignored_outside_the_overlap(
    label: str, key: str, following: str, numeral: str, role: str
) -> None:
    result = analyze_chord(label, key, following)
    assert result == analyze_chord(label, key)
    assert (result["numeral"], result["role"]) == (numeral, role)


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
        ("G#:min", "C:maj", "bvi"),
        ("B:min", "C:maj", "vii"),
        # The leading tone counts only in the dominant.
        ("F:min", "A:min", "vi"),
    ],
)
def test_analyze_chord_chromatic(label: str, key: str, numeral: str) -> None:
    assert analyze_chord(label, key) == {
        "numeral": numeral,
        "role": "chromatic",
        "function": None,
        "target": None,
    }
