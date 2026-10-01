import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from chordotomy import model
from chordotomy.chords import LABELS
from chordotomy.features import HOP, SR
from chordotomy.model import QUALITY, available, beat_scores, beat_states, fold, to_label

# The submission dictionary's 26 entries on Eb, as the decoder spells them, and the v5 label each
# maps to. Literal, deliberately not built from the module's table.
SUBMISSION_ON_EB = {
    "Eb:min/b7": "D#:min",
    "Eb:min/2": "D#:min",
    "Eb:maj/b7": "D#:maj",
    "Eb:maj/2": "D#:maj",
    "Eb:sus4(b7)": "D#:sus4",
    "Eb:sus2": "D#:sus2",
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
    "Eb:dim": "D#:dim",
    "Eb:aug": "D#:aug",
    "Eb:min": "D#:min",
    "Eb:maj": "D#:maj",
    "N": "N",
}


@pytest.mark.parametrize(("name", "label"), SUBMISSION_ON_EB.items())
def test_to_label_maps_the_dictionary_onto_v5(name: str, label: str) -> None:
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
    names = ["Eb:maj/3", "C:min9", "Eb:maj/5", "Eb:aug"]
    probability = np.array([[0.1, 0.2, 0.3, 0.15], [0.4, 0.05, 0.01, 0.02]])

    scores = fold(names, np.log(probability))

    assert scores.shape == (145, 2)
    d_sharp, c_min7 = LABELS.index("D#:maj"), LABELS.index("C:min7")
    d_sharp_aug = LABELS.index("D#:aug")
    np.testing.assert_allclose(scores[d_sharp], np.log([0.1 + 0.3, 0.4 + 0.01]))
    np.testing.assert_allclose(scores[c_min7], np.log([0.2, 0.05]))
    np.testing.assert_allclose(scores[d_sharp_aug], np.log([0.15, 0.02]))
    assert np.isneginf(scores[LABELS.index("G:min6")]).all()
    assert np.isneginf(np.delete(scores, [d_sharp, c_min7, d_sharp_aug], axis=0)).all()


def test_beat_states_take_the_majority_and_break_ties_to_the_lowest_label() -> None:
    g, a_min, n = LABELS.index("G:maj"), LABELS.index("A:min"), LABELS.index("N")
    frame_states = np.array([g, g, a_min, n, a_min, a_min, n])

    states = beat_states(frame_states, [0, 3, 7])

    assert [LABELS[s] for s in states] == ["G:maj", "A:min"]


def test_beat_scores_are_the_mean_over_each_beat() -> None:
    frame_scores = np.array([[0.0, 2.0, 4.0, 6.0, 8.0], [1.0, 3.0, -1.0, -2.0, -3.0]])

    scores = beat_scores(frame_scores, [0, 2, 5])

    np.testing.assert_allclose(scores, [[1.0, 6.0], [2.0, -2.0]])


@pytest.mark.parametrize("length", [4 * SR + 1, 5 * SR + 300, 6 * SR + 511])
def test_the_model_cqt_has_the_frames_of_the_beat_grid(length) -> None:
    # The DSP's CQTs and beat tracker frame the signal centred at HOP, 1 + length // HOP frames.
    y = (np.random.default_rng(0).standard_normal(length) * 0.1).astype(np.float32)

    assert model._cqt(y).shape == (1 + length // HOP, 288)


class _IndexNet:
    """A stand-in net: every head gives each input frame's index plus a shift, and the call number.

    The index is read from the input's first bin, so the stitched output shows which input row
    each frame came from, and the call number which window.
    """

    def __init__(self, shift: float) -> None:
        self.shift = shift
        self.windows = []  # (first, end) frame of each input

    def inference(self, cqt: np.ndarray) -> tuple[np.ndarray, ...]:
        index = cqt[:, 0]
        self.windows.append((int(index[0]), int(index[-1]) + 1))
        out = np.column_stack([index + self.shift, np.full(len(index), len(self.windows) - 1)])
        return (out,) * 6


CHUNK = int(model.CHUNK_SECONDS * SR / HOP)
OVERLAP = round(model.OVERLAP_SECONDS * SR / HOP)


@pytest.mark.parametrize("n", [1, CHUNK - 1, CHUNK, CHUNK + 1, 2 * CHUNK + 1])
def test_chunked_inference_keeps_every_frame_once_with_its_context(monkeypatch, n) -> None:
    nets = (_IndexNet(0.0), _IndexNet(1.0))
    monkeypatch.setattr(model, "_networks", lambda: nets)
    cqt = np.zeros((n, 288), dtype=np.float32)
    cqt[:, 0] = np.arange(n)

    heads = model._probabilities(cqt)

    windows = np.array(nets[0].windows)
    assert len(windows) == math.ceil(n / CHUNK)
    assert np.all(windows[:, 1] - windows[:, 0] <= CHUNK + 2 * OVERLAP)
    frames = np.arange(n)
    assert len(heads) == 6
    for head in heads:
        # Each frame once, in order, from its own input row, averaged over the two nets.
        np.testing.assert_array_equal(head[:, 0], frames + 0.5)
        # Kept only where its window holds OVERLAP frames either side of it, or the track's edge.
        first, end = windows[head[:, 1].astype(int)].T
        assert np.all(first <= np.maximum(frames - OVERLAP, 0))
        assert np.all(end >= np.minimum(frames + OVERLAP + 1, n))
