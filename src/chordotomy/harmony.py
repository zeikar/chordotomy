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
# Case shows the third: lowercase for a minor or diminished one; sus4, sus2 and sus4(b7) have none
# and stay upper.
LOWERCASE = {"min", "min7", "min6", "hdim7", "dim7", "dim"}
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
    "aug": "+",
    "dim": "°",
    "sus2": "sus2",
    "sus4(b7)": "7sus4",
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
# Each tetrad's triad, below its seventh (or min6's sixth), for the borrowed-seventh rule. The
# sus4(b7) entry keeps the table complete for every tetrad; for this quality the parallel-mode test
# already covers every borrowed case, so it changes no classification.
TRIAD = {
    "7": "maj",
    "maj7": "maj",
    "min7": "min",
    "min6": "min",
    "hdim7": "dim",
    "dim7": "dim",
    "sus4(b7)": "sus4",
}
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
    # The raised leading tone is admitted in five harmonic-minor chords and nowhere else: the
    # dominant (V, V7), the diminished triad and seventh on the leading tone (#vii°, #vii°7) and
    # the augmented mediant (III+). So it does not make F-G#-C or E-G#-C diatonic.
    if mode == "min" and (
        (offset == 7 and quality in ("maj", "7"))
        or (offset == 11 and quality in ("dim", "dim7"))
        or (offset == 3 and quality == "aug")
    ):
        return True
    return all((offset + interval) % 12 in SCALE[mode] for interval in QUALITIES[quality])


def _is_borrowed(offset: int, quality: str, mode: str) -> bool:
    # A chord of the parallel mode, or a tetrad on one of its triads whose fourth tone lies in
    # either mode: a seventh the borrowed triad takes from home is still borrowed color. So in
    # major bVIImaj7, ii°7 (the notes of the borrowed vii°7), iadd6 and vadd6 are borrowed. In
    # minor the rule would also cover I7 and IV7, but the secondary dominant claims them first. A
    # triad of the home mode with a foreign seventh stays chromatic (IV7 in major, VIImaj7 and
    # iadd6 in minor), as do sevenths outside both scales (bIII7, bVI7, Vmaj7). This only widens
    # what borrowed covers; the precedence stays diatonic, secondary dominant, leading-tone chord,
    # borrowed, chromatic.
    parallel = PARALLEL[mode]
    if _is_diatonic(offset, quality, parallel):
        return True
    if quality not in TRIAD:
        return False
    fourth = (offset + QUALITIES[quality][3]) % 12
    return _is_diatonic(offset, TRIAD[quality], parallel) and (
        fourth in SCALE[mode] or fourth in SCALE[parallel]
    )


def _resolves(following: str | None, root: str, tonic: str, mode: str) -> bool:
    if following is None or following == "N":
        return False
    following_root, quality = following.split(":")
    offset = (ROOTS.index(following_root) - ROOTS.index(tonic)) % 12
    return following_root == root and _is_diatonic(offset, quality, mode)


def _tonic_triad(label: str) -> str:
    # A tonic seventh chord (Cmaj7, Am7) settles a key as its triad does, so the tie-breaks
    # compare it to the key label as that triad.
    root, quality = label.split(":")
    triad = {"maj7": "maj", "min7": "min"}.get(quality, quality)
    return f"{root}:{triad}"


def estimate_key(progression: list[tuple[str, int]]) -> list[str]:
    """Rank all 24 keys for a list of (chord label, beats); empty if there is no chord."""
    beats = Counter[str]()
    tonic_beats = Counter[str]()
    for label, n in progression:
        if label != "N":
            beats[label] += n
            tonic_beats[_tonic_triad(label)] += n
    if not beats:
        return []
    first = _tonic_triad(next(label for label, _ in progression if label != "N"))

    def rank(key: str) -> tuple[int, int, bool]:
        tonic, mode = key.split(":")
        tonic_index = ROOTS.index(tonic)
        score = 0
        for label, n in beats.items():
            root, quality = label.split(":")
            offset = (ROOTS.index(root) - tonic_index) % 12
            if _is_diatonic(offset, quality, mode):
                score += n * DEGREE_WEIGHT.get(offset, 1)
        return score, tonic_beats[key], first == key

    # sorted is stable, also with reverse=True, so KEYS order is the final tie-break.
    return sorted(KEYS, key=rank, reverse=True)


def numeral(offset: int, quality: str, mode: str) -> str:
    text = NUMERALS[mode][offset]
    # A diminished chord or a half-diminished seventh leads up a semitone, so its root is the raised
    # degree below, never the flattened one above: C#:dim7 in C major is #i°7, pointing at ii, not
    # bii°7. The degree below a flat one is always plain.
    if quality in ("dim7", "hdim7", "dim") and text.startswith("b"):
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
    # An augmented triad never counts: it is symmetric, so its root is the bass's or
    # resolve_twins's spelling, not a fifth relation that identifies it, and C+ = E+ = G#+ would be
    # V+/IV, V+/vi or bVI+ by tie-break alone. sus2 never counts either, as sus4 does not, nor does
    # a sus4(b7): no third, so no leading tone.
    secondary = quality in ("maj", "7") and target_offset in TARGETS[mode]
    borrowed = _is_borrowed(offset, quality, mode)
    if secondary:
        target = TARGETS[mode][target_offset]
        resolution = ROOTS[(ROOTS.index(tonic) + target_offset) % 12]
        # Only the major triads on the tonic and subdominant of a minor key are also chords of the
        # parallel mode, and for those the very next chord being diatonic on the target's root is
        # the one thing that tells V/VII from a borrowed IV (G:maj and G:7 both resolve it; D:7
        # does not resolve A:maj, as it is not diatonic); another chord or an N is no resolution.
        # The borrowed-seventh rule does not widen this overlap, so I7 and IV7 in minor stay V7/iv
        # and V7/VII wherever they go.
        # Outside this overlap and the leading-tone chords below, `following` is ignored, so a
        # label depends on the chord and key alone.
        if not _is_diatonic(offset, quality, PARALLEL[mode]) or _resolves(
            following, resolution, tonic, mode
        ):
            text = ("V7" if quality == "7" else "V") + "/" + target
            return {
                "numeral": text,
                "role": "secondary_dominant",
                "function": None,
                "target": target,
            }
    if quality in ("dim7", "hdim7", "dim"):
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
