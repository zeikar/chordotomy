import numpy as np

from chordotomy.chords import LABELS, match, smooth

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


def _sims(overrides: dict[int, dict[str, float]]) -> np.ndarray:
    """(37, 6) similarities: 0.6 everywhere, C:maj 0.95 / C:7 0.85 unless overridden per beat."""
    sims = np.full((len(LABELS), 6), 0.6)
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
