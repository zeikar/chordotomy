"""Assemble the chord-timeline JSON, the project's public seam (schema v3)."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path

from . import __version__, harmony
from .chords import inversion, match, segment, smooth
from .features import SR, beat_features, load_audio

SCHEMA_VERSION = 3


def analyze(path: Path, key: str | None = None) -> dict:
    """Analyze an audio file into a chord-timeline dict of plain, JSON-serialisable types."""
    y = load_audio(path)
    f = beat_features(y)
    scores = match(f.treble, f.bass)
    segments = segment(smooth(scores, f.level, f.period), scores, f.cqt)

    # Harmony runs on chord runs, not segments: the key weights and the secondary-dominant
    # look-ahead are defined on chords, and a bass change does not end a chord.
    runs = [list(run) for _, run in groupby(segments, key=lambda s: s["chord"])]
    progression = [(run[0]["chord"], run[-1]["end_beat"] - run[0]["start_beat"]) for run in runs]
    key_info, run_analyses = harmony.analyze(progression, key)
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
            }
            for s, a in zip(segments, analyses, strict=True)
        ],
    }
