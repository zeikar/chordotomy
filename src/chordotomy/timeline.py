"""Assemble the chord-timeline JSON, the project's public seam (schema v2)."""

from __future__ import annotations

from pathlib import Path

from . import __version__, harmony
from .chords import match, segment, smooth
from .features import SR, beat_chroma, load_audio

SCHEMA_VERSION = 2


def analyze(path: Path, key: str | None = None) -> dict:
    """Analyze an audio file into a chord-timeline dict of plain, JSON-serialisable types."""
    y = load_audio(path)
    beat_times, chroma, cqt = beat_chroma(y)
    sims = match(chroma)
    segments = segment(smooth(sims), sims)

    progression = [(s["chord"], s["end_beat"] - s["start_beat"]) for s in segments]
    key_info, analyses = harmony.analyze(progression, key)

    duration = round(len(y) / SR, 3)
    # Rounded once, so segment times equal list entries exactly.
    beats = [round(float(t), 3) for t in beat_times]
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
                **a,
            }
            for s, a in zip(segments, analyses, strict=True)
        ],
    }
