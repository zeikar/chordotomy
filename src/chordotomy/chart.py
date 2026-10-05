"""A chord chart as an evaluation reference: parsed, and aligned to an analysis's beats.

A chart is the chords of a song in order, as a chord site writes them over the lyrics, typed into a
text file without the lyrics, with a `capo N` line when the chart is written for a capo. It has no
timing, so the analysis gives it one: each chord run of the timeline is assigned a chart chord, in
order, by the alignment below. The aligned chart is a timeline whose chords are the chart's where
the two differ, marked `edited` with the analyzer's candidates kept, so the viewer shows exactly the
places to check by ear and offers the analyzer's reading beside the chart's.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import numpy as np

from . import harmony, timeline
from .chords import QUALITIES, ROOTS, inversion

NOTE = re.compile(r"([A-G])([#b♯♭]?)")
# Chart suffixes, after `△`, `Δ`, `ø`, `°`, `-5` and the accidentals are normalized, to the
# vocabulary. Extensions the vocabulary lacks are dropped as the model engine drops them (9, 11 and
# 13 to the seventh, maj9 to maj7, min9 to min7); a sixth chord reads as its triad, since maj6 is
# min7's pitch set and stays out ("Chord vocabulary v5" in docs/decisions.md).
SUFFIXES = {
    "": "maj",
    "M": "maj",
    "maj": "maj",
    "m": "min",
    "min": "min",
    "-": "min",
    "7": "7",
    "M7": "maj7",
    "maj7": "maj7",
    "m7": "min7",
    "min7": "min7",
    "-7": "min7",
    "6": "maj",
    "69": "maj",
    "m6": "min6",
    "mM7": "min",
    "m7b5": "hdim7",
    "dim7": "dim7",
    "dim": "dim",
    "aug": "aug",
    "+": "aug",
    "+5": "aug",
    "#5": "aug",
    "sus4": "sus4",
    "sus": "sus4",
    "sus2": "sus2",
    "7sus4": "sus4(b7)",
    "7sus": "sus4(b7)",
    "9sus4": "sus4(b7)",
    "add9": "maj(9)",
    "add2": "maj(9)",
    "2": "maj(9)",
    "madd9": "min(9)",
    "madd2": "min(9)",
    "9": "7",
    "11": "7",
    "13": "7",
    "M9": "maj7",
    "maj9": "maj7",
    "M13": "maj7",
    "m9": "min7",
    "m11": "min7",
    "m13": "min7",
}
# Spellings of the same suffixes.
NORMALIZE = (("△", "M"), ("Δ", "M"), ("ø7", "m7b5"), ("ø", "m7b5"), ("°7", "dim7"), ("°", "dim"))
NORMALIZE += (("o7", "dim7"), ("-5", "b5"), ("♭", "b"), ("♯", "#"))
NO_CHORD = {"N", "N.C.", "NC", "N.C"}
# Bar lines and other marks a chart may carry between its chords.
MARKS = {"|", "||", "|:", ":|", "/", "%", "-"}
# A line of its own saying the chart is written for a capo, its chords sounding N semitones higher.
CAPO = re.compile(r"capo\s*:?\s*(\d+)", re.IGNORECASE)


class ChartError(ValueError):
    """A chart line holds a token that is not a chord."""


def _pitch(note: str) -> int:
    match = NOTE.fullmatch(note)
    if not match:
        raise ValueError(note)
    letter, accidental = match.groups()
    shift = {"": 0, "#": 1, "♯": 1, "b": -1, "♭": -1}[accidental]
    return (ROOTS.index(letter) + shift) % 12


def _quality(suffix: str) -> str:
    for old, new in NORMALIZE:
        suffix = suffix.replace(old, new)
    base, _, tensions = suffix.partition("(")
    added = {t.strip() for t in tensions.rstrip(")").split(",") if t.strip()}
    if added and not tensions.endswith(")"):
        raise ValueError(suffix)
    # A ninth added to a triad is the added ninth; a flat fifth on a minor seventh is its half-
    # diminished form; any other tension is dropped, as an extension past the seventh is.
    if added == {"9"} and base in ("", "M", "m", "add"):
        return "min(9)" if base == "m" else "maj(9)"
    if "b5" in added and base in ("m7", "min7"):
        return "hdim7"
    if base == "m" and added & {"M7", "maj7"}:
        return "min"
    return SUFFIXES[base]


def parse_chord(token: str) -> tuple[str, str | None]:
    """A chart chord as (Harte label, bass or None), sharps only: `F#m7-5` is (`F#:hdim7`, None),
    `D/F#` is (`D:maj`, `F#`), `N.C.` is (`N`, None). Raises ValueError on anything else."""
    if token in NO_CHORD:
        return "N", None
    head = token.replace("6/9", "69")
    head, slash, bass = head.partition("/")
    match = NOTE.match(head)
    if not match:
        raise ValueError(token)
    root = _pitch(match.group())
    try:
        quality = _quality(head[match.end() :])
        bass_pitch = _pitch(bass) if slash else None
    except (KeyError, ValueError) as exc:
        raise ValueError(token) from exc
    label = f"{ROOTS[root]}:{quality}"
    return label, None if bass_pitch is None else ROOTS[bass_pitch]


class Chart(NamedTuple):
    """A chart's chords in order, as (Harte label, bass or None), and its capo in semitones."""

    chords: list[tuple[str, str | None]]
    capo: int


