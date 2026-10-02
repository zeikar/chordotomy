import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys

import numpy as np
import pytest
import soundfile
from conftest import librosa_activation
from typer.testing import CliRunner

import chordotomy.beats
import chordotomy.model
import chordotomy.timeline
from chordotomy import __version__
from chordotomy.cli import app
from chordotomy.features import SR

# Bound at import, before conftest's dsp_engine replaces chordotomy.model.available in each test.
REAL_AVAILABLE = chordotomy.model.available
ENGINE_FAILURE = (
    "lv_chordia cannot be imported (No module named 'audioop'); install the model extra with "
    "`uv sync --extra model`, or pass --engine dsp"
)


@pytest.fixture
def clip(synth, tmp_path):
    path = tmp_path / "clip.wav"
    soundfile.write(path, synth([("C:maj", 8)]), SR)
    return path


def test_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"chordotomy {__version__}"


def test_analyze_writes_the_timeline(clip, tmp_path) -> None:
    out = tmp_path / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out)])

    assert result.exit_code == 0
    assert "Wrote" in result.stdout
    data = json.loads(out.read_text())
    assert data["schema_version"] == 8
    assert data["source"]["path"] == str(clip)


def test_key_overrides_the_estimate(clip, tmp_path) -> None:
    out = tmp_path / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--key", "A:min"])

    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert data["key"]["label"] == "A:min"
    assert data["key"]["source"] == "given"
    assert data["key"]["candidates"][0] == "C:maj"
    assert {s["numeral"] for s in data["segments"]} == {"III"}


def test_flat_key_is_spelled_with_sharps(clip, tmp_path) -> None:
    out = tmp_path / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--key", "Bb:maj"])

    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert data["key"]["label"] == "A#:maj"
    assert {s["numeral"] for s in data["segments"]} == {"V/V"}
    assert {s["role"] for s in data["segments"]} == {"secondary_dominant"}


def test_bad_key_is_a_usage_error(clip, tmp_path) -> None:
    out = tmp_path / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--key", "Cm"])

    assert result.exit_code == 2
    assert "--key" in result.stderr
    assert "not a key" in result.stderr
    assert not out.exists()


def test_default_output_is_not_overwritten_without_force(clip, tmp_path) -> None:
    runner = CliRunner()
    out = tmp_path / "clip.chords.json"

    assert runner.invoke(app, ["analyze", str(clip)]).exit_code == 0
    assert out.exists()
    mode = out.stat().st_mode

    out.write_text("hand-corrected")
    result = runner.invoke(app, ["analyze", str(clip)])
    assert result.exit_code == 1
    assert "--force" in result.stderr
    assert out.read_text() == "hand-corrected"

    assert runner.invoke(app, ["analyze", str(clip), "--force"]).exit_code == 0
    json.loads(out.read_text())
    # The forced write goes through a temp file; it must not end up with different permissions.
    assert out.stat().st_mode == mode


def test_file_appearing_during_analysis_is_not_overwritten(clip, tmp_path, monkeypatch) -> None:
    out = tmp_path / "out.json"

    def stub(path, key=None, engine=None):
        out.write_text("sentinel")
        return {"schema_version": 1}

    monkeypatch.setattr(chordotomy.timeline, "analyze", stub)
    runner = CliRunner()

    result = runner.invoke(app, ["analyze", str(clip), "-o", str(out)])
    assert result.exit_code == 1
    assert "--force" in result.stderr
    assert out.read_text() == "sentinel"

    assert runner.invoke(app, ["analyze", str(clip), "-o", str(out), "--force"]).exit_code == 0
    assert json.loads(out.read_text()) == {"schema_version": 1}


