"""Typer CLI for chordotomy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import soundfile
import typer

from . import __version__, timeline
from .features import NoBeatsError

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


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(1)


def _exists(output: Path) -> typer.Exit:
    return _fail(f"{output} exists; pass --force to overwrite")


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
) -> None:
    """Analyze AUDIO into a beat-aligned chord-timeline JSON."""
    if output is None:
        output = audio.with_suffix(".chords.json")
    if output.exists() and not force:
        raise _exists(output)

    try:
        result = timeline.analyze(audio)
    except (soundfile.LibsndfileError, NoBeatsError) as exc:
        raise _fail(f"{audio}: {exc}") from exc

    text = json.dumps(result, indent=2) + "\n"
    # The early check is a fast fail; only exclusive creation keeps the no-overwrite promise
    # if the file appears while analysis runs.
    try:
        with output.open("w" if force else "x") as f:
            f.write(text)
    except FileExistsError as exc:
        raise _exists(output) from exc
    except OSError as exc:
        raise _fail(f"{output}: {exc}") from exc
    typer.echo(f"Wrote {output}")
