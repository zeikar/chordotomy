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
# Accidentals are relative to the key's own scale, so minor spells its natural-minor degrees plain.
NUMERALS = {
    "maj": ("I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII"),
    "min": ("I", "bII", "II", "III", "#III", "IV", "#IV", "V", "VI", "#VI", "VII", "#VII"),
}
# Tonic substitutes on III / VI; VII is the subtonic dominant in minor.
FUNCTIONS = {
    "I": "tonic",
    "II": "predominant",
    "III": "tonic",
    "IV": "predominant",
    "V": "dominant",
    "VI": "tonic",
    "VII": "dominant",
}
# Triads a secondary dominant can tonicize, by root offset: the tonic and the diminished degrees
# are excluded, and minor's degree 5 is written V, as its harmonic-minor dominant.
TARGETS = {
    "maj": {2: "ii", 4: "iii", 5: "IV", 7: "V", 9: "vi"},
    "min": {3: "III", 5: "iv", 7: "V", 8: "VI", 10: "VII"},
}
PARALLEL = {"maj": "min", "min": "maj"}


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


def numeral(offset: int, quality: str, mode: str) -> str:
    text = NUMERALS[mode][offset]
    if quality == "min":
        text = text.lower()
    return text + "7" if quality == "7" else text


def analyze_chord(label: str, key: str, following: str | None = None) -> dict[str, str | None]:
    """Classify one chord against a key: numeral, role, function and target.

    `following` is the label of the next segment (`N` included), `None` for the last one.
    """
    if label == "N":
        return {"numeral": None, "role": None, "function": None, "target": None}
    tonic, mode = key.split(":")
    root, quality = label.split(":")
    offset = (ROOTS.index(root) - ROOTS.index(tonic)) % 12
    text = numeral(offset, quality, mode)
    if _is_diatonic(offset, quality, mode):
        # Diatonic numerals carry no accidental, so case and the 7 are all to strip.
        function = FUNCTIONS[text.upper().removesuffix("7")]
        return {"numeral": text, "role": "diatonic", "function": function, "target": None}
    target_offset = (offset - 7) % 12
    secondary = quality in ("maj", "7") and target_offset in TARGETS[mode]
    borrowed = _is_diatonic(offset, quality, PARALLEL[mode])
    if secondary:
        target = TARGETS[mode][target_offset]
        resolution = ROOTS[(ROOTS.index(tonic) + target_offset) % 12]
        resolution += ":min" if target.islower() else ":maj"
        # Only the major triads on the tonic and subdominant of a minor key are also borrowed, and
        # for those the very next chord being the target triad is the one thing that tells V/iv
        # from a borrowed I; a seventh on the target, another chord or an N is no resolution.
        # Everywhere else `following` is ignored, so a label depends on the chord and key alone.
        if not borrowed or following == resolution:
            text = ("V7" if quality == "7" else "V") + "/" + target
            return {
                "numeral": text,
                "role": "secondary_dominant",
                "function": None,
                "target": target,
            }
    if borrowed:
        return {"numeral": text, "role": "borrowed", "function": None, "target": None}
    return {"numeral": text, "role": "chromatic", "function": None, "target": None}
