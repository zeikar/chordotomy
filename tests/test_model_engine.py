"""The lv-chordia engine end to end; skipped unless the model extra is installed."""

import importlib.metadata
import importlib.util
import re

import pytest
import soundfile

from chordotomy import model
from chordotomy.chords import LABELS
from chordotomy.features import HOP, SR
from chordotomy.timeline import analyze

# find_spec rather than importorskip: collecting the file then imports neither lv_chordia nor torch.
if importlib.util.find_spec("lv_chordia") is None:
    pytest.skip("the model extra is not installed", allow_module_level=True)


def _write(tmp_path, y):
    path = tmp_path / "clip.wav"
    soundfile.write(path, y, SR)
    return path


def _per_beat(result: dict) -> list[str]:
    return [s["chord"] for s in result["segments"] for _ in range(s["start_beat"], s["end_beat"])]


@pytest.fixture
def fresh_networks():
    """Load the nets anew in the test, and again after it, so a patched load does not stick."""
    model._networks.cache_clear()
    yield
    model._networks.cache_clear()


def test_the_model_engine_writes_its_chords_and_version(mix, chord_at, tmp_path) -> None:
    progression = [("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4)]

    result = analyze(_write(tmp_path, mix(progression)), engine="model")

    assert result["schema_version"] == 6
    assert result["generator"]["engine"] == {
        "name": "lv-chordia",
        "version": importlib.metadata.version("lv-chordia"),
    }
    segments = result["segments"]
    for s in segments:
        assert len(set(s["candidates"])) == 3
        assert set(s["candidates"]) <= set(LABELS)
    beats = result["beats"]
    correct = total = 0
    for s in segments:
        for i in range(s["start_beat"], s["end_beat"]):
            end = beats[i + 1] if i + 1 < len(beats) else result["source"]["duration"]
            midpoint = (beats[i] + end) / 2
            if midpoint >= 8.0:
                continue
            total += 1
            correct += s["chord"].split(":")[0] == chord_at(progression, midpoint).split(":")[0]
    # Measured: 16 of 17.
    assert correct >= 14, (correct, total)


def _raise(*args, **kwargs):
    raise RuntimeError("PytorchStreamReader failed reading zip archive")


@pytest.mark.parametrize(
    "load",
    [_raise, lambda *args, **kwargs: {}, lambda *args, **kwargs: None],
    ids=["unreadable", "empty", "none"],
)
def test_a_damaged_checkpoint_is_an_engine_error(synth, monkeypatch, fresh_networks, load) -> None:
    monkeypatch.setattr("torch.load", load)

    with pytest.raises(model.EngineError, match=r"\.sdict.*uv sync --extra model"):
        model.recognize(synth([("C:maj", 8)]))


def test_a_missing_checkpoint_is_an_engine_error(synth, monkeypatch, fresh_networks, tmp_path):
    # NetworkInterface would build an untrained net without a word.
    monkeypatch.setattr("lv_chordia.mir.common.CACHE_DATA_PATH", str(tmp_path))

    with pytest.raises(
        model.EngineError, match=rf"\.sdict is missing from {re.escape(str(tmp_path))}"
    ):
        model.recognize(synth([("C:maj", 8)]))


def test_chunked_inference_stitches_into_the_same_chords(synth, tmp_path, monkeypatch) -> None:
    progression = [("C:maj", 4, 36), ("A:min", 4, 45), ("F:maj", 4, 41), ("G:7", 4, 43)] * 2
    y = synth([*progression, ("C:maj", 4, 36), ("D:min7", 4, 38)])
    path = _write(tmp_path, y)
    plain = _per_beat(analyze(path, engine="model"))

    windows = []

    def spy(inference):
        def run(cqt):
            windows.append(len(cqt))
            return inference(cqt)

        return run

    for interface in model._networks():
        monkeypatch.setattr(interface, "inference", spy(interface.inference))
    monkeypatch.setattr(model, "CHUNK_SECONDS", 6)

    chunked = _per_beat(analyze(path, engine="model"))

    assert len(windows) > len(model._networks())
    assert max(windows) * HOP < len(y)
    # Measured: all 40 beats.
    assert sum(a == b for a, b in zip(plain, chunked, strict=True)) >= len(plain) - 2


def test_the_nets_run_on_the_cpu_even_when_cuda_is_reported(
    synth, monkeypatch, fresh_networks
) -> None:
    # On a machine without CUDA, a net left on use_gpu would fail moving itself to the GPU.
    monkeypatch.setattr("torch.cuda.device_count", lambda: 1)

    model.recognize(synth([("C:maj", 8)]))

    for interface in model._networks():
        assert interface.net.use_gpu is False
        assert {p.device.type for p in interface.net.parameters()} == {"cpu"}
