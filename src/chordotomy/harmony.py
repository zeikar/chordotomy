"""Harmonic analysis: a pure function of the chord sequence (no audio)."""

from __future__ import annotations

from collections import Counter

from .chords import QUALITIES, ROOTS

KEYS = [f"{root}:{mode}" for root in ROOTS for mode in ("maj", "min")]
FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E"}
SCALE = {"maj": {0, 2, 4, 5, 7, 9, 11}, "min": {0, 2, 3, 5, 7, 8, 10}}
# The tonic outweighs IV and V, which outweigh the other degrees (1; a chord that is not diatonic
# weighs 0), so time spent on I, IV and V decides between keys that share most of their triads.
DEGREE_WEIGHT = {0: 3, 5: 2, 7: 2}
# Accidentals are relative to the key's own scale, so minor spells its natural-minor degrees plain.
NUMERALS = {
    "maj": ("I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII"),
    "min": ("I", "bII", "II", "III", "#III", "IV", "#IV", "V", "VI", "#VI", "VII", "#VII"),
}
# Case shows the third: lowercase for a minor or diminished one; sus4 has none and stays upper.
LOWERCASE = {"min", "min7", "min6", "hdim7", "dim7"}
# min6 is `add6` because `iv6` is the first-inversion figure, and `add6` cannot be read as one.
# ø and ° are the characters themselves, not ASCII stand-ins: the viewer turns only the b and #
# accidentals into glyphs, so a stand-in would reach the reader as a letter.
NUMERAL_SUFFIX = {
    "maj": "",
    "min": "",
    "7": "7",
    "maj7": "maj7",
    "min7": "7",
    "min6": "add6",
    "hdim7": "ø7",
    "dim7": "°7",
    "sus4": "sus4",
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
# Triads a secondary dominant or leading-tone chord can tonicize, by root offset: the tonic and
# the diminished degrees are excluded, and minor's degree 5 is written V, as its harmonic-minor
# dominant.
TARGETS = {
    "maj": {2: "ii", 4: "iii", 5: "IV", 7: "V", 9: "vi"},
    "min": {3: "III", 5: "iv", 7: "V", 8: "VI", 10: "VII"},
}
PARALLEL = {"maj": "min", "min": "maj"}
CANDIDATES = 3


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
    # The raised leading tone is admitted in two harmonic-minor chords only, the dominant (V, V7)
    # and the diminished seventh on the leading tone (#vii°7), so it does not make F-G#-C diatonic.
    if mode == "min" and (
        (offset == 7 and quality in ("maj", "7")) or (offset == 11 and quality == "dim7")
    ):
        return True
    return all((offset + interval) % 12 in SCALE[mode] for interval in QUALITIES[quality])


def _resolves(following: str | None, root: str, tonic: str, mode: str) -> bool:
    if following is None or following == "N":
        return False
    following_root, quality = following.split(":")
    offset = (ROOTS.index(following_root) - ROOTS.index(tonic)) % 12
    return following_root == root and _is_diatonic(offset, quality, mode)


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
    # A diminished or half-diminished seventh leads up a semitone, so its root is the raised degree
    # below, never the flattened one above: C#:dim7 in C major is #i°7, pointing at ii, not bii°7.
    # The degree below a flat one is always plain.
    if quality in ("dim7", "hdim7") and text.startswith("b"):
        text = "#" + NUMERALS[mode][offset - 1]
    if quality in LOWERCASE:
        text = text.lower()
    return text + NUMERAL_SUFFIX[quality]


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
        # The degree names the function; only minor's #VII carries an accidental to strip.
        function = FUNCTIONS[NUMERALS[mode][offset].lstrip("#b")]
        return {"numeral": text, "role": "diatonic", "function": function, "target": None}
    target_offset = (offset - 7) % 12
    secondary = quality in ("maj", "7") and target_offset in TARGETS[mode]
    borrowed = _is_diatonic(offset, quality, PARALLEL[mode])
    if secondary:
        target = TARGETS[mode][target_offset]
        resolution = ROOTS[(ROOTS.index(tonic) + target_offset) % 12]
        # Only the major triads on the tonic and subdominant of a minor key are also borrowed, and
        # for those the very next chord being diatonic on the target's root is the one thing that
        # tells V/VII from a borrowed IV (G:maj and G:7 both resolve it; D:7 does not resolve
        # A:maj, as it is not diatonic); another chord or an N is no resolution.
        # Outside this overlap and the leading-tone chords below, `following` is ignored, so a
        # label depends on the chord and key alone.
        if not borrowed or _resolves(following, resolution, tonic, mode):
            text = ("V7" if quality == "7" else "V") + "/" + target
            return {
                "numeral": text,
                "role": "secondary_dominant",
                "function": None,
                "target": target,
            }
    if quality in ("dim7", "hdim7"):
        # The fifth relation of a dominant identifies it on its own; a leading-tone chord only by
        # where it goes, so it takes the same resolution test as the overlap above, always.
        target_offset = (offset + 1) % 12
        resolution = ROOTS[(ROOTS.index(tonic) + target_offset) % 12]
        if target_offset in TARGETS[mode] and _resolves(following, resolution, tonic, mode):
            target = TARGETS[mode][target_offset]
            return {
                "numeral": "vii" + NUMERAL_SUFFIX[quality] + "/" + target,
                "role": "secondary_dominant",
                "function": None,
                "target": target,
            }
    if borrowed:
        return {"numeral": text, "role": "borrowed", "function": None, "target": None}
    return {"numeral": text, "role": "chromatic", "function": None, "target": None}


def analyze(
    progression: list[tuple[str, int]], key: str | None = None
) -> tuple[dict | None, list[dict]]:
    """Analyze a list of (chord label, beats) into a key object and one analysis per entry.

    `key`, if given, must already be normalized by `parse_key`. The key object is `None` only
    when there is no chord to estimate from and no key was given.
    """
    ranked = estimate_key(progression)
    if key is None and not ranked:
        # Every entry is N here, and an N is analyzed without looking at the key.
        return None, [analyze_chord("N", "C:maj") for _ in progression]
    label = key or ranked[0]
    # The candidates stay the estimator's ranking even when the key is given, so a wrong
    # override can be compared against what the chords suggest.
    key_object = {
        "label": label,
        "source": "estimated" if key is None else "given",
        "candidates": ranked[:CANDIDATES],
    }
    labels = [chord for chord, _ in progression]
    analyses = [
        analyze_chord(chord, label, following)
        for chord, following in zip(labels, [*labels[1:], None], strict=True)
    ]
    return key_object, analyses
