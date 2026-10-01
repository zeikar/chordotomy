"""Chord vocabulary, template scoring and decoding.

The scoring and the no-chord handling follow the ideas of Mauch & Dixon, "Approximate Note
Transcription for the Improved Identification of Difficult Chords" (ISMIR 2010), implemented from
the paper, not from their GPL-licensed plugin.
"""

from __future__ import annotations

from collections import Counter
from itertools import groupby, pairwise

import numpy as np

ROOTS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
# Left out, for the reasons in docs/ARCHITECTURE.md: maj6 (min7's pitch set), sus2 (sus4's), the
# augmented and diminished triads, and extensions (9, 11, 13, add9).
QUALITIES = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "min6": (0, 3, 7, 9),
    "hdim7": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "sus4": (0, 5, 7),
}
# Quality-major, and the order is the tie-break: smooth takes the first argmax.
# Pitch-set twins score exactly alike without bass evidence (G:min6 and E:hdim7; the four dim7
# labels on one set), and then the earlier label wins: min6 over hdim7, the lowest root of a dim7.
# resolve_twins then respells a diminished twin by where it leads.
LABELS = [f"{root}:{quality}" for quality in QUALITIES for root in ROOTS] + ["N"]
# A tone's first four partials in semitones above it: the fundamental, the octave, the twelfth
# and the double octave. Partial k weighs PARTIAL_DECAY ** (k - 1) in a template.
PARTIALS = (0, 12, 19, 24)
# A triad's own partials land on tetrad tones: the third's twelfth on the seventh (E -> B under
# C, C -> G under A:min), the fifth's on the ninth, and whitening lifts a lone partial in a
# sparse region. A template that expects those partials stops reading them as a tetrad. 0 gives
# binary templates; a sweep rebuilds the table for each decay it tries.
PARTIAL_DECAY = 0.8


