import json

import numpy as np
import pytest
import soundfile
from typer.testing import CliRunner

import chordotomy.timeline
from chordotomy import __version__
from chordotomy.cli import app
from chordotomy.features import SR


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
    assert data["schema_version"] == 1
    assert data["source"]["path"] == str(clip)


def test_default_output_is_not_overwritten_without_force(clip, tmp_path) -> None:
    runner = CliRunner()
    out = tmp_path / "clip.chords.json"

    assert runner.invoke(app, ["analyze", str(clip)]).exit_code == 0
    assert out.exists()

    out.write_text("hand-corrected")
    result = runner.invoke(app, ["analyze", str(clip)])
    assert result.exit_code == 1
    assert "--force" in result.stderr
    assert out.read_text() == "hand-corrected"

    assert runner.invoke(app, ["analyze", str(clip), "--force"]).exit_code == 0
    json.loads(out.read_text())


def test_file_appearing_during_analysis_is_not_overwritten(clip, tmp_path, monkeypatch) -> None:
    out = tmp_path / "out.json"

    def stub(path):
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
