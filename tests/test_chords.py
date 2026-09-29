import numpy as np

from chordotomy.chords import LABELS, match

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
