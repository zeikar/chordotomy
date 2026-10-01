"""Golden vectors for the viewer's harmony, generated from the Python analysis.

Python is the reference. `harmony_vectors.json` holds what `harmony.analyze`, `chords.inversion`,
`timeline.chord_runs` and `timeline.progression` return on the cases below. The viewer's
`harmony.js` replays every case and must agree with it. `test_harmony_vectors.py` fails when the
file no longer matches the Python, so regenerate it after any change to those four:

    uv run python tests/harmony_vectors.py
"""

import json
from pathlib import Path

from chordotomy import chords, harmony, timeline
from chordotomy.chords import LABELS, QUALITIES, ROOTS
from chordotomy.harmony import KEYS

PATH = Path(__file__).with_name("harmony_vectors.json")

CHORDS = [label for label in LABELS if label != "N"]
# Per mode, a template as (semitones above the tonic, quality, beats), transposed to every key of
# that mode. An offset of None is an N.
KEY_TEMPLATES = {
    "maj": {
        "I IV V I": [(0, "maj", 2), (5, "maj", 1), (7, "maj", 1), (0, "maj", 2)],
        "Imaj7 vi7 ii7 V7": [(0, "maj7", 1), (9, "min7", 1), (2, "min7", 1), (7, "7", 1)],
        # I holds two beats each time: at one, IV and the borrowed bVII outweigh it and IV's key
        # is estimated.
        "I bVII IV N I": [
            (0, "maj", 2),
            (10, "maj", 1),
            (5, "maj", 1),
            (None, "N", 1),
            (0, "maj", 2),
        ],
    },
    "min": {
        "i iv V i": [(0, "min", 2), (5, "min", 1), (7, "maj", 1), (0, "min", 2)],
        "i7 VImaj7 iiø7 V7": [(0, "min7", 1), (8, "maj7", 1), (2, "hdim7", 1), (7, "7", 1)],
        "i IV #vii°7 i": [(0, "min", 2), (5, "maj", 1), (11, "dim7", 1), (0, "min", 2)],
    },
}
# The chords of test_following_is_ignored_outside_the_overlap, each with a diatonic chord on the
# root it would resolve to. C major has no diatonic chord on D#, so A#:maj keeps the test's D#:maj.
# B:hdim7 and B:dim are left out: the leading-tone cases already hold them. The augmented triads
# stand before the chord a fifth below, which they never resolve.
CONTROLS = [
    ("D:maj", "C:maj", "G:maj"),
    ("A:maj", "C:maj", "D:min"),
    ("A#:maj", "C:maj", "D#:maj"),
    ("D:maj7", "A:min", "G:maj"),
    ("G:aug", "C:maj", "C:maj"),
    ("C:aug", "C:maj", "F:maj"),
]
# The estimator's tie-breaks and edge cases: those tests/test_harmony.py pins, and a few more.
TIES = [
    ("Am F C G", None, [("A:min", 1), ("F:maj", 1), ("C:maj", 1), ("G:maj", 1)]),
    ("Am twice as long", None, [("A:min", 2), ("F:maj", 1), ("C:maj", 1), ("G:maj", 1)]),
    ("tonic sevenths", None, [("A:min7", 2), ("C:maj7", 2)]),
    ("C G C G", None, [("C:maj", 1), ("G:maj", 1)] * 2),
    ("G C G C", None, [("G:maj", 1), ("C:maj", 1)] * 2),
    ("N ignored", None, [("N", 4), ("C:maj", 2), ("N", 1), ("G:7", 2)]),
    ("all N", None, [("N", 8)]),
    ("all N in a given key", "C:maj", [("N", 8)]),
    ("every quality on C", None, [(f"C:{quality}", 1) for quality in QUALITIES]),
    ("a diatonic maj7 votes", None, [("C:maj7", 4), ("G:maj", 2), ("D:min", 1)]),
]
# Segments as (chord, start_beat, end_beat).
RUNS = {
    "a chord split by the bass": [("C:maj", 0, 2), ("C:maj", 2, 4)],
    "N between chords": [("C:maj", 0, 4), ("N", 4, 6), ("F:maj", 6, 10)],
    "a single segment": [("C:maj", 0, 8)],
    "alternating chords": [("C:maj", 0, 2), ("G:maj", 2, 4), ("C:maj", 4, 6), ("G:maj", 6, 8)],
}


