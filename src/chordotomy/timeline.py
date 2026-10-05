"""Assemble the chord-timeline JSON, the project's public seam (schema v11)."""

from __future__ import annotations

from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np

from . import __version__, beats, harmony, model
from .chords import (
    beat_basses,
    inversion,
    match,
    no_chord,
    pick_bass,
    resolve_twins,
    segment,
    smooth,
)
from .features import SR, beat_features, load_audio

if TYPE_CHECKING:
    from .stagecache import StageCache

SCHEMA_VERSION = 11


def chord_runs(segments: list[dict]) -> list[list[dict]]:
    """Group consecutive segments with one chord into runs.

    Harmony runs on chord runs, not segments: the key weights and the secondary-dominant
    look-ahead are defined on chords, and a bass change does not end a chord.
    """
    return [list(run) for _, run in groupby(segments, key=lambda s: s["chord"])]


def progression(runs: list[list[dict]]) -> list[tuple[str, int]]:
    """Each run's chord and its length in beats, the input of `harmony.analyze`."""
    return [(run[0]["chord"], run[-1]["end_beat"] - run[0]["start_beat"]) for run in runs]


def analyze(
    path: Path,
    key: str | None = None,
    engine: Literal["dsp", "model"] = "dsp",
    *,
    source_url: str | None = None,
    cache: StageCache | None = None,
) -> dict:
    """Analyze an audio file into a chord-timeline dict of plain, JSON-serialisable types.

    engine picks the chord recognizer and the envelope the beats are tracked on: the DSP's
    templates on librosa's onset strength, or the lv-chordia model on Beat This!'s activation,
    whose weights are downloaded on first use. Raises NoBeatsError on audio without beats, and
    EngineError when the model engine cannot run. source_url is the web page the recording came
    from; it is recorded in the timeline as given and never fetched. cache, for evaluation, keeps
    the slow stages (the activation, the beat features and the model's frames) across runs; the
    result is the same with or without it.
    """
    if engine not in ("dsp", "model"):
        raise ValueError(f"unknown engine {engine!r}; expected 'dsp' or 'model'")

    def stage(run, *args, **kwargs):
        return run(*args, **kwargs) if cache is None else cache.run(run, *args, **kwargs)

    y = load_audio(path)
    # Before lv-chordia: audio without beats fails here, at Beat This!'s gate or in the tracker,
    # without loading its nets.
    envelope = stage(beats.activation, y) if engine == "model" else None
    f = stage(beat_features, y, onset_envelope=envelope)
    if engine == "model":
        # The model replaces the per-beat chord states and scores and judges the bass. Its beats
        # come from Beat This!'s activation through the DSP's tracker and octave check; the cut
        # rule, the twin resolution and the harmony are the same rules as the DSP's. The DSP's N
        # gate is not applied: the model labels N itself.
        frame_states, frame_scores, frame_bass = stage(model.recognize, y)
        boundaries = [*f.frames, len(frame_states)]
        states = model.beat_states(frame_states, boundaries)
        scores = model.beat_scores(frame_scores, boundaries)
        head = model.beat_scores(frame_bass.T, boundaries)
        basses, inferred = model.beat_bass(head, states, [pick_bass(c) for c in f.cqt.T])
        recognizer = {"name": model.NAME, "version": model.version()}
    else:
        scores = match(f.treble, f.bass)
        forced = no_chord(f.level, f.onset, f.flatness, f.harmonic)
        states = smooth(scores, forced, np.diff(f.times))
        basses, inferred = beat_basses(states, f.cqt)
        recognizer = {"name": "dsp", "version": __version__}
    segments = resolve_twins(segment(states, scores, basses, inferred))

    runs = chord_runs(segments)
    key_info, keys, run_analyses = harmony.analyze(progression(runs), key)
    analyses = [a for run, a in zip(runs, run_analyses, strict=True) for _ in run]

    duration = round(len(y) / SR, 3)
    # Rounded once, so segment times equal list entries exactly.
    beat_times = [round(float(t), 3) for t in f.times]
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": "chordotomy", "version": __version__, "engine": recognizer},
        "source": {"path": str(path), "duration": duration, "url": source_url},
        "global_key": key_info,
        "key_regions": keys,
        "beats": beat_times,
        "segments": [
            {
                "start_beat": s["start_beat"],
                "end_beat": s["end_beat"],
                "start_time": beat_times[s["start_beat"]],
                "end_time": (
                    duration if s["end_beat"] == len(beat_times) else beat_times[s["end_beat"]]
                ),
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
