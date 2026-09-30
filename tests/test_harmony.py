import pytest

from chordotomy.harmony import estimate_key, parse_key


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