def parse(text: str) -> Chart:
    """The chords of a chart file in order, and the capo a `capo N` line gives (0 without one). A
    line starting with `#` is a comment; bar lines and repeat marks between chords are skipped.
    Raises ChartError naming the line of the first token that is not a chord."""
    chords = []
    capo = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if found := CAPO.fullmatch(line.strip()):
            capo = int(found[1]) % 12
            continue
        for token in line.split():
            if token in MARKS:
                continue
            try:
                chords.append(parse_chord(token))
            except ValueError:
                raise ChartError(f"line {number}: {token!r} is not a chord") from None
    return Chart(chords, capo)


# What passing over a chart chord costs, in beats of full mismatch: a chart chord the analysis has
# no run for, merged into a neighbour or missed. One short chord's worth: passing a chord costs as
# much as two beats of a wrong one, so a lone mismatch is kept rather than skipped around. A chart's
# N.C. costs the same, so a chord the analysis hears in a break is put on it and shows.
SKIP = 2.0
# Added to the distance of two chords on different roots: against a chart's C, Am (two shared tones
# of four, 0.75) is further than Cmaj7 (three of four, 0.25).
ROOT_MISS = 0.25
_POPCOUNT = np.array([bin(n).count("1") for n in range(4096)])


def _mask(label: str, shift: int = 0) -> int:
    if label == "N":
        return 0
    root, quality = label.split(":")
    start = ROOTS.index(root) + shift
    return sum(1 << ((start + i) % 12) for i in set(QUALITIES[quality]))


def _distances(chart: list[str], runs: list[str], shift: int) -> np.ndarray:
    """(len(chart), len(runs)) distances in [0, 1]: one minus the shared share of the two pitch
    sets, plus ROOT_MISS for different roots; 0 between two N, 1 between a chord and N."""
    a = np.array([_mask(label, shift) for label in chart])[:, None]
    b = np.array([_mask(label) for label in runs])[None, :]
    union = _POPCOUNT[a | b]
    shared = np.divide(_POPCOUNT[a & b], union, out=np.ones(union.shape), where=union > 0)
    roots_a = [(ROOTS.index(c.split(":")[0]) + shift) % 12 if c != "N" else -1 for c in chart]
    roots_b = [ROOTS.index(c.split(":")[0]) if c != "N" else -1 for c in runs]
    distance = 1 - shared + ROOT_MISS * (np.array(roots_a)[:, None] != np.array(roots_b)[None, :])
    return np.minimum(distance, 1.0)


def _path(cost: np.ndarray, silent: list[bool]) -> tuple[float, list[int | None]]:
    """Each run's chart index, or None for an N run left unaligned, at the least total cost.

    cost is (chart, runs): a run's beats times its distance to each chart chord. Runs take chart
    chords in order, each at or after the previous run's, and every chart chord passed over costs
    SKIP. An N run (silent) may also be passed over itself, at no cost: silence the chart does not
    mark is not aligned. States are 0 (before the chart) and 1 + a chart index.
    """
    n_chart, n_runs = cost.shape
    passed = np.arange(n_chart + 1) * SKIP  # passed[k]: passing chart chords 0..k-1
    best = np.full(n_chart + 1, np.inf)
    best[0] = 0.0
    back = np.zeros((n_runs, n_chart + 1), dtype=int)
    state = np.arange(n_chart + 1)
    for j in range(n_runs):
        # Arriving at state b from a < b passes chart chords a..b-2.
        leaving = best - passed
        lowest = np.minimum.accumulate(leaving)
        lowest_at = np.maximum.accumulate(np.where(leaving == lowest, state, 0))
        arrive = np.full(n_chart + 1, np.inf)
        arrive[1:] = lowest[:-1] + passed[:n_chart]
        stay = best.copy()
        stay[0] = np.inf
        stays = stay <= arrive
        taken = np.where(stays, stay, arrive)
        taken[1:] += cost[:, j]
        came = np.where(stays, state, np.concatenate([[0], lowest_at[:-1]]))
        if silent[j]:
            # Passed over: the state carries, marked by a negative pointer.
            passes = best <= taken
            back[j] = np.where(passes, -1, came)
            best = np.where(passes, best, taken)
        else:
            back[j] = came
            best = taken
    end = best + passed[n_chart] - passed
    b = int(np.argmin(end))
    path: list[int | None] = []
    for j in range(n_runs - 1, -1, -1):
        if back[j, b] == -1:
            path.append(None)
        else:
            path.append(b - 1)
            b = int(back[j, b])
    return float(end.min()), path[::-1]


