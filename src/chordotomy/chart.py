"""A chord chart as an evaluation reference: parsed, and aligned to an analysis's beats.

A chart is the chords of a song in order, as a chord site writes them over the lyrics, typed into a
text file without the lyrics. It has no timing, so the analysis gives it one: each chord run of the
timeline is assigned a chart chord, in order, by the alignment below. The aligned chart is a
timeline whose chords are the chart's where the two differ, marked `edited` with the analyzer's
candidates kept, so the viewer shows exactly the places to check by ear and offers the analyzer's
reading beside the chart's.
"""

from __future__ import annotations

import re

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


def parse(text: str) -> list[tuple[str, str | None]]:
    """The chords of a chart file in order. A line starting with `#` is a comment; bar lines and
    repeat marks between chords are skipped. Raises ChartError naming the line of the first token
    that is not a chord."""
    chords = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for token in line.split():
            if token in MARKS:
                continue
            try:
                chords.append(parse_chord(token))
            except ValueError:
                raise ChartError(f"line {number}: {token!r} is not a chord") from None
    return chords


# What a skipped chart chord costs, in beats of full mismatch: a chart chord the analysis has no
# run for, merged into a neighbour or missed. One short chord's worth: passing a chord costs as
# much as two beats of a wrong one, so a lone mismatch is kept rather than skipped around.
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
    sets, plus ROOT_MISS for different roots; 1 between a chord and N."""
    a = np.array([_mask(label, shift) for label in chart])[:, None]
    b = np.array([_mask(label) for label in runs])[None, :]
    union = _POPCOUNT[a | b]
    shared = np.divide(_POPCOUNT[a & b], union, out=np.ones(union.shape), where=union > 0)
    roots_a = np.array(
        [(ROOTS.index(c.split(":")[0]) + shift) % 12 if c != "N" else -1 for c in chart]
    )
    roots_b = np.array([ROOTS.index(c.split(":")[0]) if c != "N" else -1 for c in runs])
    distance = 1 - shared + ROOT_MISS * (roots_a[:, None] != roots_b[None, :])
    return np.minimum(distance, 1.0)


def _path(cost: np.ndarray, skip: np.ndarray) -> tuple[float, list[int]]:
    """The chart index of each run minimizing assignment and skip costs, in order: each run takes a
    chart chord at or after the previous run's, the chords passed over cost their skip."""
    n_chart, n_runs = cost.shape
    passed = np.concatenate([[0.0], np.cumsum(skip)])  # passed[k]: skipping chords 0..k-1
    best = passed[:n_chart] + cost[:, 0]
    back = np.zeros((n_runs, n_chart), dtype=int)
    index = np.arange(n_chart)
    for j in range(1, n_runs):
        # Arriving at chart chord i from i' < i passes the chords between them.
        leaving = best - passed[1 : n_chart + 1]
        lowest = np.minimum.accumulate(leaving)
        lowest_at = np.maximum.accumulate(np.where(leaving == lowest, index, 0))
        arrive = np.full(n_chart, np.inf)
        arrive[1:] = lowest[:-1] + passed[1:n_chart]
        stay = best <= arrive
        back[j] = np.where(stay, index, np.concatenate([[0], lowest_at[:-1]]))
        best = np.where(stay, best, arrive) + cost[:, j]
    end = best + passed[n_chart] - passed[1 : n_chart + 1]
    i = int(np.argmin(end))
    path = [i]
    for j in range(n_runs - 1, 0, -1):
        i = int(back[j, i])
        path.append(i)
    return float(end.min()), path[::-1]


def _shifted(chord: tuple[str, str | None], shift: int) -> tuple[str, str | None]:
    label, bass = chord
    if label == "N":
        return chord
    root, quality = label.split(":")
    moved = ROOTS[(ROOTS.index(root) + shift) % 12]
    return f"{moved}:{quality}", None if bass is None else ROOTS[(ROOTS.index(bass) + shift) % 12]


def align(result: dict, chart: list[tuple[str, str | None]]) -> tuple[dict, int, int]:
    """The timeline `result` with `chart`'s chords put on its chord runs, the semitones the chart
    was moved up to fit the recording (0 to 11), and how many segments now differ from the analysis.

    Each run that is not N takes one chart chord, in order; a chart chord may span several runs
    (the analysis split it) or none (it merged or missed one). The chart is tried in all twelve
    transpositions, as a chart for a capo is written in another key, and the one that fits best is
    kept, the untransposed on a tie. A segment whose chord or bass changes takes the chart's and is
    `edited`, keeping the analyzer's candidates. A chart chord with no slash says nothing about the
    bass: the analyzer's bass stays if it is the chart chord's root, third or fifth (G over the
    analyzer's D bass is G/D), else the bass is its root; an added tone or a seventh in the bass
    takes the chart's slash.
    The key, the key regions and every numeral are analyzed again from the new chords.
    """
    if not chart:
        raise ChartError("the chart has no chords")
    runs = timeline.chord_runs(result["segments"])
    played = [k for k, run in enumerate(runs) if run[0]["chord"] != "N"]
    labels = [label for label, _ in chart]
    assigned: dict[int, tuple[str, str | None]] = {}
    shift = 0
    if played:
        beats = np.array([runs[k][-1]["end_beat"] - runs[k][0]["start_beat"] for k in played])
        heard = [runs[k][0]["chord"] for k in played]
        # A chart's N.C. may pass unheard: the analysis's N runs are not aligned at all.
        skip = np.array([0.0 if label == "N" else SKIP for label in labels])
        fits = [_path(_distances(labels, heard, s) * beats, skip) for s in range(12)]
        shift = min(range(12), key=lambda s: fits[s][0])
        assigned = {
            k: _shifted(chart[i], shift) for k, i in zip(played, fits[shift][1], strict=True)
        }

    segments = []
    for k, run in enumerate(runs):
        for s in run:
            if k not in assigned:
                segments.append(s)
                continue
            label, bass = assigned[k]
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
    differ = sum(s["edited"] for s in segments)
    aligned = {**result, "global_key": key_info, "key_regions": regions, "segments": segments}
    return aligned, shift, differ
