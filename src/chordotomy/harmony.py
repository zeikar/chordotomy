"""Harmonic analysis: a pure function of the chord sequence (no audio).

The key is estimated for the whole song, and per key region, the stretch a modulating song spends
in one key; each chord is analyzed against its region's key.
"""

from __future__ import annotations

from collections import Counter
from itertools import groupby

from .chords import QUALITIES, ROOTS

KEYS = [f"{root}:{mode}" for root in ROOTS for mode in ("maj", "min")]
FLATS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E"}
SCALE = {"maj": {0, 2, 4, 5, 7, 9, 11}, "min": {0, 2, 3, 5, 7, 8, 10}}
# The tonic outweighs IV and V, which outweigh the other degrees (1; a chord that is not diatonic
# weighs 0), so time spent on I, IV and V decides between keys that share most of their triads.
DEGREE_WEIGHT = {0: 3, 5: 2, 7: 2}
# What a key change costs, in the unit of the weights (beats × degree weight): a stretch becomes a
# region of its own only when it reads more than that much better in another key. Two real songs
# put the working range at 16–32, and synthesized ones bound it: a ii–V7/ii vamp and Fm–Bb inside a
# C-major verse (36 better in D minor) split at 16 and hold at 24; a 20-beat half-step ending,
# F–C–Bb–C ×2, F (48 in F, 0 in the song's E major), is kept through 44 and lost at 48, where it
# gains only what the change costs; and a C-major verse with an A-minor chorus, Am–Dm–E7 ×4, stays
# one region at 24 only with the relative rule below.
KEY_CHANGE_PENALTY = 24
# Relative keys share a scale, so only the degree weights tell them apart, and a switch between
# them follows where the time goes inside a section rather than a modulation: a real song split
# into C-sharp minor and E major over chords both keys share. So no region switches straight to its
# relative. A third key can still bridge them: at a penalty of 12 to 15 the A-minor chorus above
# goes C, D minor, C, as D minor reads it 32 better than C, and the estimator names that region A
# minor.
RELATIVE = {f"{root}:maj": f"{ROOTS[(i + 9) % 12]}:min" for i, root in enumerate(ROOTS)}
RELATIVE |= {minor: major for major, minor in RELATIVE.items()}
# Accidentals are relative to the key's own scale, so minor spells its natural-minor degrees plain.
NUMERALS = {
    "maj": ("I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII"),
    "min": ("I", "bII", "II", "III", "#III", "IV", "#IV", "V", "VI", "#VI", "VII", "#VII"),
}
# Case shows the third: lowercase for a minor or diminished one; sus4, sus2 and sus4(b7) have none
# and stay upper.
LOWERCASE = {"min", "min7", "min6", "hdim7", "dim7", "dim", "min(9)"}
# min6 is `add6` because `iv6` is the first-inversion figure, and `add6` cannot be read as one; the
# added ninths are `add9` for the same reason, as `I9` would read as a ninth chord.
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
    "maj(9)": "add9",
    "min(9)": "add9",
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
# Each tetrad's triad, below its seventh (or min6's sixth, or an added ninth), for the
# borrowed-seventh rule. The
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
    "maj(9)": "maj",
    "min(9)": "min",
}
# The chords a secondary dominant can be: a major triad, alone or with a seventh or an added ninth.
DOMINANTS = ("maj", "7", "maj(9)")
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
    # A tonic seventh chord (Cmaj7, Am7) or added ninth (Cadd9) settles a key as its triad does,
    # so the tie-breaks compare it to the key label as that triad.
    root, quality = label.split(":")
    triad = {"maj7": "maj", "min7": "min", "maj(9)": "maj", "min(9)": "min"}.get(quality, quality)
    return f"{root}:{triad}"


def _weight(label: str, key: str) -> int:
    # One beat's weight, shared by the estimator and the key regions.
    if label == "N":
        return 0
    tonic, mode = key.split(":")
    root, quality = label.split(":")
    offset = (ROOTS.index(root) - ROOTS.index(tonic)) % 12
    return DEGREE_WEIGHT.get(offset, 1) if _is_diatonic(offset, quality, mode) else 0


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
        score = sum(n * _weight(label, key) for label, n in beats.items())
        return score, tonic_beats[key], first == key

    # sorted is stable, also with reverse=True, so KEYS order is the final tie-break.
    return sorted(KEYS, key=rank, reverse=True)


