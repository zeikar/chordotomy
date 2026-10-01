import importlib.util
from pathlib import Path

import numpy as np
import pytest

from chordotomy.chords import LABELS
from chordotomy.model import QUALITY, available, beat_scores, beat_states, fold, to_label

# The submission dictionary's 26 entries on Eb, as the decoder spells them, and the v4 label each
# maps to. Literal, deliberately not built from the module's table.
SUBMISSION_ON_EB = {
    "Eb:min/b7": "D#:min",
    "Eb:min/2": "D#:min",
    "Eb:maj/b7": "D#:maj",
    "Eb:maj/2": "D#:maj",
    "Eb:sus4(b7)": "D#:sus4",
    "Eb:sus2": "D#:maj",
    "Eb:sus4": "D#:sus4",
    "Eb:13": "D#:7",
    "Eb:11": "D#:7",
    "Eb:min9": "D#:min7",
    "Eb:9": "D#:7",
    "Eb:maj9": "D#:maj7",
    "Eb:dim7": "D#:dim7",
    "Eb:hdim7": "D#:hdim7",
    "Eb:min7": "D#:min7",
    "Eb:7": "D#:7",
    "Eb:maj7": "D#:maj7",
    "Eb:min/5": "D#:min",
    "Eb:min/b3": "D#:min",
    "Eb:maj/5": "D#:maj",
    "Eb:maj/3": "D#:maj",
    "Eb:dim": "D#:dim7",
    "Eb:aug": "D#:maj",
    "Eb:min": "D#:min",
    "Eb:maj": "D#:maj",
    "N": "N",
}


@pytest.mark.parametrize(("name", "label"), SUBMISSION_ON_EB.items())
def test_to_label_maps_the_dictionary_onto_v4(name: str, label: str) -> None:
    assert to_label(name) == label


def test_to_label_respells_flat_roots_and_keeps_sharp_ones() -> None:
    assert to_label("Ab:7") == "G#:7"
    assert to_label("Bb:min/b3") == "A#:min"
    assert to_label("C#:maj7") == "C#:maj7"
    assert to_label("F#:hdim7") == "F#:hdim7"
    assert to_label("C:maj") == "C:maj"


@pytest.mark.skipif(not available(), reason="the model extra is not installed")
def test_every_dictionary_quality_is_mapped() -> None:
    # Located without importing lv_chordia, whose package import loads torch.
    package = Path(importlib.util.find_spec("lv_chordia").submodule_search_locations[0])
    names = (package / "data" / "submission_chord_list.txt").read_text().split()
    qualities = {name.split(":")[1].partition("/")[0] for name in names if name != "N"}
    assert qualities == set(QUALITY)
    assert all(to_label(name) in LABELS for name in names)


def test_fold_sums_the_probability_of_every_name_on_a_label() -> None:
    names = ["Eb:maj/3", "C:min9", "Eb:sus2"]
    probability = np.array([[0.1, 0.2, 0.3], [0.4, 0.05, 0.01]])

    scores = fold(names, np.log(probability))

    assert scores.shape == (109, 2)
    d_sharp, c_min7 = LABELS.index("D#:maj"), LABELS.index("C:min7")
    np.testing.assert_allclose(scores[d_sharp], np.log([0.1 + 0.3, 0.4 + 0.01]))
    np.testing.assert_allclose(scores[c_min7], np.log([0.2, 0.05]))
    assert np.isneginf(scores[LABELS.index("G:min6")]).all()
    assert np.isneginf(np.delete(scores, [d_sharp, c_min7], axis=0)).all()


def test_beat_states_take_the_majority_and_break_ties_to_the_lowest_label() -> None:
    g, a_min, n = LABELS.index("G:maj"), LABELS.index("A:min"), LABELS.index("N")
    frame_states = np.array([g, g, a_min, n, a_min, a_min, n])

    states = beat_states(frame_states, [0, 3, 7])

    assert [LABELS[s] for s in states] == ["G:maj", "A:min"]


def test_beat_scores_are_the_mean_over_each_beat() -> None:
    frame_scores = np.array([[0.0, 2.0, 4.0, 6.0, 8.0], [1.0, 3.0, -1.0, -2.0, -3.0]])

    scores = beat_scores(frame_scores, [0, 2, 5])

    np.testing.assert_allclose(scores, [[1.0, 6.0], [2.0, -2.0]])
