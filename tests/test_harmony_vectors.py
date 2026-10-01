import json

from harmony_vectors import PATH, cases

from chordotomy.chords import LABELS, QUALITIES
from chordotomy.harmony import KEYS


def _fixture() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_fixture_matches_python() -> None:
    # Through JSON, as the file holds it: the progression tuples become lists.
    expected = json.loads(json.dumps(cases()))
    assert _fixture() == expected, (
        "tests/harmony_vectors.json no longer matches the Python analysis; "
        "regenerate it with `uv run python tests/harmony_vectors.py`"
    )


def test_fixture_covers_the_vocabulary_and_keys() -> None:
    fixture = _fixture()
    progressions = fixture["progressions"]
    assert {label for case in progressions for label, _ in case["progression"]} == set(LABELS)
    keys = {case["expected"]["key"]["label"] for case in progressions if case["expected"]["key"]}
    assert keys == set(KEYS)
    qualities = {label.split(":")[1] for label, _, _ in fixture["inversions"] if label != "N"}
    assert qualities == set(QUALITIES)
