import json
import sys
import zipfile

import pytest
import soundfile
from typer.testing import CliRunner

pytest.importorskip("mir_eval")
pytest.importorskip("pooch")

import pooch  # noqa: E402
import requests  # noqa: E402

from chordotomy import evaluate, model  # noqa: E402
from chordotomy.cli import app  # noqa: E402
from chordotomy.features import SR  # noqa: E402

# Eight beats at 0.5 s on the 4 s clip: the last ends exactly at the duration, so no N tail.
ARFF = "@RELATION beatinfo\n" + "".join(f"{i * 0.5},1,{i % 4 + 1},'Cmaj'\n" for i in range(8))
COLUMNS = (
    "root",
    "majmin",
    "sevenths",
    "tetrads",
    "majmin_inv",
    "n_est",
    "n_ref",
    "n_precision",
    "n_recall",
    "beat_f",
    "cmlt",
    "amlt",
    "period_ratio",
    "bass_ref",
    "inv_prec",
    "inv_rec",
    "nonchord",
)


@pytest.fixture
def track(synth, tmp_path):
    audio = tmp_path / "clip.wav"
    soundfile.write(audio, synth([("C:maj", 8)]), SR)
    arff = tmp_path / "0001_beatinfo.arff"
    arff.write_text(ARFF)
    return "0001", audio, arff


@pytest.fixture
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("fetch must not be called")

    monkeypatch.setattr(evaluate, "fetch", fail)


def _run(*args):
    return CliRunner().invoke(app, ["evaluate", *args])


def _overall(output):
    row = next(line for line in output.splitlines() if line.startswith("overall"))
    return dict(zip(COLUMNS, map(float, row.split()[1:]), strict=True))


def test_tiny_aam_prints_a_row_per_track_and_overall(monkeypatch, track) -> None:
    monkeypatch.setattr(evaluate, "tiny_aam_tracks", lambda limit: [track])

    result = _run("tiny-aam")

    assert result.exit_code == 0
    assert any(line.startswith("0001") for line in result.stdout.splitlines())
    overall = _overall(result.stdout)
    assert overall["majmin"] >= 0.9
    assert overall["n_est"] <= 0.1
    assert overall["n_ref"] == 0.0
    assert overall["period_ratio"] == pytest.approx(1.0, abs=0.05)


def test_guitarset_scores_the_performed_annotation(monkeypatch, tmp_path, track) -> None:
    _, audio, _ = track
    jams = tmp_path / "take_comp.jams"
    jams.write_text(
        json.dumps(
            {
                "annotations": [
                    {
                        "namespace": "chord",
                        "annotation_metadata": {"data_source": ""},
                        "data": [{"time": 0.0, "duration": 4.0, "value": "C:maj"}],
                    },
                    {
                        "namespace": "chord",
                        "annotation_metadata": {"data_source": "Semi-automatic"},
                        "data": [{"time": 0.0, "duration": 4.0, "value": "C:maj/1"}],
                    },
                    {
                        "namespace": "beat_position",
                        "annotation_metadata": {"data_source": ""},
                        "data": [
                            {"time": t, "duration": 0.0, "value": {"position": t + 1}}
                            for t in range(4)
                        ],
                    },
                ]
            }
        )
    )
    monkeypatch.setattr(evaluate, "guitarset_tracks", lambda limit: [("take_comp", audio, jams)])

    result = _run("guitarset")

    assert result.exit_code == 0
    assert any(line.startswith("take_comp") for line in result.stdout.splitlines())
    overall = _overall(result.stdout)
    assert overall["majmin"] >= 0.9
    assert overall["n_est"] <= 0.1


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_limit_below_one_is_a_usage_error(no_network, limit) -> None:
    result = _run("tiny-aam", "--limit", limit)

    assert result.exit_code == 2
    assert "--limit" in result.stderr


@pytest.mark.parametrize("missing", ["mir_eval", "pooch"])
def test_missing_extra_gives_the_hint(no_network, monkeypatch, missing) -> None:
    monkeypatch.setitem(sys.modules, missing, None)

    result = _run("tiny-aam")

    assert result.exit_code == 1
    assert "uv sync --extra eval" in result.stderr