def _shifted(chord: tuple[str, str | None], shift: int) -> tuple[str, str | None]:
    label, bass = chord
    if label == "N":
        return chord
    root, quality = label.split(":")
    moved = ROOTS[(ROOTS.index(root) + shift) % 12]
    return f"{moved}:{quality}", None if bass is None else ROOTS[(ROOTS.index(bass) + shift) % 12]


class Alignment(NamedTuple):
    """The aligned chart and what to say about it.

    timeline: the analysis with the chart's chords on its runs; charted: per segment, whether its
    run took a chart chord (an N run left unaligned did not); differ: the segments that differ from
    the analysis; passed: the chart chords no run took; fits: the transposition, 0 to 11 semitones
    up, under which the chart fits the analysis best, to compare with the chart's capo.
    """

    timeline: dict
    charted: list[bool]
    differ: int
    passed: int
    fits: int


def align(result: dict, chart: Chart) -> Alignment:
    """The timeline `result` with `chart`'s chords put on its chord runs.

    Each chord run takes one chart chord, in order; a chart chord may span several runs (the
    analysis split it) or none (it merged or missed one). An N run takes a chart chord or is left
    as it is, unaligned. The chart is moved up by its capo. A segment whose chord or bass changes
    takes the chart's and is `edited`, keeping the analyzer's candidates. A chart chord with no
    slash says nothing about the bass: the analyzer's bass stays if it is the chart chord's root,
    third or fifth (G over the analyzer's D bass is G/D), else the bass is its root. The key, the
    key regions and every numeral are analyzed again from the new chords.
    """
    if not chart.chords:
        raise ChartError("the chart has no chords")
    runs = timeline.chord_runs(result["segments"])
    heard = [run[0]["chord"] for run in runs]
    beats = np.array([run[-1]["end_beat"] - run[0]["start_beat"] for run in runs])
    silent = [label == "N" for label in heard]
    labels = [label for label, _ in chart.chords]
    fits = [_path(_distances(labels, heard, s) * beats, silent) for s in range(12)]
    best = min(range(12), key=lambda s: (fits[s][0], s != chart.capo))
    path = fits[chart.capo][1]

    segments = []
    charted = [i is not None for run, i in zip(runs, path, strict=True) for _ in run]
    for run, i in zip(runs, path, strict=True):
        for s in run:
            if i is None:
                segments.append(s)
                continue
            label, bass = _shifted(chart.chords[i], chart.capo)
            if label == "N":
                bass = None
            elif bass is None:
                kept = inversion(label, s["bass"]) in ("root", "first", "second")
                bass = s["bass"] if kept else label.split(":")[0]
            if (label, bass) == (s["chord"], s["bass"]):
                segments.append(s)
            else:
                changed = {"chord": label, "bass": bass, "inversion": inversion(label, bass)}
                segments.append({**s, **changed, "edited": True})

    key = result["global_key"]
    given = key["label"] if key is not None and key["source"] == "given" else None
    chord_runs = timeline.chord_runs(segments)
    key_info, regions, run_analyses = harmony.analyze(timeline.progression(chord_runs), given)
    analyses = [a for run, a in zip(chord_runs, run_analyses, strict=True) for _ in run]
    segments = [{**s, **a} for s, a in zip(segments, analyses, strict=True)]
    aligned = {**result, "global_key": key_info, "key_regions": regions, "segments": segments}
    taken = {i for i in path if i is not None}
    differ = sum(s["edited"] for s in segments)
    return Alignment(aligned, charted, differ, len(labels) - len(taken), best)
