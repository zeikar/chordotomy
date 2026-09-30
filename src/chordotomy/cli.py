"""Typer CLI for chordotomy."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Annotated

import soundfile
import typer

from . import __version__, harmony, timeline
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


def _parse_key(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return harmony.parse_key(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(1)


def _exists(output: Path) -> typer.Exit:
    return _fail(f"{output} exists; pass --force to overwrite")


def _replace(output: Path, text: str) -> None:
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
        with os.fdopen(fd, "w") as f:
            f.write(text)
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
        result = timeline.analyze(audio, key=key)
    except (soundfile.LibsndfileError, NoBeatsError) as exc:
        raise _fail(f"{audio}: {exc}") from exc

    text = json.dumps(result, indent=2) + "\n"
    # The early checks are fast fails; the write must hold up if the output appears or becomes a
    # link while analysis runs. Exclusive creation refuses anything already there. --force
    # writes a temp file and swaps it in, so the write never follows a symlink or hard link
    # to the recording.
    try:
        if force:
            _replace(output, text)
        else:
            with output.open("x") as f:
                f.write(text)
    except FileExistsError as exc:
        raise _exists(output) from exc
    except OSError as exc:
        raise _fail(f"{output}: {exc}") from exc
    typer.echo(f"Wrote {output}")