def _build_templates(decay: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Chord tones, chord tones with their partials, and one-hot roots; one row per label but N.

    The binary chord tones are what the bass profiles are built from.
    """
    partials = np.zeros(12)
    for k, semitones in enumerate(PARTIALS, start=1):
        partials[semitones % 12] += decay ** (k - 1)
    tones = np.zeros((len(LABELS) - 1, 12))
    templates = np.zeros((len(LABELS) - 1, 12))
    roots = np.zeros((len(LABELS) - 1, 12))
    for row, label in enumerate(LABELS[:-1]):
        root, quality = label.split(":")
        classes = sorted((ROOTS.index(root) + i) % 12 for i in QUALITIES[quality])
        tones[row, classes] = 1.0
        # Summed in pitch-class order, so labels on one pitch set get the same row to the last
        # bit and the twins tie exactly.
        for pitch_class in classes:
            templates[row] += np.roll(partials, pitch_class)
        roots[row, ROOTS.index(root)] = 1.0
    return tones, templates, roots


TONES, TEMPLATES, ROOT_TEMPLATES = _build_templates(PARTIAL_DECAY)

# N is not a template. A flat template out-scores a triad whenever its tones are under 3.0x the
# other bins, which a real mix's chroma always is (research pitfall 1). Instead a chord has to
# beat this constant, and correlation gives a flat chroma 0 against every chord.
N_SCORE = 0.3
# BASS_WEIGHT, BASS_TONE, TEMPERATURE, CHORD_SECONDS, QUALITY_OFFSET and PARTIAL_DECAY are tuned
# together on the planned grid: GuitarSet sevenths under Tiny AAM's floors, with the synthesized
# suite green. PARTIAL_DECAY then moved from 0.6 to 0.8 at a cost (0.3 pp of GuitarSet sevenths,
# 0.5-0.6 pp of Tiny AAM) so that no one-step move breaks the two-beat A:min/C inside C:maj.
# TEMPERATURE 0.035, BASS_TONE 0.6 and maj7/min7 -0.05 score higher, but give up that margin or
# Tiny AAM's sevenths floor a step later; see "Tuning the v4 constants" in docs/ARCHITECTURE.md.
# The weight of the bass chroma's evidence for a chord, against the treble's correlation.
BASS_WEIGHT = 0.3
# A chord's bass profile is 1 on its root and BASS_TONE on its other tones. A bass on the third
# or fifth still supports the chord, so the treble decides Am/C against C and G/B against Bm;
# the root counts more, so a root bass settles the ties the treble cannot (G:min6 against
# E:hdim7).
BASS_TONE = 0.7
# Sharpens score gaps into likelihood ratios: a gap g on one beat is worth g / TEMPERATURE nats
# against the transition cost. Too high and two-beat chord changes are smoothed away. The
# self-loop spreads what it leaves over the other 108 labels, so at period 0.5 leaving a chord and
# coming back costs about 12.6 nats. The suite's binding case, the two-beat A:min/C inside C:maj
# at 0.24 per beat, holds up to 0.039.
TEMPERATURE = 0.03
# The expected chord length in seconds, not beats, so a tracker locked at half or double tempo
# does not halve or double it (research pitfall 3).
CHORD_SECONDS = 2.8
# A beat this far below the track's loud beats is no chord. Whitening is scale-free, so without
# the gate a silent beat's residual ringing would whiten into a chord.
N_GATE_DB = 40
# Added to every label of a quality, so a tetrad or a sus has to beat its triad by evidence.
# match reads it on each call, so a sweep can assign entries.
QUALITY_OFFSET = {
    "maj": 0.0,
    "min": 0.0,
    # The templates model four partials at one decay; a real tone's higher ones still land on its
    # triad's seventh (the fifth's 5th harmonic on the major seventh, the root's 7th just under
    # the minor seventh). Each has to stay under what a played seventh gains over its triad; the 7
    # needs none to hold Tiny AAM's floors.
    "7": 0.0,
    "maj7": -0.1,
    "min7": -0.1,
    # One value for both twins (G:min6 is E:hdim7's pitch set), so the bass, not the offset, tells
    # them apart.
    "min6": -0.1,
    "hdim7": -0.1,
    # A 7 chord with a weak root leaves three of a dim7's four tones (E G Bb of C:7 in C#:dim7).
    "dim7": -0.1,
    # The largest: Tiny AAM, annotated in maj and min only, scores every sus4 call as a miss, and a
    # played sus4 clears its maj by more than a played seventh clears its triad. Pinned from both
    # sides: at -0.2 Tiny AAM's root falls under its floor; the suite's four-beat G:sus4 clears
    # G:maj by 0.27 over its beats here, so at -0.3 it falls under the 0.19 an extra chord change
    # costs and is smoothed into the G:maj after it.
    "sus4": -0.25,
}


def _correlate(templates: np.ndarray, chroma: np.ndarray) -> np.ndarray:
    """Correlation of each template row (m, 12) with each chroma column (12, n), shape (m, n).

    Both sides are centred and unit-normed over the 12 pitch classes; a column with no variation
    (silent or flat) has no shape to correlate and scores 0.
    """
    t = templates - templates.mean(axis=1, keepdims=True)
    t = t / np.linalg.norm(t, axis=1, keepdims=True)
    c = chroma - chroma.mean(axis=0, keepdims=True)
    norm = np.linalg.norm(c, axis=0, keepdims=True)
    c = np.divide(c, norm, out=np.zeros_like(c), where=norm > 0)
    return t @ c


def match(treble: np.ndarray, bass: np.ndarray) -> np.ndarray:
    """Score treble and bass chroma columns (12, n) against every label, shape (109, n).

    A chord's score is the correlation of the treble chroma with its template, in [-1, 1], plus
    BASS_WEIGHT times the correlation of the bass chroma with its bass profile, plus its quality's
    QUALITY_OFFSET. The last row (N) is the constant N_SCORE.
    """
    profiles = ROOT_TEMPLATES + BASS_TONE * (TONES - ROOT_TEMPLATES)
    offset = np.array([QUALITY_OFFSET[label.split(":")[1]] for label in LABELS[:-1]])
    chords = _correlate(TEMPLATES, treble) + BASS_WEIGHT * _correlate(profiles, bass)
    return np.vstack([chords + offset[:, None], np.full((1, treble.shape[1]), N_SCORE)])


def smooth(scores: np.ndarray, level: np.ndarray, durations: np.ndarray) -> np.ndarray:
    """Viterbi-decode (109, n) scores into one label index per beat.

    level is each beat's loudness in dB relative to the track's loud beats; a beat below
    -N_GATE_DB can only be N. durations is (n - 1,) seconds, the gap from each beat to the next.

    This is librosa.sequence.viterbi with one self-loop matrix per transition instead of one per
    track, and its arithmetic step for step (the log of each likelihood and transition plus tiny,
    a uniform start, the first index on ties), so on a constant grid the path is librosa's.
    """
    # Shifting a column by its maximum leaves the path unchanged and keeps every value in (0, 1].
    likelihood = np.exp((scores - scores.max(axis=0, keepdims=True)) / TEMPERATURE)
    likelihood[:-1, level < -N_GATE_DB] = 0.0  # every chord row; N is the last
    tiny = np.finfo(float).tiny
    log_likelihood = np.log(likelihood + tiny)
    # The chance that chord changes, arriving every CHORD_SECONDS on average, fire none within
    # the beat. Per beat, in seconds, so a grid whose period changes inside a file keeps the
    # expected chord length in seconds. Unlike 1 - duration / CHORD_SECONDS it stays in (0, 1)
    # when a beat is longer than a chord, as on a half-tempo grid.
    stay = np.exp(-durations / CHORD_SECONDS)
    log_stay = np.log(stay + tiny)
    log_switch = np.log((1.0 - stay) / (len(LABELS) - 1) + tiny)
    diagonal = np.eye(len(LABELS), dtype=bool)
    n = scores.shape[1]
    value = log_likelihood[:, 0] + np.log(1.0 / len(LABELS) + tiny)
    back = np.empty((n - 1, len(LABELS)), dtype=int)
    for i in range(n - 1):
        # candidates[k, j]: the best path into label k at beat i, then k -> j.
        candidates = value[:, None] + np.where(diagonal, log_stay[i], log_switch[i])
        back[i] = candidates.argmax(axis=0)
        value = candidates[back[i], np.arange(len(LABELS))] + log_likelihood[:, i + 1]
    path = np.empty(n, dtype=int)
    path[-1] = value.argmax()
    for i in range(n - 2, -1, -1):
        path[i] = back[i, path[i + 1]]
    return path


CANDIDATES = 3
# A bass move cuts a chord run once it holds this many beats. A chord change already cuts, so this
# governs moves under a held chord only: there a one-beat move is a passing or walking tone, and
# cutting on it would fragment the timeline without changing the harmony; two beats is a new bass.
BASS_HOLD = 2


def segment(states: np.ndarray, scores: np.ndarray, cqt: np.ndarray) -> list[dict]:
    """Cut the beats into segments, each with ranked candidate labels and a bass.

    A segment ends where the smoothed state changes and, inside a chord run, where the per-beat
    pick_bass value changes to one held for BASS_HOLD beats, so consecutive segments may share a
    chord. cqt is the (84, n) beat-synchronous matrix from beat_features. A segment's bass is its
    held value; with none, the most frequent per-beat value, silence included (ties to a note, then
    the earliest). N has None.
    """
    basses = [pick_bass(column) for column in cqt.T]
    runs = [0, *map(int, np.flatnonzero(np.diff(states)) + 1), len(states)]
    held = {}  # segment start -> the bass held inside that segment
    for run_start, run_end in pairwise(runs):
        if LABELS[states[run_start]] == "N":
            continue
        groups = []  # (first beat, value) of every group of equal values that holds
        beat = run_start
        for value, group in groupby(basses[run_start:run_end]):
            length = len(list(group))
            if length >= BASS_HOLD:
                groups.append((beat, value))
            beat += length
        if groups:
            # Fewer than BASS_HOLD beats before the first held group are a blip it absorbs; more
            # are a stretch of their own, which the vote below labels.
            held[run_start if groups[0][0] - run_start < BASS_HOLD else groups[0][0]] = groups[0][1]
        for (_, previous), (beat, value) in pairwise(groups):
            if value != previous:
                held[beat] = value
    segments = []
    for start, end in pairwise(sorted({*runs, *held})):
        chosen = int(states[start])
        mean = scores[:, start:end].mean(axis=1)
        # Rank by mean score, but the smoothed label leads: it is what the timeline shows.
        ranked = [i for i in np.argsort(-mean, kind="stable") if i != chosen]
        candidates = [LABELS[i] for i in [chosen, *ranked][:CANDIDATES]]
        if start in held:
            # The held value wins over a vote: a move shorter than BASS_HOLD, however loud, is
            # excluded from the choice, so the reported bass is the one the cut rule saw.
            bass = held[start]
        else:
            # A vote over the per-beat values the cut rule uses, not a pick on the mean profile,
            # so a loud one-beat note cannot outvote the beats around it. Silence votes too, so a
            # lone note among rests does not label the span; a tie goes to a note, then earliest.
            votes = Counter(basses[start:end])
            bass = max(votes, key=lambda b: (votes[b], b is not None))
            if LABELS[chosen] == "N":
                bass = None
        segments.append(
            {
                "start_beat": int(start),
                "end_beat": int(end),
                "chord": LABELS[chosen],
                "candidates": candidates,
                "bass": bass,
            }
        )
    return segments


def _pitch_classes(label: str) -> frozenset[int]:
    root, quality = label.split(":")
    return frozenset((ROOTS.index(root) + i) % 12 for i in QUALITIES[quality])


def _leading_twin(label: str, following: str) -> str | None:
    """The dim7 or hdim7 on label's pitch set rooted a semitone below following's root, if any."""
    leading = ROOTS[(ROOTS.index(following.split(":")[0]) - 1) % 12]
    # Only a dim7 (the other three roots) or a min6 (the hdim7 a minor third below) has one.
    for twin in (f"{leading}:dim7", f"{leading}:hdim7"):
        if twin != label and _pitch_classes(twin) == _pitch_classes(label):
            return twin
    return None


def resolve_twins(segments: list[dict]) -> list[dict]:
    """Respell a diminished chord run as the twin that leads into the next chord.

    Pitch-set twins score exactly alike without a bass on one of their roots, so LABELS order picks
    one (a min6 over its hdim7, a dim7's lowest root), which says nothing about the music. A
    diminished chord is spelled by where it leads, so a run becomes its twin a semitone below the
    next chord's root, when it has one: a bass-less C:dim7 before G:maj is F#:dim7, an A:min6
    before G:maj is F#:hdim7.

    The bass counts for a min6 and not for a dim7. A dim7 is symmetric: every tone is a twin's
    root, so the bass profile roots it on whatever tone is lowest, and that is its inversion, not
    its root (C#°7 over E decodes as E:dim7 and becomes C#:dim7 in first inversion before D:min).
    For the same reason a dim7 run followed by a dim7 on its set is that chord over a moved bass,
    and takes the following run's label. A min6 and its hdim7 are different chords on one set,
    and a bass on the min6's root is the evidence for the m6 reading, so that run is left. A run
    with no leading twin keeps the recognizer's reading, as does a run before N or at the end. A
    run split by the bass is one chord and one decision. The candidates lead with the new label,
    then the recognizer's.
    """
    runs = [list(run) for _, run in groupby(segments, key=lambda s: s["chord"])]
    resolved = []
    following = None  # the next run's label as written
    # From the last run back, so a run leads into the next chord as it will be written: in a
    # chromatic chain C#°7 D°7 D#°7 Em decoded as C#:dim7 D:dim7 C:dim7 E:min, D:dim7 is followed
    # by D#:dim7 and stays, where the decoded C:dim7 would make it B:dim7.
    for run in reversed(runs):
        label = run[0]["chord"]
        root, _, quality = label.partition(":")
        bass_decided = quality != "dim7" and any(s["bass"] == root for s in run)
        if label != "N" and following not in (None, "N") and not bass_decided:
            if quality == "dim7" and _pitch_classes(following) == _pitch_classes(label):
                twin = following
            else:
                twin = _leading_twin(label, following)
            if twin is not None and twin != label:
                run = [
                    {
                        **s,
                        "chord": twin,
                        "candidates": [
                            twin,
                            label,
                            *(c for c in s["candidates"] if c not in (twin, label)),
                        ][:CANDIDATES],
                    }
                    for s in run
                ]
        resolved.append(run)
        following = run[0]["chord"]
    return [s for run in reversed(resolved) for s in run]


# The bass register: C1-B3, the three lowest octaves of the CQT that beat_features returns.
BASS_BINS = 36
# Leakage into a neighbouring bin is 0.5-0.6 of a peak but is never a local maximum, so a bin
# needs to be both a local maximum and at least this fraction of the register's strongest.
BASS_SALIENCE = 0.5
# Position names index a quality's QUALITIES intervals in order: third is the seventh of a 7, maj7,
# min7, hdim7 or dim7 and the added sixth of a min6; sus4 has no third, and its first is the
# fourth.
INVERSIONS = ("root", "first", "second", "third")


def pick_bass(profile: np.ndarray) -> str | None:
    """Name the lowest salient note in a beat's CQT profile, or None if the register is silent.

    The profile has one bin per semitone with bin 0 = C1, as beat_features returns it. Only the
    first BASS_BINS bins are candidates; the bins above are context for the local-maximum test.
    """
    reference = profile[:BASS_BINS].max()
    if reference == 0:
        return None
    padded = np.pad(profile, 1)
    is_peak = (profile >= padded[:-2]) & (profile >= padded[2:])
    for b in range(BASS_BINS):
        if is_peak[b] and profile[b] >= BASS_SALIENCE * reference:
            return ROOTS[b % 12]
    return None


def inversion(label: str, bass: str | None) -> str | None:
    """Position of the bass note within a chord label: root/first/second/third or non_chord."""
    if label == "N" or bass is None:
        return None
    root, quality = label.split(":")
    offset = (ROOTS.index(bass) - ROOTS.index(root)) % 12
    intervals = QUALITIES[quality]
    return INVERSIONS[intervals.index(offset)] if offset in intervals else "non_chord"
