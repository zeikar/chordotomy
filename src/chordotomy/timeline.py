"""Assemble the chord-timeline JSON, the project's public seam (schema v6)."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path
from typing import Literal

from . import __version__, harmony, model
from .chords import inversion, match, resolve_twins, segment, smooth
from .features import SR, beat_features, load_audio

SCHEMA_VERSION = 6


def chord_runs(segments: list[dict]) -> list[list[dict]]:
    """Group consecutive segments with one chord into runs.

    Harmony runs on chord runs, not segments: the key weights and the secondary-dominant
    look-ahead are defined on chords, and a bass change does not end a chord.
    """
    return [list(run) for _, run in groupby(segments, key=lambda s: s["chord"])]


def progression(runs: list[list[dict]]) -> list[tuple[str, int]]:
    """Each run's chord and its length in beats, the input of `harmony.analyze`."""
    return [(run[0]["chord"], run[-1]["end_beat"] - run[0]["start_beat"]) for run in runs]


def analyze(path: Path, key: str | None = None, engine: Literal["dsp", "model"] = "dsp") -> dict:
    """Analyze an audio file into a chord-timeline dict of plain, JSON-serialisable types.

    engine picks the chord recognizer: the DSP's templates or the lv-chordia model.
    """
    if engine not in ("dsp", "model"):
        raise ValueError(f"unknown engine {engine!r}; expected 'dsp' or 'model'")
    y = load_audio(path)
    # Before the model: audio without beats fails here, without loading the nets.
    f = beat_features(y)
    if engine == "model":
        # The model replaces only the per-beat chord states and scores. The beat grid, the bass
        # and inversions, the segmentation, the twin resolution and the harmony stay the DSP's.
        # The DSP's level gate is not applied: the model labels N itself.
        frame_states, frame_scores = model.recognize(y)
        boundaries = [*f.frames, len(frame_states)]
        states = model.beat_states(frame_states, boundaries)
        scores = model.beat_scores(frame_scores, boundaries)
        recognizer = {"name": model.NAME, "version": model.version()}
    else:
        scores = match(f.treble, f.bass)
        states = smooth(scores, f.level, f.period)
        recognizer = {"name": "dsp", "version": __version__}
    segments = resolve_twins(segment(states, scores, f.cqt))

    runs = chord_runs(segments)
    key_info, run_analyses = harmony.analyze(progression(runs), key)
    analyses = [a for run, a in zip(runs, run_analyses, strict=True) for _ in run]

    duration = round(len(y) / SR, 3)
    # Rounded once, so segment times equal list entries exactly.
    beats = [round(float(t), 3) for t in f.times]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": "chordotomy", "version": __version__, "engine": recognizer},
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