def _region_keys(progression: list[tuple[str, int]], penalty: int) -> list[str]:
    # A Viterbi path over the 24 keys, one per run, scoring the runs' weights in their keys less
    # `penalty` per change. A path's score is the pair (that sum, minus its changes), so of two
    # paths that sum the same the one with fewer changes wins: a change that gains only the penalty
    # never splits, wherever it sits and whichever key comes first in KEYS. The path decides only
    # where the regions lie: each is named by the estimator over its own runs, so a single region
    # is named as the whole song is.
    label, n = progression[0]
    best = {key: (n * _weight(label, key), 0) for key in KEYS}
    back = []
    for label, n in progression[1:]:
        pointers, scores = {}, {}
        for current in KEYS:
            # max keeps the first of equal scores, so a tie goes to the earliest in KEYS.
            source = max(
                (other for other in KEYS if other not in (current, RELATIVE[current])),
                key=best.__getitem__,
            )
            stay = best[current]
            switch = (best[source][0] - penalty, best[source][1] - 1)
            # Switching on a tie puts each change as late as it can go, so a run that weighs the
            # same in both keys (an N, a pivot chord) stays with the key before it.
            pointers[current] = source if switch >= stay else current
            total, minus_changes = max(stay, switch)
            scores[current] = (total + n * _weight(label, current), minus_changes)
        back.append(pointers)
        best = scores
    # Of paths with equal sums and equal changes, the one ending in the earliest key in KEYS.
    path = [max(KEYS, key=best.__getitem__)]
    for pointers in reversed(back):
        path.append(pointers[path[-1]])
    path.reverse()
    run_keys: list[str] = []
    for _, group in groupby(path):
        start = len(run_keys)
        end = start + len(list(group))
        ranked = estimate_key(progression[start:end])
        # A stretch of only N is a stepping stone to the relative key (C, N, then A minor). With a
        # positive penalty it is never the first, as a leading N keeps the first chord's key at no
        # cost, and it stays with the key before it, as any N at a change does.
        run_keys += [ranked[0] if ranked else run_keys[-1]] * (end - start)
    return run_keys


def _regions(progression: list[tuple[str, int]], run_keys: list[str]) -> list[dict]:
    # Neighbours named alike are one region.
    regions: list[dict] = []
    beat = 0
    for (_, n), key in zip(progression, run_keys, strict=True):
        if regions and regions[-1]["label"] == key:
            regions[-1]["end_beat"] += n
        else:
            regions.append({"start_beat": beat, "end_beat": beat + n, "label": key})
        beat += n
    return regions


def key_regions(
    progression: list[tuple[str, int]], penalty: int = KEY_CHANGE_PENALTY
) -> list[dict]:
    """Split a list of (chord label, beats) into key regions; empty if there is no chord.

    Each region is `{"start_beat", "end_beat", "label"}`; they are contiguous from beat 0 to the
    total. `penalty` is what a key change costs, in beats × degree weight, and must be positive.
    """
    if all(label == "N" for label, _ in progression):
        return []
    return _regions(progression, _region_keys(progression, penalty))


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
    # a sus4(b7): no third, so no leading tone. An added ninth keeps the triad's leading tone, so a
    # maj(9) counts as its triad does; a maj7 does not, its major seventh no dominant's.
    secondary = quality in DOMINANTS and target_offset in TARGETS[mode]
    borrowed = _is_borrowed(offset, quality, mode)
    if secondary:
        target = TARGETS[mode][target_offset]
        resolution = ROOTS[(ROOTS.index(tonic) + target_offset) % 12]
        # Only the major triads on the tonic and subdominant of a minor key, alone or with an added
        # ninth, are also chords of the parallel mode, and for those the very next chord being
        # diatonic on the target's root is the one thing that tells V/VII from a borrowed IV (G:maj
        # and G:7 both resolve it; D:7 does not resolve A:maj, as it is not diatonic); another
        # chord or an N is no resolution.
        # The borrowed-seventh rule does not widen this overlap, so I7 and IV7 in minor stay V7/iv
        # and V7/VII wherever they go.
        # Outside this overlap and the leading-tone chords below, `following` is ignored, so a
        # label depends on the chord and key alone.
        if not _is_diatonic(offset, quality, PARALLEL[mode]) or _resolves(
            following, resolution, tonic, mode
        ):
            text = "V" + NUMERAL_SUFFIX[quality] + "/" + target
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
) -> tuple[dict | None, list[dict], list[dict]]:
    """Analyze a list of (chord label, beats) into a key, key regions and one analysis per entry.

    The key object is the whole song's. `key`, if given, must already be normalized by
    `parse_key`; it is then the one region and every entry is analyzed in it. Otherwise the
    regions are those of `key_regions`, and each entry is analyzed in its region's key. The key
    object is `None`, and the regions empty, only when there is no chord to estimate from and no
    key was given.
    """
    ranked = estimate_key(progression)
    if key is None and not ranked:
        # Every entry is N here, and an N is analyzed without looking at the key.
        return None, [], [analyze_chord("N", "C:maj") for _ in progression]
    label = key or ranked[0]
    # The candidates stay the estimator's ranking even when the key is given, so a wrong
    # override can be compared against what the chords suggest.
    key_object = {
        "label": label,
        "source": "estimated" if key is None else "given",
        "candidates": ranked[:CANDIDATES],
    }
    if key is None:
        run_keys = _region_keys(progression, KEY_CHANGE_PENALTY)
    else:
        run_keys = [key] * len(progression)
    labels = [chord for chord, _ in progression]
    # The look-ahead reads the next run whatever its region.
    analyses = [
        analyze_chord(chord, run_key, following)
        for chord, run_key, following in zip(labels, run_keys, [*labels[1:], None], strict=True)
    ]
    return key_object, _regions(progression, run_keys), analyses