@pytest.mark.parametrize("force", [False, True])
def test_timeline_is_written_as_utf8(clip, tmp_path, monkeypatch, force) -> None:
    out = tmp_path / "out.json"
    data = {
        "source": {"path": "노래.wav"},
        "segments": [{"numeral": "viiø7/V"}, {"numeral": "vii°7/ii"}],
    }
    monkeypatch.setattr(chordotomy.timeline, "analyze", lambda path, key=None, engine=None: data)

    args = ["analyze", str(clip), "-o", str(out)] + (["--force"] if force else [])
    result = CliRunner().invoke(app, args)

    assert result.exit_code == 0
    raw = out.read_bytes()
    for text in ("노래.wav", "viiø7/V", "vii°7/ii"):
        assert text.encode("utf-8") in raw
    assert b"\\u" not in raw
    assert json.loads(out.read_text(encoding="utf-8")) == data


@pytest.mark.parametrize("force", [False, True])
def test_an_undecodable_path_is_written_as_an_escape(clip, tmp_path, monkeypatch, force) -> None:
    # A filename that is not UTF-8 decodes with a surrogate on Linux, and UTF-8 cannot encode it.
    out = tmp_path / "out.json"
    data = {"source": {"path": "caf\udce9.wav"}}
    monkeypatch.setattr(chordotomy.timeline, "analyze", lambda path, key=None, engine=None: data)

    args = ["analyze", str(clip), "-o", str(out)] + (["--force"] if force else [])
    result = CliRunner().invoke(app, args)

    assert result.exit_code == 0
    assert b'"caf\\udce9.wav"' in out.read_bytes()
    assert json.loads(out.read_text(encoding="utf-8")) == data


def test_undecodable_audio_is_an_error(tmp_path) -> None:
    bad = tmp_path / "bad.wav"
    bad.write_text("not audio")

    result = CliRunner().invoke(app, ["analyze", str(bad)])

    assert result.exit_code == 1
    assert "bad.wav" in result.stderr


def test_missing_input_is_a_usage_error(tmp_path) -> None:
    result = CliRunner().invoke(app, ["analyze", str(tmp_path / "missing.wav")])

    assert result.exit_code == 2
    assert "does not exist" in result.stderr


def test_silent_audio_reports_no_beats(tmp_path) -> None:
    silent = tmp_path / "silent.wav"
    soundfile.write(silent, np.zeros(4 * SR, dtype=np.float32), SR)

    result = CliRunner().invoke(app, ["analyze", str(silent)])

    assert result.exit_code == 1
    assert "no beats" in result.stderr


def test_unwritable_output_is_an_error(clip, tmp_path) -> None:
    out = tmp_path / "no_such_dir" / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out)])

    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "no_such_dir" in result.stderr


@pytest.mark.parametrize("force", [False, True])
def test_output_may_not_be_the_input(clip, force) -> None:
    before = clip.read_bytes()

    args = ["analyze", str(clip), "-o", str(clip)] + (["--force"] if force else [])
    result = CliRunner().invoke(app, args)

    assert result.exit_code == 1
    assert "input file" in result.stderr
    assert clip.read_bytes() == before


def test_output_may_not_be_a_symlink_to_the_input(clip, tmp_path) -> None:
    before = clip.read_bytes()
    link = tmp_path / "link.json"
    link.symlink_to(clip)

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(link), "--force"])

    assert result.exit_code == 1
    assert "input file" in result.stderr
    assert clip.read_bytes() == before


def test_output_may_not_be_a_hard_link_to_the_input(clip, tmp_path) -> None:
    before = clip.read_bytes()
    link = tmp_path / "hard.json"
    os.link(clip, link)

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(link), "--force"])

    assert result.exit_code == 1
    assert "input file" in result.stderr
    assert clip.read_bytes() == before


