"""Beat This!'s activation on the real net; skipped unless the model extra and its weights are here.

The suite never downloads: `chordotomy fetch-weights` puts the checkpoint in the cache first.
"""

import contextlib
import hashlib
import importlib.util

import numpy as np
import pytest

from chordotomy import beats, model
from chordotomy.features import HOP, SR, NoBeatsError
from chordotomy.model import EngineError

# find_spec rather than importorskip: collecting the file then imports neither beat_this nor torch.
if importlib.util.find_spec("beat_this") is None or not beats.verified():
    pytest.skip(
        "the model extra or the Beat This! weights are not installed", allow_module_level=True
    )

# Bound at import, before conftest's stubs replace them in each test.
REAL_AVAILABLE = model.available
REAL_ACTIVATION = beats.activation

CYCLE = ("C:maj", "F:maj", "G:maj", "A:min", "D:min", "E:min")


@pytest.fixture(autouse=True)
def beat_this_engine(monkeypatch):
    """Undo conftest's stubs, and fail any download."""
    monkeypatch.setattr(model, "available", REAL_AVAILABLE)
    monkeypatch.setattr(beats, "activation", REAL_ACTIVATION)
    monkeypatch.setattr(beats, "urlopen", lambda *a, **k: pytest.fail("the suite downloaded"))


@pytest.fixture
def fresh_tracker():
    """Load the net anew in the test, and again after it, so a patched load does not stick."""
    beats._tracker.cache_clear()
    yield
    beats._tracker.cache_clear()


def _picked(logits: np.ndarray) -> bool:
    """Whether Beat This!'s own peak picking, Postprocessor("minimal"), finds a beat."""
    import torch
    from beat_this.model.postprocessor import Postprocessor

    beat = torch.from_numpy(np.ascontiguousarray(logits, dtype=np.float32))
    found, _ = Postprocessor("minimal")(beat, beat)
    return len(found) > 0


def test_the_spectrogram_matches_beat_this(mix) -> None:
    pytest.importorskip("torchaudio")
    import torch
    from beat_this.preprocessing import LogMelSpect

    y = mix([("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4), ("C:maj", 4)])  # 10 s

    mel = beats._log_mel(y)

    ref = LogMelSpect()(torch.from_numpy(y)).numpy()
    assert mel.shape == ref.shape == (1 + len(y) // beats.MEL_HOP, beats.N_MELS)
    # Measured: 1.9e-5, on values up to 6.8.
    assert np.abs(mel - ref).max() < 1e-3


@pytest.mark.parametrize(("clip", "found"), [("syncopated", True), ("silence", False)])
def test_the_gate_agrees_with_beat_this_peak_picking(syncopated, clip, found) -> None:
    y = syncopated(8, 8, 86) if clip == "syncopated" else np.zeros(4 * SR, dtype=np.float32)

    logits = beats.logits(y)

    assert beats.has_peaks(logits) is found
    assert _picked(logits) is found


def test_the_shortest_clip_the_spectrogram_takes_runs(synth) -> None:
    # The first length that reaches torch.stft: beats or none, never its RuntimeError.
    y = synth([("C:maj", 8)])[: beats.N_FFT // 2 + 1]

    with contextlib.suppress(NoBeatsError):
        assert beats.activation(y).shape == (1 + len(y) // HOP,)


def test_digital_silence_has_no_beats() -> None:
    with pytest.raises(NoBeatsError):
        beats.activation(np.zeros(4 * SR, dtype=np.float32))


def test_the_gate_agrees_at_its_edge(synth) -> None:
    # One strike per bar of 4 beats at 90 BPM, held: a few frames stand far above the rest.
    y = synth([(CYCLE[i % len(CYCLE)], 1) for i in range(12)], bpm=90 / 4, decay=2.0)
    logits = beats.logits(y)

    for above in (0, 1, 3):
        # Shifted so that exactly `above` frames stay above 0.
        shifted = logits - np.sort(logits)[-1 - above]
        assert np.sum(shifted > 0) == above
        assert beats.has_peaks(shifted) is _picked(shifted) is (above > 0), above


@pytest.mark.parametrize("length", [4 * SR + 1, 5 * SR + 300, 6 * SR + 511])
def test_the_activation_has_the_frames_of_the_beat_grid(drums, length) -> None:
    activation = beats.activation(drums(16)[:length])

    assert activation.shape == (1 + length // HOP,)
    assert activation.dtype == np.float64
    assert activation.min() >= 0
    assert activation.max() <= 1


def test_logits_are_chunked_as_beat_this_chunks_them(mix, monkeypatch) -> None:
    pytest.importorskip("torchaudio")
    import torch
    from beat_this.inference import split_predict_aggregate

    y = mix([("C:maj", 6), ("A:min", 6), ("F:maj", 6), ("G:7", 6)])  # 12 s, 601 frames
    # Three chunks, the last one moved back to end at the piece's end, overlapping the second.
    monkeypatch.setattr(beats, "CHUNK_FRAMES", 300)

    logits = beats.logits(y)

    with torch.inference_mode():
        ref = split_predict_aggregate(
            torch.from_numpy(beats._log_mel(y)),
            chunk_size=300,
            border_size=beats.BORDER_FRAMES,
            overlap_mode="keep_first",
            model=beats._tracker(beats.CHECKPOINT),
        )["beat"].numpy()
    # Measured: 0.0. Compared with the default chunks instead, the logits differ by up to 6.8 on
    # nearly every frame: the transformer attends over its whole chunk, so the context changes
    # each frame's output, not only the borders'. Hence the reference is beat_this's own chunking.
    np.testing.assert_allclose(logits, ref, atol=1e-4)


def test_the_net_runs_on_the_cpu_even_when_cuda_is_reported(
    drums, monkeypatch, fresh_tracker
) -> None:
    monkeypatch.setattr("torch.cuda.device_count", lambda: 1)

    beats.activation(drums(8))

    net = beats._tracker(beats.CHECKPOINT)
    assert {t.device.type for t in [*net.parameters(), *net.buffers()]} == {"cpu"}


def test_a_checkpoint_that_cannot_be_loaded_is_an_engine_error(
    drums, tmp_path, monkeypatch, fresh_tracker
) -> None:
    garbage = b"not a checkpoint" * 64
    monkeypatch.setattr(beats, "CACHE_DIR", tmp_path)
    # Pinned to the garbage itself, so fetch takes it as verified rather than downloading.
    pin = (hashlib.sha256(garbage).hexdigest(), len(garbage))
    monkeypatch.setattr(beats, "CHECKPOINTS", {beats.CHECKPOINT: pin})
    beats.checkpoint_path().write_bytes(garbage)

    with pytest.raises(EngineError) as info:
        beats.activation(drums(8))

    message = str(info.value)
    for part in (str(beats.checkpoint_path()), "--reinstall-package beat-this", "--engine dsp"):
        assert part in message
    assert "\n" not in message
