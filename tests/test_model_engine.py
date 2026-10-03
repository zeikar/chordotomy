"""The lv-chordia engine end to end; skipped unless the model extra is installed."""

import importlib.metadata
import importlib.util
import json
import re

import numpy as np
import pytest
import soundfile
from typer.testing import CliRunner

from chordotomy import beats, evaluate, model
from chordotomy.chords import LABELS, ROOTS
from chordotomy.cli import app
from chordotomy.features import HOP, SR
from chordotomy.timeline import analyze

# find_spec rather than importorskip: collecting the file then imports neither lv_chordia nor torch.
if importlib.util.find_spec("lv_chordia") is None:
    pytest.skip("the model extra is not installed", allow_module_level=True)

# Bound at import, before conftest's dsp_engine replaces them in each test.
REAL_AVAILABLE = model.available
REAL_ACTIVATION = beats.activation


@pytest.fixture(autouse=True)
def model_engine(monkeypatch):
    """Undo conftest's dsp_engine: here the CLI sees the installed model."""
    monkeypatch.setattr(model, "available", REAL_AVAILABLE)


@pytest.fixture
def beat_this_weights(monkeypatch):
    """Undo conftest's stub of Beat This!'s activation, for a test that runs the whole engine.

    Skipped unless the weights are already in the cache: the suite never downloads them.
    """
    if not beats.verified():
        pytest.skip("the Beat This! weights are not in the cache; see `chordotomy fetch-weights`")
    monkeypatch.setattr(beats, "activation", REAL_ACTIVATION)


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


def test_the_model_engine_writes_its_chords_and_version(
    mix, chord_at, tmp_path, beat_this_weights
) -> None:
    progression = [("C:maj", 4), ("A:min", 4), ("F:maj", 4), ("G:7", 4)]

    result = analyze(_write(tmp_path, mix(progression)), engine="model")

    assert result["schema_version"] == 9
    assert {s["bass"] for s in result["segments"]} <= {None, *ROOTS}
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


def test_recognize_returns_the_bass_head(synth) -> None:
    y = synth([("C:maj", 8)])

    _, _, bass = model.recognize(y)

    assert bass.shape == (1 + len(y) // HOP, 13)
    assert np.allclose(bass.sum(axis=1), 1, atol=1e-4)


def test_chunked_inference_stitches_into_the_same_chords(
    synth, tmp_path, monkeypatch, beat_this_weights
) -> None:
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
    # Measured: all 41 beats.
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


def test_analyze_with_the_model_engine_says_which_engine_runs(
    synth, tmp_path, beat_this_weights
) -> None:
    clip = _write(tmp_path, synth([("C:maj", 8)]))
    out = tmp_path / "out.json"
    installed = importlib.metadata.version("lv-chordia")

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--engine", "model"])

    assert result.exit_code == 0, result.output
    assert f"engine: lv-chordia {installed}" in result.stderr
    assert json.loads(out.read_text())["generator"]["engine"] == {
        "name": "lv-chordia",
        "version": installed,
    }


def test_evaluate_with_the_model_engine_prints_a_row(
    synth, tmp_path, monkeypatch, beat_this_weights
) -> None:
    pytest.importorskip("mir_eval")
    pytest.importorskip("pooch")
    clip = _write(tmp_path, synth([("C:maj", 8)]))
    arff = tmp_path / "0001_beatinfo.arff"
    arff.write_text("".join(f"{i * 0.5},1,{i % 4 + 1},'Cmaj'\n" for i in range(8)))
    # One synthesized track in place of the dataset, so nothing is downloaded.
    monkeypatch.setattr(evaluate, "tiny_aam_tracks", lambda limit: [("0001", clip, arff)])

    result = CliRunner().invoke(app, ["evaluate", "tiny-aam", "--engine", "model"])

    assert result.exit_code == 0, result.output
    assert "engine: lv-chordia" in result.stderr
    assert any(line.startswith("0001") for line in result.stdout.splitlines())


def test_a_missing_dictionary_is_an_engine_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(model.importlib.resources, "files", lambda package: tmp_path)

    with pytest.raises(model.EngineError, match=r"_chord_list\.txt.*uv sync --extra model"):
        model._decoder()