def test_forced_write_does_not_follow_a_link_made_during_analysis(
    clip, tmp_path, monkeypatch
) -> None:
    before = clip.read_bytes()
    out = tmp_path / "out.json"

    def stub(path, key=None, engine=None):
        os.link(clip, out)
        return {"schema_version": 1}

    monkeypatch.setattr(chordotomy.timeline, "analyze", stub)

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--force"])

    assert result.exit_code == 0
    assert clip.read_bytes() == before
    assert json.loads(out.read_text()) == {"schema_version": 1}
    assert [p.name for p in tmp_path.iterdir()].count("out.json") == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_unwritable_forced_output_is_an_error(clip, tmp_path) -> None:
    out = tmp_path / "no_such_dir" / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--force"])

    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "no_such_dir" in result.stderr


def test_forced_write_keeps_the_existing_mode(clip, tmp_path) -> None:
    out = tmp_path / "out.json"
    out.write_text("old")
    out.chmod(0o600)

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--force"])

    assert result.exit_code == 0
    assert out.stat().st_mode & 0o777 == 0o600
    assert json.loads(out.read_text())["schema_version"] == 8


@pytest.mark.parametrize("args", [[], ["--engine", "dsp"]], ids=["default", "dsp"])
def test_without_the_model_the_dsp_writes_the_chords(clip, tmp_path, args) -> None:
    out = tmp_path / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), *args])

    assert result.exit_code == 0
    assert "engine:" not in result.stderr
    assert json.loads(out.read_text())["generator"]["engine"] == {
        "name": "dsp",
        "version": __version__,
    }


def test_the_model_engine_without_the_extra_is_a_usage_error(clip, tmp_path, monkeypatch):
    # The real check, on an interpreter where lv_chordia cannot be found.
    monkeypatch.setattr(chordotomy.model, "available", REAL_AVAILABLE)
    monkeypatch.setitem(sys.modules, "lv_chordia", None)
    out = tmp_path / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--engine", "model"])

    assert result.exit_code == 2
    assert "--engine" in result.stderr
    assert "uv sync --extra model" in result.stderr
    assert not out.exists()


def test_the_default_is_the_model_when_it_is_installed(clip, tmp_path, monkeypatch) -> None:
    out = tmp_path / "out.json"
    engines = []

    def stub(path, key=None, engine=None):
        engines.append(engine)
        return {"schema_version": 6}

    monkeypatch.setattr(chordotomy.model, "available", lambda: True)
    monkeypatch.setattr(chordotomy.model, "version", lambda: "9.9.9")
    monkeypatch.setattr(chordotomy.timeline, "analyze", stub)

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out)])

    assert result.exit_code == 0
    assert engines == ["model"]
    # A model run takes seconds to minutes; it says so before it starts.
    assert "engine: lv-chordia 9.9.9" in result.stderr


@pytest.mark.parametrize("cached", [False, True])
def test_the_model_engine_says_when_it_downloads_the_beat_weights(
    clip, tmp_path, monkeypatch, cached
) -> None:
    monkeypatch.setattr(chordotomy.model, "available", lambda: True)
    monkeypatch.setattr(chordotomy.model, "version", lambda: "9.9.9")
    monkeypatch.setattr(chordotomy.beats, "verified", lambda: cached)
    monkeypatch.setattr(chordotomy.timeline, "analyze", lambda path, key=None, engine=None: {})
    args = ["analyze", str(clip), "-o", str(tmp_path / "out.json"), "--engine", "model"]

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 0
    assert ("fetch-weights" in result.stderr) is not cached
    assert (str(chordotomy.beats.checkpoint_path()) in result.stderr) is not cached


def test_a_broken_model_is_an_error_not_a_fallback(clip, tmp_path, monkeypatch) -> None:
    out = tmp_path / "out.json"

    def broken(y):
        raise chordotomy.model.EngineError(ENGINE_FAILURE)

    monkeypatch.setattr(chordotomy.model, "available", lambda: True)
    monkeypatch.setattr(chordotomy.model, "version", lambda: "9.9.9")
    monkeypatch.setattr(chordotomy.model, "recognize", broken)
    monkeypatch.setattr(chordotomy.beats, "activation", librosa_activation)

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--engine", "model"])

    assert result.exit_code == 1
    assert f"error: {ENGINE_FAILURE}" in result.stderr
    assert "Traceback" not in result.output
    assert not out.exists()


