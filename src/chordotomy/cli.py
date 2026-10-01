"""Typer CLI for chordotomy."""

from __future__ import annotations

import importlib
import json
import os
import stat
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import soundfile
import typer

from . import __version__, harmony, model, timeline
from . import evaluate as evaluation
from .features import NoBeatsError


class Dataset(StrEnum):
    TINY_AAM = "tiny-aam"
    GUITARSET = "guitarset"


class Engine(StrEnum):
    AUTO = "auto"
    MODEL = "model"
    DSP = "dsp"


app = typer.Typer(no_args_is_help=True, add_completion=False)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"chordotomy {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    """Dissect a song's harmony."""


def _parse_key(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return harmony.parse_key(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _resolve_engine(value: Engine) -> Engine:
    # available() only looks for lv_chordia, so deciding never imports torch.
    if value is Engine.AUTO:
        return Engine.MODEL if model.available() else Engine.DSP
    if value is Engine.MODEL and not model.available():
        raise typer.BadParameter(
            "lv-chordia is not installed; install the model extra with `uv sync --extra model`"
        )
    return value


EngineOption = Annotated[
    Engine,
    typer.Option(
        "--engine",
        callback=_resolve_engine,
        help="auto: lv-chordia when installed, else the DSP.",
    ),
]


def _announce(engine: Engine) -> None:
    # The model takes seconds to minutes, most of it before any output.
    if engine is Engine.MODEL:
        typer.echo(f"engine: {model.NAME} {model.version()}", err=True)


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(1)


def _exists(output: Path) -> typer.Exit:
    return _fail(f"{output} exists; pass --force to overwrite")


def _replace(output: Path, data: bytes) -> None:
    # The replacement keeps the existing output's mode, else the mode a plain open would give, as
    # the non-force path. mkstemp creates it 0600, so it stays private until the final chmod.
    if output.exists():
        mode = stat.S_IMODE(output.stat().st_mode)
    else:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, tmp = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, output)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@app.command()
def analyze(
    audio: Annotated[
        Path,
        typer.Argument(exists=True, dir_okay=False, readable=True, help="Audio file (mp3, wav)."),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Timeline JSON path (default: AUDIO.chords.json)."),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite an existing output file.")
    ] = False,
    key: Annotated[
        str | None,
        typer.Option(
            "--key",
            callback=_parse_key,
            help=(
                "Key as <root>:maj or <root>:min, e.g. A:min or Bb:maj; "
                "overrides the estimated key (candidates are still ranked)."
            ),
        ),
    ] = None,
    engine: EngineOption = Engine.AUTO,
) -> None:
    """Analyze AUDIO into a beat-aligned chord-timeline JSON."""
    if output is None:
        output = audio.with_suffix(".chords.json")
    # samefile compares device and inode, so symlinks and hard links to the input are both
    # caught; --force must not truncate the recording into JSON.
    if output.exists() and output.samefile(audio):
        raise _fail(f"{output} is the input file; choose a different --output")
    if output.exists() and not force:
        raise _exists(output)

    try:
        _announce(engine)
        result = timeline.analyze(audio, key=key, engine=engine.value)
    except (soundfile.LibsndfileError, NoBeatsError) as exc:
        raise _fail(f"{audio}: {exc}") from exc
    except model.EngineError as exc:
        raise _fail(str(exc)) from exc

    # UTF-8 characters, not \u escapes, so a numeral's ø or ° and a non-ASCII path read as
    # themselves in the file, whatever the locale. A path that was not UTF-8 to begin with holds a
    # lone surrogate, which UTF-8 cannot encode; backslashreplace writes it as the JSON escape
    # json.dumps would have. Encoded before anything is opened, so a failure leaves no empty file.
    data = (json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8", "backslashreplace"
    )
    # The early checks are fast fails; the write must hold up if the output appears or becomes a
    # link while analysis runs. Exclusive creation refuses anything already there. --force
    # writes a temp file and swaps it in, so the write never follows a symlink or hard link
    # to the recording.
    try:
        if force:
            _replace(output, data)
        else:
            with output.open("xb") as f:
                f.write(data)
    except FileExistsError as exc:
        raise _exists(output) from exc
    except OSError as exc:
        raise _fail(f"{output}: {exc}") from exc
    typer.echo(f"Wrote {output}")


@app.command()
def evaluate(
    dataset: Annotated[Dataset, typer.Argument(help="Dataset to score against.")],
    limit: Annotated[
        int | None, typer.Option("--limit", min=1, help="Score only the first N tracks.")
    ] = None,
    engine: EngineOption = Engine.AUTO,
) -> None:
    """Score the chord front end on a public dataset (opt-in, downloads on first use)."""
    # Check the extra before anything can download.
    for name in ("mir_eval", "pooch"):
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            raise _fail("the evaluation needs the eval extra: uv sync --extra eval") from exc

    try:
        _announce(engine)
        evaluation.run(dataset.value, limit, engine.value)
    except evaluation.DatasetError as exc:
        raise _fail(f"{dataset.value}: {exc}") from exc
    except model.EngineError as exc:
        raise _fail(str(exc)) from exc
