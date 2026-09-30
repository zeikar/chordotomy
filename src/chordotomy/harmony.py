"""Harmonic analysis: a pure function of the chord sequence (no audio)."""

from __future__ import annotations

from collections import Counter

from .chords import QUALITIES, ROOTS

KEYS = [f"{root}:{mode}" for root in ROOTS for mode in ("maj", "min")]
FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
SCALE = {"maj": {0, 2, 4, 5, 7, 9, 11}, "min": {0, 2, 3, 5, 7, 8, 10}}
# The tonic outweighs IV and V, which outweigh the other degrees (1; a chord that is not diatonic
# weighs 0), so time spent on I, IV and V decides between keys that share most of their triads.
DEGREE_WEIGHT = {0: 3, 5: 2, 7: 2}


def parse_key(text: str) -> str:
    """Normalize `<root>:maj|min` (flat roots allowed) to the sharp-only key label."""
    root, _, mode = text.partition(":")
    root = FLATS.get(root, root)
    if root not in ROOTS or mode not in ("maj", "min"):
        raise ValueError(
            f"{text!r} is not a key; use <root>:maj or <root>:min, e.g. C:maj, A:min, Bb:maj"
        )
    return f"{root}:{mode}"


def _is_diatonic(offset: int, quality: str, mode: str) -> bool:
    # The harmonic-minor dominant is the one place the raised leading tone is admitted, so it
    # does not make F-G#-C diatonic.
    if mode == "min" and offset == 7 and quality in ("maj", "7"):
        return True
    return all((offset + interval) % 12 in SCALE[mode] for interval in QUALITIES[quality])


def estimate_key(progression: list[tuple[str, int]]) -> list[str]:
    """Rank all 24 keys for a list of (chord label, beats); empty if there is no chord."""
    beats = Counter[str]()
    for label, n in progression:
        if label != "N":
            beats[label] += n
    if not beats:
        return []
    first = next(label for label, _ in progression if label != "N")

    def rank(key: str) -> tuple[int, int, bool]:
        tonic, mode = key.split(":")
        tonic_index = ROOTS.index(tonic)
        score = 0
        for label, n in beats.items():
            root, quality = label.split(":")
            offset = (ROOTS.index(root) - tonic_index) % 12
            if _is_diatonic(offset, quality, mode):
                score += n * DEGREE_WEIGHT.get(offset, 1)
        return score, beats[key], first == key

    # sorted is stable, also with reverse=True, so KEYS order is the final tie-break.
    return sorted(KEYS, key=rank, reverse=True)