def test_the_dsp_engine_touches_no_torch(clip, tmp_path, monkeypatch) -> None:
    # Block the imports instead of faking the modules: libraries legitimately probe sys.modules
    # (scipy.stats touches torch.Tensor if torch is there), so a stand-in fails for the wrong
    # reason depending on what an earlier test already imported. Absent from sys.modules plus a
    # finder that raises means any real import by the DSP path fails the test.
    blocked = ("torch", "lv_chordia", "beat_this", "torchaudio")

    class Blocker:
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in blocked:
                raise ImportError(f"{name} imported by the DSP engine")

    for name in list(sys.modules):
        if name.split(".")[0] in blocked:
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "meta_path", [Blocker(), *sys.meta_path])
    out = tmp_path / "out.json"

    result = CliRunner().invoke(app, ["analyze", str(clip), "-o", str(out), "--engine", "dsp"])

    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text())["generator"]["engine"]["name"] == "dsp"


def test_importing_the_cli_touches_no_librosa() -> None:
    # A fresh interpreter with stand-ins for librosa, torch, lv_chordia, beat_this and torchaudio
    # whose every attribute raises, so none of them (nor numba) is really loaded, and an eager
    # note_to_midi or cq_to_chroma, or any torch use, at import would fail.
    code = (
        "import sys, types\n"
        "class Fake(types.ModuleType):\n"
        "    def __getattr__(self, name):\n"
        "        raise AssertionError(f'{self.__name__}.{name} used at import')\n"
        "for name in ('librosa', 'torch', 'lv_chordia', 'beat_this', 'torchaudio'):\n"
        "    sys.modules[name] = Fake(name)\n"
        "import chordotomy.cli\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("command", ["analyze", "evaluate"])
def test_a_missing_package_version_is_an_error_not_a_traceback(
    clip, tmp_path, monkeypatch, command
) -> None:
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(chordotomy.model, "available", lambda: True)
    monkeypatch.setattr(importlib.metadata, "version", missing)
    if command == "evaluate" and not all(
        importlib.util.find_spec(name) for name in ("mir_eval", "pooch")
    ):
        pytest.skip("the eval extra is not installed")
    args = [command, str(clip) if command == "analyze" else "tiny-aam", "--engine", "model"]

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 1
    assert "error:" in result.stderr
    assert "uv sync --extra model" in result.stderr
    assert "Traceback" not in result.output


def test_fetch_weights_without_the_extra_is_a_usage_error() -> None:
    result = CliRunner().invoke(app, ["fetch-weights"])

    assert result.exit_code == 2
    # Rich wraps the message inside a bordered error box.
    assert "uv sync --extra model" in " ".join(result.output.replace("│", " ").split())


def test_fetch_weights_prints_the_path(monkeypatch, tmp_path) -> None:
    path = tmp_path / "beat_this-final0.ckpt"
    monkeypatch.setattr(chordotomy.model, "available", lambda: True)
    monkeypatch.setattr(chordotomy.beats, "verified", lambda: False)
    monkeypatch.setattr(chordotomy.beats, "fetch", lambda: path)

    result = CliRunner().invoke(app, ["fetch-weights"])

    assert result.exit_code == 0
    assert str(path) in result.stdout


def test_fetch_weights_failure_is_an_error_not_a_traceback(monkeypatch) -> None:
    def offline():
        raise chordotomy.model.EngineError("cannot fetch the weights; pass --engine dsp")

    monkeypatch.setattr(chordotomy.model, "available", lambda: True)
    monkeypatch.setattr(chordotomy.beats, "verified", lambda: False)
    monkeypatch.setattr(chordotomy.beats, "fetch", offline)

    result = CliRunner().invoke(app, ["fetch-weights"])

    assert result.exit_code == 1
    assert result.stderr.count("error:") == 1
    assert "Traceback" not in result.output
