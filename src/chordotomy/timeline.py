"""Assemble the chord-timeline JSON, the project's public seam (schema v5)."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

from . import __version__, harmony
from .chords import inversion, match, resolve_twins, segment, smooth
from .features import SR, beat_features, load_audio

SCHEMA_VERSION = 5


def chord_runs(segments: list[dict]) -> list[list[dict]]:
    """Group consecutive segments with one chord into runs.

    Harmony runs on chord runs, not segments: the key weights and the secondary-dominant
    look-ahead are defined on chords, and a bass change does not end a chord.
    """
    return [list(run) for _, run in groupby(segments, key=lambda s: s["chord"])]


def progression(runs: list[list[dict]]) -> list[tuple[str, int]]:
    """Each run's chord and its length in beats, the input of `harmony.analyze`."""
    return [(run[0]["chord"], run[-1]["end_beat"] - run[0]["start_beat"]) for run in runs]


def analyze(path: Path, key: str | None = None) -> dict:
    """Analyze an audio file into a chord-timeline dict of plain, JSON-serialisable types."""
    y = load_audio(path)
    f = beat_features(y)
    scores = match(f.treble, f.bass)
    segments = resolve_twins(segment(smooth(scores, f.level, f.period), scores, f.cqt))

    runs = chord_runs(segments)
    key_info, run_analyses = harmony.analyze(progression(runs), key)
    analyses = [a for run, a in zip(runs, run_analyses, strict=True) for _ in run]

    duration = round(len(y) / SR, 3)
    # Rounded once, so segment times equal list entries exactly.
    beats = [round(float(t), 3) for t in f.times]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": "chordotomy", "version": __version__},
        "source": {"path": str(path), "duration": duration},
        "key": key_info,
        "beats": beats,
        "segments": [
            {
                "start_beat": s["start_beat"],
                "end_beat": s["end_beat"],
                "start_time": beats[s["start_beat"]],
                "end_time": duration if s["end_beat"] == len(beats) else beats[s["end_beat"]],
                "chord": s["chord"],
                "candidates": s["candidates"],
                "bass": s["bass"],
                "inversion": inversion(s["chord"], s["bass"]),
                **a,
                # The viewer sets this when the user changes a chord; `candidates` then stays
                # what the analyzer heard.
                "edited": False,
            }
            for s, a in zip(segments, analyses, strict=True)
        ],
    }