@pytest.mark.parametrize(
    "error",
    [
        requests.HTTPError("404 Client Error: Not Found for url: https://zenodo.org/x"),
        ValueError("File 'tinyAAM.zip' does not match the known hash 'md5:00'"),
        zipfile.BadZipFile("File is not a zip file"),
    ],
)
def test_data_boundary_failures_are_one_error_line(monkeypatch, tmp_path, error) -> None:
    def fail(self, *args, **kwargs):
        raise error

    monkeypatch.setattr(evaluate, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(pooch.Pooch, "fetch", fail)

    result = _run("tiny-aam")

    assert result.exit_code == 1
    assert "error: tiny-aam:" in result.stderr
    assert str(error) in result.stderr
    assert "Traceback" not in result.output


def test_malformed_annotation_names_the_file_and_label(monkeypatch, track) -> None:
    _, audio, arff = track
    arff.write_text("0.0,1,1,'Cdim'\n")
    monkeypatch.setattr(evaluate, "tiny_aam_tracks", lambda limit: [track])

    result = _run("tiny-aam")

    assert result.exit_code == 1
    assert "error: tiny-aam:" in result.stderr
    assert arff.name in result.stderr
    assert "Cdim" in result.stderr


def test_unreadable_annotation_names_the_path(monkeypatch, tmp_path, track) -> None:
    name, audio, _ = track
    missing = tmp_path / "gone.arff"
    monkeypatch.setattr(evaluate, "tiny_aam_tracks", lambda limit: [(name, audio, missing)])

    result = _run("tiny-aam")

    assert result.exit_code == 1
    assert "error: tiny-aam:" in result.stderr
    assert str(missing) in result.stderr
    assert "Traceback" not in result.output


def test_analysis_failures_keep_their_traceback(monkeypatch, track) -> None:
    def boom(path, engine=None):
        raise RuntimeError("analysis broke")

    monkeypatch.setattr(evaluate, "tiny_aam_tracks", lambda limit: [track])
    monkeypatch.setattr("chordotomy.timeline.analyze", boom)

    result = _run("tiny-aam")

    assert isinstance(result.exception, RuntimeError)
    assert "error:" not in result.stderr


def test_a_broken_model_is_one_error_line(monkeypatch, track) -> None:
    message = "lv_chordia cannot be imported; `uv sync --extra model`, or pass --engine dsp"
    engines = []

    def broken(path, engine=None):
        engines.append(engine)
        raise model.EngineError(message)

    monkeypatch.setattr(evaluate, "tiny_aam_tracks", lambda limit: [track])
    monkeypatch.setattr(model, "available", lambda: True)
    monkeypatch.setattr(model, "version", lambda: "9.9.9")
    monkeypatch.setattr("chordotomy.timeline.analyze", broken)

    result = _run("tiny-aam")

    assert result.exit_code == 1
    assert engines == ["model"]
    assert "engine: lv-chordia 9.9.9" in result.stderr
    assert f"error: {message}" in result.stderr
    assert "Traceback" not in result.output


def test_the_model_engine_without_the_extra_is_a_usage_error(no_network) -> None:
    result = _run("tiny-aam", "--engine", "model")

    assert result.exit_code == 2
    assert "--engine" in result.stderr
    assert "uv sync --extra model" in result.stderr


@pytest.fixture
def cache(monkeypatch, tmp_path):
    """A tinyAAM.zip of two fake tracks already in the cache, so pooch never downloads."""
    ids = ["0001", "0002"]
    archive = tmp_path / "tinyAAM.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for i in ids:
            z.writestr(f"annotations/{i}_beatinfo.arff", "arff")
            z.writestr(f"audio-mixes-mp3/{i}_mix.mp3", "mp3")
    monkeypatch.setattr(evaluate, "CACHE_DIR", tmp_path)
    monkeypatch.setitem(evaluate.REGISTRY, "tinyAAM.zip", f"md5:{pooch.file_hash(archive, 'md5')}")
    monkeypatch.setattr(evaluate, "TINY_AAM_IDS", ids)
    return tmp_path


def test_interrupted_extraction_is_completed(cache) -> None:
    partial = cache / "tinyAAM.zip.unzip" / "annotations" / "0001_beatinfo.arff"
    partial.parent.mkdir(parents=True)
    partial.write_text("arff")

    tracks = evaluate.tiny_aam_tracks(None)

    assert [t[0] for t in tracks] == ["0001", "0002"]
    assert all(p.exists() for _, audio, annotation in tracks for p in (audio, annotation))


def test_a_member_missing_from_the_archive_is_an_error(monkeypatch, cache) -> None:
    monkeypatch.setattr(evaluate, "TINY_AAM_IDS", ["0001", "0002", "9999"])

    with pytest.raises(evaluate.DatasetError, match="9999_beatinfo.arff"):
        evaluate.tiny_aam_tracks(None)
