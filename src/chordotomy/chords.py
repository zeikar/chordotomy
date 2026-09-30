"""Chord vocabulary, template scoring and decoding.

The scoring and the no-chord handling follow the ideas of Mauch & Dixon, "Approximate Note
Transcription for the Improved Identification of Difficult Chords" (ISMIR 2010), implemented from
the paper, not from their GPL-licensed plugin.
"""

from __future__ import annotations

from collections import Counter
from itertools import groupby, pairwise

import librosa
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
# Quality-major, and the order is the tie-break: librosa.sequence.viterbi takes the first argmax.
# Pitch-set twins score exactly alike without bass evidence (G:min6 and E:hdim7; the four dim7
# labels on one set), and then the earlier label wins: min6 over hdim7, the lowest root of a dim7.
LABELS = [f"{root}:{quality}" for quality in QUALITIES for root in ROOTS] + ["N"]
# A tone's first four partials in semitones above it: the fundamental, the octave, the twelfth
# and the double octave. Partial k weighs PARTIAL_DECAY ** (k - 1) in a template.
PARTIALS = (0, 12, 19, 24)
# A triad's own partials land on tetrad tones: the third's twelfth on the seventh (E -> B under
# C, C -> G under A:min), the fifth's on the ninth, and whitening lifts a lone partial in a
# sparse region. A template that expects those partials stops reading them as a tetrad. 0 gives
# binary templates; a sweep rebuilds the table for each decay it tries.
PARTIAL_DECAY = 0.6


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
# BASS_WEIGHT, BASS_TONE and CHORD_SECONDS are stage 1's tuned values: the best Tiny AAM majmin
# among those that kept the synthesized suite green, with its two-beat A:min/C inside a run of
# C:maj as the binding case. TEMPERATURE and QUALITY_OFFSET are v4 starting values, not yet tuned.
# The weight of the bass chroma's evidence for a chord, against the treble's correlation.
BASS_WEIGHT = 0.45
# A chord's bass profile is 1 on its root and BASS_TONE on its other tones. A bass on the third
# or fifth still supports the chord, so the treble decides Am/C against C and G/B against Bm;
# the root counts more, so a root bass settles the ties the treble cannot (G:min6 against
# E:hdim7).
BASS_TONE = 0.8
# Sharpens score gaps into likelihood ratios: a gap g on one beat is worth g / TEMPERATURE nats
# against the transition cost. Too high and two-beat chord changes are smoothed away. The
# self-loop spreads what it leaves over the other 108 labels, so at period 0.5 leaving a chord and
# coming back costs about 12.1 nats (9.9 with stage 1's 37 labels). The suite's binding case, the
# two-beat A:min/C inside C:maj at 0.22 per beat, holds up to 0.035.
TEMPERATURE = 0.02
# The expected chord length in seconds, not beats, so a tracker locked at half or double tempo
# does not halve or double it (research pitfall 3).
CHORD_SECONDS = 2.2
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
    # the minor seventh). Each has to stay under what a played seventh gains over its triad.
    "7": -0.05,
    "maj7": -0.15,
    "min7": -0.15,
    # One value for both twins (G:min6 is E:hdim7's pitch set), so the bass, not the offset, tells
    # them apart.
    "min6": -0.05,
    "hdim7": -0.05,
    # A 7 chord with a weak root leaves three of a dim7's four tones (E G Bb of C:7 in C#:dim7).
    "dim7": -0.2,
    # The largest: Tiny AAM, annotated in maj and min only, scores every sus4 call as a miss, and a
    # played sus4 clears its maj by more than a played seventh clears its triad.
    "sus4": -0.3,
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


def smooth(scores: np.ndarray, level: np.ndarray, period: float) -> np.ndarray:
    """Viterbi-decode (109, n) scores into one label index per beat.

    level is each beat's loudness in dB relative to the track's loud beats; a beat below
    -N_GATE_DB can only be N. period is the beat period in seconds.
    """
    # Shifting a column by its maximum leaves the path unchanged and keeps every value in (0, 1],
    # which librosa.sequence.viterbi requires.
    likelihood = np.exp((scores - scores.max(axis=0, keepdims=True)) / TEMPERATURE)
    likelihood[:-1, level < -N_GATE_DB] = 0.0  # every chord row; N is the last
    # The chance that chord changes, arriving every CHORD_SECONDS on average, fire none within
    # one beat. Unlike 1 - period / CHORD_SECONDS it stays in (0, 1) when a beat is longer than a
    # chord, as on a half-tempo grid.
    transition = librosa.sequence.transition_loop(len(LABELS), np.exp(-period / CHORD_SECONDS))
    return librosa.sequence.viterbi(likelihood, transition)


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