def _up(root: str, semitones: int) -> str:
    return ROOTS[(ROOTS.index(root) + semitones) % 12]


def _progression_case(name: str, progression: list[tuple[str, int]], key: str | None) -> dict:
    key_object, analyses = harmony.analyze(progression, key)
    return {
        "name": name,
        "key": key,
        "progression": progression,
        "expected": {"key": key_object, "analyses": analyses},
    }


def _two_chords(label: str, following: str | None, key: str) -> dict:
    """The chord before `following`, or alone at the end of the piece when it is None."""
    if following is None:
        return _progression_case(f"{label} at the end in {key}", [(label, 1)], key)
    return _progression_case(
        f"{label} then {following} in {key}", [(label, 1), (following, 1)], key
    )


def _progressions() -> list[dict]:
    cases = []
    # Every chord before an N, so nothing resolves: every numeral, role and function in both modes.
    for key in ("C:maj", "A:min"):
        progression = [entry for label in CHORDS for entry in ((label, 1), ("N", 1))]
        cases.append(_progression_case(f"every chord in {key}", progression, key))
    # Every leading-tone chord before chords on every target root, so every target is tried.
    for key in ("C:maj", "A:min"):
        for quality in ("dim7", "hdim7", "dim"):
            for root in ROOTS:
                above = _up(root, 1)
                followings = [f"{above}:{q}" for q in ("maj", "min", "7", "maj7")]
                for following in [*followings, f"{_up(root, 2)}:maj", "N", None]:
                    cases.append(_two_chords(f"{root}:{quality}", following, key))
    # Minor's overlap of secondary dominants and borrowed chords, before chords a fifth down.
    for label in ("A:maj", "D:maj", "A:7", "D:7"):
        below = _up(label.split(":")[0], -7)
        followings = [f"{below}:{q}" for q in ("maj", "min", "7", "min7")]
        for following in [*followings, "N", None]:
            cases.append(_two_chords(label, following, "A:min"))
    for label, key, target in CONTROLS:
        for following in (target, "N"):
            cases.append(_two_chords(label, following, key))
    # Key estimation in all 24 keys, which also pins the root arithmetic away from C and A.
    for key in KEYS:
        tonic, mode = key.split(":")
        for name, template in KEY_TEMPLATES[mode].items():
            progression = [
                ("N", beats) if offset is None else (f"{_up(tonic, offset)}:{quality}", beats)
                for offset, quality, beats in template
            ]
            cases.append(_progression_case(f"{name} in {key}", progression, None))
    for name, key, progression in TIES:
        cases.append(_progression_case(name, progression, key))
    return cases


def _inversions() -> list[list]:
    pairs = [
        (f"{root}:{quality}", bass)
        for root in ("C", "F#")
        for quality in QUALITIES
        for bass in ROOTS
    ]
    pairs += [("N", "C"), ("C:maj", None)]
    return [[label, bass, chords.inversion(label, bass)] for label, bass in pairs]


def _runs() -> list[dict]:
    cases = []
    for name, spans in RUNS.items():
        segments = [{"chord": c, "start_beat": start, "end_beat": end} for c, start, end in spans]
        runs = timeline.chord_runs(segments)
        cases.append(
            {
                "name": name,
                "segments": segments,
                "expected": {
                    "sizes": [len(run) for run in runs],
                    "progression": timeline.progression(runs),
                },
            }
        )
    return cases


def cases() -> dict:
    return {"progressions": _progressions(), "inversions": _inversions(), "runs": _runs()}


def main() -> None:
    # One case per line, so a change to the analysis shows up as a reviewable diff.
    sections = []
    for name, items in cases().items():
        rows = ",\n".join(json.dumps(item, ensure_ascii=False) for item in items)
        sections.append(f"{json.dumps(name)}: [\n{rows}\n]")
    PATH.write_text("{\n" + ",\n".join(sections) + "\n}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
