import json
import os
import subprocess
import sys

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
    assert data["schema_version"] == 4
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

    def stub(path, key=None):
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

    def stub(path, key=None):
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
    assert json.loads(out.read_text())["schema_version"] == 4


def test_importing_the_cli_touches_no_librosa() -> None:
    # A fresh interpreter with a stand-in librosa whose every attribute raises, so no real librosa
    # (and no numba) is loaded, and an eager note_to_midi or cq_to_chroma at import would fail.
    code = (
        "import sys, types\n"
        "class Fake(types.ModuleType):\n"
        "    def __getattr__(self, name):\n"
        "        raise AssertionError(f'librosa.{name} used at import')\n"
        "sys.modules['librosa'] = Fake('librosa')\n"
        "import chordotomy.cli\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
