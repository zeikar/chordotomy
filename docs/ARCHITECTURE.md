# Architecture

Three slices are implemented: chords on the beat, then key estimation and Roman-numeral analysis, then the bass note and inversions. This records the design decided before the first line of code (2026-09-29) and the reasons behind it.

## Pipeline

```text
audio ─→ beat tracking
           │
           ├─→ harmonic signal ─→ one tuning estimate ─┬─→ CQT, 36 bins per octave ─→ whitening
           │                                           │      ─→ treble and bass chroma, level, per beat
           │                                           │                    │
           │                                           │                    ↓
           │                                           │   template correlation + gated N + Viterbi
           │                                           │                    │
           │                                           └─→ CQT, 12 bins per octave ─→ bass note,
           │                                                                 segment cuts ─→ segments
           │                                                                                  │
           │                                                                                  ↓
viewer ←── chord-timeline JSON ←────────────────────────────── key estimation + Roman numerals
```

- Chords are called per beat, not per frame, so a passing note doesn't become a chord change.
- There is no ML: a whitened chroma from librosa's CQT and beat tracking, then major / minor / 7th templates. See "Whitened chroma and an energy-gated N" under Design decisions.
- The bass note comes from a low-register CQT of the mix. It settles slash chords and inversions (`F#7/A#`), which the chroma can't: it folds all octaves together and can't tell which note is lowest. See "Bass from DSP, not Demucs" under Design decisions.
- Analysis marks secondary dominants and borrowed chords. The analyzer writes no prose: the explanations come from a Claude Code skill that reads the JSON. See "Explanations from an agent skill" under Design decisions.
- A Python CLI (uv, Typer) writes the JSON. A static HTML viewer (`viewer/`) plays the audio and highlights the current chord; correcting chords in it comes later.

### Stages implemented

Audio is decoded to mono at 22050 Hz. The harmonic part is taken with HPSS, so drums don't leak into the chroma.

Beats come from `librosa.beat.beat_track` with `trim=False`, because the default trim dropped the last real beats of a synthesized clip. The tracker places no beats in leading or trailing silence. So the grid is extended at the median beat period (the tracker's tempo when only one beat is found) in both directions. Without that, the final chord's last beat would swallow a silent tail, and leading silence would have no beats to label `N`. A tail beat is added only if at least half a period remains, to avoid a sliver interval. Beat tracking runs first, so a file with no beats fails before any chroma work.

The chord CQT starts at C1 and spans 252 bins, seven octaves at 36 bins per octave (a third of a semitone), the resolution of Mauch & Dixon. Its tuning is one `estimate_tuning` value on the harmonic signal, shared with the bass CQT below.

Each frame is then whitened along the frequency axis. A bin becomes its excess over the Hamming-weighted running mean of its octave (37 bins, k-18 to k+18), in running standard deviations; a bin at or below the mean is 0. So a chord's own tones cannot dominate their background, and a broadband, loud mix stops looking flat. The window edges repeat the edge value, and digital silence (sigma 0) whitens to 0. No max-normalisation follows, because the correlation below is scale-free.

Two pitch windows fold the whitened bins to twelve pitch classes: each class takes the bin on its pitch and one either side, which absorbs what the tuning estimate leaves. Both windows are raised cosines. The treble window fades in from E2 to C3 (MIDI 40 to 48) and out from C6 to C7 (MIDI 84 to 96). It starts above the bass line and the kick, which would flatten the chroma, and ends below the hi-hat and sibilance octaves. The bass window is flat up to B2 (MIDI 47) and fades out by B3 (MIDI 59). Each beat takes the median of its frames, for both chromas.

The level is the median RMS of the harmonic signal per beat, in dB relative to the 95th-percentile beat. A high percentile rather than the maximum, so one loud hit cannot push a quiet intro under the gate below.

Templates are binary: 12 roots × {maj, min, 7}. A chord's score is the Pearson correlation of the treble chroma with its template, in [-1, 1], plus `BASS_WEIGHT` = 0.45 times the correlation of the bass chroma with the chord's bass profile. The profile is 1.0 on the root and `BASS_TONE` = 0.8 on the chord's other tones. Both sides are centred and unit-normed over the twelve classes, so a flat or silent chroma has no shape and scores 0 against every chord.

`N` is not a template. Its score is the constant `N_SCORE` = 0.3, which a chord has to beat. A beat more than `N_GATE_DB` = 40 dB below the loud beats can only be `N`, because whitening is scale-free and would turn a silent beat's residual ringing into a chord.

Smoothing is a Viterbi decode over these scores. Likelihoods are `exp((score - best) / TEMPERATURE)` with `TEMPERATURE` = 0.03, so a gap of g on one beat is worth g / 0.03 nats against the transition cost. A state stays put with probability p = exp(-period / `CHORD_SECONDS`), with `CHORD_SECONDS` = 2.2, and the rest is spread evenly over the other states. Chord length is in seconds, not beats, so a tracker locked at half or double tempo does not halve or double it. The temperature is low enough that a real change lasting two beats survives, and the self-loop is strong enough that a single beat where a chord flickers to its sibling does not.

Consecutive beats with the same state become one chord run. A run is also cut where the per-beat bass changes to a value that holds for two beats (see the bass paragraphs below). Each resulting segment carries three candidate labels, computed over its own beats: the smoothed chord first, then the labels with the highest mean score over the segment. Scores are not written out, per the confidence rule below. Consecutive segments may therefore share a chord.

The cut rule governs a bass move under a held chord only, because a chord change already cuts. So a one-beat slash chord that comes with a chord change (C → G/B → Am) is its own segment. A one-beat bass move under an unchanged chord is almost always a passing or walking tone, and cutting on it would fragment the timeline without changing the harmony. An alternating bass under a held chord (C–E–C–E, C–G–C–G) is a root-position accompaniment pattern, not a series of inversions: no value holds two beats, so it stays one segment. A segment's bass is the value held inside it. A move shorter than two beats is excluded from that choice, so three C beats and one loud E beat read C. A segment with no held value takes the most frequent per-beat value, silence included, ties to a note and then to the earliest, so `null` when most beats are silent. The first held value cuts at its own start when at least two beats precede it in the run (`C–E–C–E–G–G` is two segments, the first by that vote); with fewer, it absorbs them. A bass-register silence held for two or more beats under one chord (a bass player resting while the chord is voiced above the register) also cuts: the middle segment has bass `null`, and the chord on either side keeps its own bass. `N` runs are never cut and have no bass.

The bass note is by definition the lowest sounding note, so it is read from a CQT that keeps octaves apart. Folding it into a chroma would lose that: a chord played alone ties its tones on an argmax, and any low chord tone louder than the bass would win. The CQT is taken from the same harmonic signal as the chroma. It starts at C1 (32.7 Hz) and spans 84 bins, seven octaves at 12 bins per octave, the same span as the chord CQT. Bin k is k semitones above C1. The lowest 36 bins (C1–B3, 32.7–246.9 Hz) are the bass register. The bins above it are context for the peak test and give the silence floor the file's level.

Twelve bins per octave rather than the chroma's 36, because the CQT window at C1 is then 0.53 s instead of 1.59 s, so beats stay separable. The cost is that a note leaks into its neighbouring semitone bins at 0.50 to 0.60 of its peak. The pick rule below is built around that. The magnitude is reduced to the median over each beat, on the same grid as the chroma.

For tuning, both CQTs take the same `estimate_tuning` value, measured at 36 bins per octave on the harmonic signal. The bass CQT divides it by three for its 12-bin grid. So the bass bins line up with the chord chroma's, and on a recording detuned by half a semitone the chroma's root and the bass note fall on the same side.

A beat column is zeroed when its register maximum is below 1 % (`SILENCE_FLOOR`) of the loudest bin of the whole matrix, the file's loudest note anywhere. A file with nothing in the register never sets its own reference this way: what survives there is leakage under real notes above, which the peak test rejects. The column is zeroed rather than lifted by an additive floor, because a flat column would make C1 the lowest peak.

On each column the bass is the lowest local maximum inside the register that is at least half the register's maximum. Its pitch class is the bin mod 12. Local maxima are tested over the whole 84-bin profile, so a note just above the register (C4 leaks into B3 at half its height) is a slope, not a peak. Leakage is never a local maximum, and a bass note's harmonics all lie above it. Taking the lowest peak rather than the loudest is the definition of a bass; the price is that a fundamental weaker than half the loudest register bin is not picked. A zero column, or one with no qualifying peak, has no bass.

The bass also feeds the chord choice, through the bass chroma and its weight in the score. The treble chroma starts at E2, so the bass line no longer flattens it. The bass chroma is not a root vote: a chord's bass profile is 1.0 on its root and 0.8 on its other tones. A bass pedal now argues for every chord that contains it, most for the chord rooted on it. A loud pedal outside the chord still pulls the label toward chords that contain it. A bass on the third or fifth still supports its chord, so the treble decides between a first inversion and the chord rooted on the bass (`A:min/C` against `C:maj`, `G:maj/B` against `B:min`). A root bass breaks the ties the treble cannot, like `C:maj` with an added sixth against `A:min` with a seventh. The bass note that goes into the segments is still the CQT pick above, not this chroma.

### Harmonic analysis

The analysis is a pure function of the chord runs and an optional key. A chord run is consecutive segments with the same chord, with their beats summed, so a bass change under a chord changes neither the key weights nor the look-ahead below. It takes no audio (see "Key from chords, not audio" under Design decisions). It lives in `harmony.py`.

A chord is diatonic when every chord tone (root, third, fifth, and the seventh of a `7` chord) lies in the key's scale: major, or natural minor. Minor admits one more case, `maj` and `7` on the dominant degree, the harmonic-minor V and V7. The raised leading tone is admitted nowhere else, so `F:min` in A minor is chromatic, not diatonic. The resulting sets are major: `I ii iii IV V V7 vi`; minor: `i III iv v V V7 VI VII VII7`. `VII7` is there because `G:7` in A minor is G–B–D–F, all natural minor. `C:7` in C major is not diatonic, since Bb is outside the scale.

The key is one global key per file. Each of the 24 keys scores the sum over chords of beats times a weight. A non-diatonic chord weighs 0. A diatonic chord weighs 3 on the tonic, 2 on the subdominant or dominant degree, and 1 on any other degree. Beats are used rather than seconds because they are the musical duration and the segments carry them. Relative keys share six triads, so the choice between them comes down to where the time goes: `Am–F–C–G` with equal beats is C major, and the same loop with `Am` twice as long is A minor. Ties break on beats spent on the key's own tonic triad, then on whether the first chord is that triad, then on the fixed key order. A timeline of only `N` has no key. The top 3 keys are written out.

`--key` replaces the estimated key. The estimator still runs, so `key.candidates` keeps showing what the chords suggest, and you can see how far an override is from it.

A numeral is the root's offset from the tonic, spelled with accidentals relative to the key's own scale (major scale, or natural minor). `maj` and `7` chords are uppercase, `min` chords lowercase, and `7` chords append `7`. Accidentals describe the root only, so `E:7` in A minor is `V7`, never with a raised leading tone. Diminished triads are not in the chord vocabulary, so `vii°` in major and `ii°` in minor are never detected and never appear.

Each chord gets one role. The first match wins:

1. `diatonic`, by the test above in the key's own mode.
2. `secondary_dominant`, for a `maj` or `7` chord whose root a perfect fifth below is a tonicizable diatonic triad. Major targets are `ii iii IV V vi`; minor targets are `III iv V VI VII`. Never the tonic, never a diminished degree. The numeral is `V/<target>` or `V7/<target>`, and `target` names the tonicized numeral. The rule is the pitch relationship, so a `V7/V` that resolves elsewhere is still labeled.
3. `borrowed`, when the chord is diatonic in the parallel mode (same tonic, other mode). The seventh counts, so `A#:7` (Bb7) is a borrowed `bVII7` in C major, while `D#:7` and `G#:7` (Eb7, Ab7) are not borrowed, because Db and Gb are outside C minor.
4. `chromatic`, everything else, with the plain numeral.

Two chords satisfy both rule 2 and rule 3, both in minor keys: the major triads on the tonic and the subdominant. `A:maj` in A minor is either `V/iv` or a borrowed `I`, and `D:maj` is either `V/VII` or a borrowed `IV`. Here the label looks one chord ahead. The chord is a secondary dominant only when the immediately following chord is diatonic in the key and has the target's root: `D:min` after `A:maj` (`D:7` and `D:maj` are not diatonic in A minor), `G:maj` or `G:7` after `D:maj`. Any other chord, a non-diatonic chord on that root, an `N`, or the end of the track makes it borrowed. Silence is not a resolution, however long. Every other label depends on the chord and key alone.

The function is set for diatonic chords only: `I`, `III`, `VI` are `tonic`; `II`, `IV` are `predominant`; `V`, `VII` are `dominant`. `iii` and `vi` are tonic substitutes, and `VII` in minor is the subtonic dominant. Other roles have no function.

## The chord-timeline JSON

This is the project's public seam. It carries beat positions, not just seconds, so another tool, or a notation stage someone else builds, can consume it. `chordotomy analyze` writes it as schema version 3.

| field | type | meaning |
| --- | --- | --- |
| `schema_version` | int, `3` | schema version of this file |
| `generator.name` | `"chordotomy"` | |
| `generator.version` | str | the chordotomy version that wrote the file |
| `source.path` | str | the audio path as given on the command line |
| `source.duration` | float, seconds, 3 decimals | |
| `beats` | list of float seconds, 3 decimals, ascending | beat index = list position |
| `key` | object or `null` | the key the numerals are relative to; `null` only when the timeline has no chord and no `--key` was given |
| `key.label` | str | `<root>:maj` or `<root>:min`, sharps only, e.g. `C:maj`, `A:min` |
| `key.source` | `"estimated"` or `"given"` | `given` when `--key` was passed |
| `key.candidates` | list of up to 3 str | the estimator's ranking, best first, no scores; `candidates[0] == label` when `source` is `estimated`; `[]` when the timeline has no chord |
| `segments[].start_beat` | int | inclusive |
| `segments[].end_beat` | int | exclusive; may equal `len(beats)`, meaning the segment runs to the end of the audio |
| `segments[].start_time` | float | `beats[start_beat]` |
| `segments[].end_time` | float | `beats[end_beat]`, or `source.duration` when `end_beat == len(beats)` |
| `segments[].chord` | str | Harte label or `N`; always the root-position label; consecutive segments may repeat it when the bass changes under one chord |
| `segments[].candidates` | list of 3 str | best first, `candidates[0] == chord`, no scores |
| `segments[].bass` | str or `null` | the segment's held bass, sharps only (`C` to `B`): the per-beat bass (the lowest note sounding in the bass register) that holds for at least 2 beats under the chord; when no value holds that long (a one-beat chord, a bass moving every beat), the most frequent per-beat value, silence included, ties to a note and then to the earliest; a bass move shorter than 2 beats under an unchanged chord (a passing tone, an alternating C–E or C–G accompaniment) is not reported; `null` for `N` and when no beat has a note in the bass register |
| `segments[].inversion` | `"root"`, `"first"`, `"second"`, `"third"`, `"non_chord"`, or `null` | `chord` over `bass`: `root` when the bass is the root, `first` / `second` when it is the third / fifth, `third` when it is the seventh of a `7` chord, `non_chord` when it is not a chord tone; `null` whenever `bass` is `null` |
| `segments[].numeral` | str or `null` | Roman numeral of the root-position chord relative to `key` (grammar above); `null` for `N` |
| `segments[].role` | `"diatonic"`, `"secondary_dominant"`, `"borrowed"`, `"chromatic"`, or `null` | how the chord relates to the key; `null` for `N` |
| `segments[].function` | `"tonic"`, `"predominant"`, `"dominant"`, or `null` | harmonic function; set only for `diatonic` chords |
| `segments[].target` | str or `null` | for `secondary_dominant`, the numeral of the chord it tonicizes (`V7/V` → `V`); `null` otherwise |

A chord label is `<root>:<quality>` in Harte syntax. The root is one of `C C# D D# E F F# G G# A A# B`, spelled with sharps only, and the quality is `maj`, `min`, or `7`. `N` means no chord. A key label is the label of its tonic triad, `<root>:maj` or `<root>:min`, sharps only. `bass` is spelled the same way, as a bare root.

`chord` and `numeral` stay root-position labels. A slash chord is `chord` over `bass`: `C:maj` with bass `E` is C/E. Figured-bass numerals (`I6`, `V65`) are not written, since they follow from `numeral` and `inversion` by a fixed table. A bass move shorter than 2 beats under an unchanged chord is neither reported nor cut on, because it would turn a held chord into a flicker of inversions without changing the harmony. Consecutive segments may repeat a `chord` when the bass changes under it; in v1 and v2 they never did.

Segments are contiguous: each `start_beat` equals the previous `end_beat`, and the first starts at beat 0. Leading and trailing silence is labeled `N`. The only unlabeled span is the sub-beat head between the start of the audio and `beats[0]`, which is shorter than one beat.

The schema is stable. Any change to the documented schema, an added field included, is breaking and bumps `schema_version`.

```json
{
  "schema_version": 3,
  "generator": {"name": "chordotomy", "version": "0.0.0"},
  "source": {"path": "song.mp3", "duration": 4.0},
  "key": {"label": "C:maj", "source": "estimated", "candidates": ["C:maj", "G:maj", "F:maj"]},
  "beats": [0.116, 0.604, 1.092, 1.58, 2.068, 2.556, 3.044, 3.532],
  "segments": [
    {
      "start_beat": 0, "end_beat": 2, "start_time": 0.116, "end_time": 1.092,
      "chord": "C:maj", "candidates": ["C:maj", "C:7", "A:min"],
      "bass": "C", "inversion": "root",
      "numeral": "I", "role": "diatonic", "function": "tonic", "target": null
    },
    {
      "start_beat": 2, "end_beat": 4, "start_time": 1.092, "end_time": 2.068,
      "chord": "C:maj", "candidates": ["C:maj", "E:min", "A:min"],
      "bass": "E", "inversion": "first",
      "numeral": "I", "role": "diatonic", "function": "tonic", "target": null
    },
    {
      "start_beat": 4, "end_beat": 6, "start_time": 2.068, "end_time": 3.044,
      "chord": "D:7", "candidates": ["D:7", "D:maj", "B:min"],
      "bass": "F#", "inversion": "first",
      "numeral": "V7/V", "role": "secondary_dominant", "function": null, "target": "V"
    },
    {
      "start_beat": 6, "end_beat": 8, "start_time": 3.044, "end_time": 4.0,
      "chord": "G:7", "candidates": ["G:7", "G:maj", "B:min"],
      "bass": "B", "inversion": "first",
      "numeral": "V7", "role": "diatonic", "function": "dominant", "target": null
    }
  ]
}
```

## Evaluation

`chordotomy evaluate {tiny-aam,guitarset} [--limit N]` scores the analyzer on real audio. It is opt-in and for development (the `eval` extra). Nothing in it reaches the timeline JSON. Both datasets are CC BY 4.0 on Zenodo. They are downloaded on demand into the checkout's gitignored `datasets/`, never committed.

- **Tiny AAM**: 20 mixed tracks with one chord per beat, reduced to major, minor and `N`. Its annotation has no bass, so its `majmin_inv` assumes every reference chord is in root position; read it as bass agreement with that assumption, not as inversion accuracy.
- **GuitarSet**: the 180 accompaniment takes (`_comp`, mono mic), scored against the performed chord annotation, which carries the bass.

Scoring is `mir_eval`, and the table is per track with an `overall` row weighted by duration. Three things matter when reading it:

- `majmin` reduces sevenths and sixths to the triad. It leaves out power chords, sus and diminished chords, so those intervals are not counted at all.
- `N` against `N` counts as correct. A track the analyzer calls all `N` is scored right wherever the reference is also `N`, so `N_est` and `N_ref`, the shares of duration labeled `N`, are printed beside the scores.
- `sevenths` needs the seventh to match, and `majmin_inv` compares the bass as a scale degree above the root, so a right chord over the wrong bass, or over no detected bass (`bass` null), fails it.

Baseline, front end at `b70fb50`:

| | root | majmin | sevenths | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.773 | 0.738 | 0.725 | 0.653 | 0.123 | 0.015 |
| GuitarSet (180 takes) | 0.485 | 0.519 | 0.460 | 0.335 | 0.450 | 0.000 |

On Tiny AAM the analyzer calls 12% of the duration `N` against 1.5% in the reference, and most of that is two tracks: 2720 (77% `N`) and 2990 (56%).

Whitened front end, at the commit that adds these rows. The decode constants were tuned on Tiny AAM; GuitarSet was held out. `BASS_WEIGHT`, `BASS_TONE`, `TEMPERATURE` and `CHORD_SECONDS` are the best Tiny AAM majmin among the values that keep the default test suite green. The suite is a hard constraint: two-beat chord changes and first-inversion chords must survive. Without it the best Tiny AAM majmin was about 0.823. The 0.788 below is the price of that constraint, chosen deliberately. Vocabulary expansion (v4) is the next stage.

| | root | majmin | sevenths | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.848 | 0.788 | 0.760 | 0.691 | 0.011 | 0.015 |
| GuitarSet (180 takes) | 0.688 | 0.619 | 0.492 | 0.373 | 0.007 | 0.000 |

## Design decisions

### An analyzer, not a transcriber

Chord timelines (Chordify, Moises) and audio → score (Klangio) are already commercial products. Automatic harmonic analysis with an explanation, the "why does this progression work" part, is the gap. So chordotomy stops at chords and their function. Staff notation, melody → MIDI, and section detection are out. The first two need note-level rhythm, meaning quantization and triplets, which is the hardest and least distinctive part of the problem. Section detection is a research problem of its own. Model training is out as well: DSP and pretrained models only.

Chord extraction will sometimes be wrong, and the analysis is only as good as the chords. That's why correcting chords and entering a progression by hand are core features rather than extras.

### Key from chords, not audio

The key is estimated from the chord segments, not from the recording. Corrected or hand-entered chords then get the same analysis as extracted ones, and the estimator can be tested with plain progressions instead of synthesized audio.

### Local-first

People will feed it commercial recordings. A hosted upload service would mean storing copyrighted audio, so audio never leaves the machine.

### Bass from DSP, not Demucs

The bass note comes from a low-register CQT (see Stages implemented), not from a Demucs bass stem. Demucs's code is MIT, but its pretrained weights on Hugging Face (`adefossez/HTDemucs`) carry no license statement. They were trained on MUSDB18-HQ, which is licensed for non-commercial research, plus private songs, so the terms of the output could not be stated. DSP also avoids a multi-gigabyte torch dependency.

The tradeoff is lower accuracy than a separated stem when other low instruments or kick drums share the register. HPSS removes most of the kick.

### Explanations from an agent skill

The analyzer never calls an LLM. The repo is a Claude Code plugin whose `explain-harmony` skill (`skills/explain-harmony/`) runs `chordotomy analyze`, reads the JSON, and writes the explanations. The app then needs no API key, SDK dependency, or network code, and it stays deterministic and testable. The agent can also take follow-up questions. The audio stays local; only the chord timeline, as text, reaches the model. The tradeoffs: explanations are not stored in the JSON, so a viewer can't show them without a separate write-back, and getting them needs an agent.

### Whitened chroma and an energy-gated N

The first front end summed the CQT into a chroma, added a floor, and scored it by cosine against binary templates plus a flat template for `N`. On real mixes it called 12 % of Tiny AAM `N`, and 77 % of track 2720. On that track the `N` similarity had a median of 0.774 against 0.731 for the best chord.

The flat template wins because a real mix's chroma is never sparse. The flat template beats a triad whenever the chord-tone bins are under 3.0 times the others (for a `7` chord, 2.73 times), and harmonics, drums and melody keep a mix under that. Mauch & Dixon measured the same thing: without preprocessing, many chords in noisier songs become "no chord". In their Table 1, without NNLS, chord recognition is 38.6 % with no preprocessing, 74.5 % with background subtraction and 79.0 % with standardisation. So the chroma is whitened against its octave background before it is scored. This is implemented from the paper, never from their GPL plugin (see "Licenses").

`N` is a gate and a constant, not a template, because no template shape is right for it. Silence is an energy fact, so `N_GATE_DB` reads it from the level. A quiet-but-tonal beat is a chord, so `N_SCORE` is a bar the correlation has to clear, and a flat chroma correlates 0 against every chord. The gate cannot be read from the chroma, because whitening is scale-free.

The evidence is the Tiny AAM rows in Evaluation: `N` falls from 12.3 % to 1.1 % of the duration (the reference has 1.5 %), and majmin rises from 0.738 to 0.788. GuitarSet, held out, goes from 0.519 to 0.619.

The bass evidence is a chord-tone profile because a root-only term pulled first inversions toward the chord rooted on the bass (`A:min/C` read as `C:maj`, `G:maj/B` as `B:min`), and slash chords are a product feature.

The self-loop is in seconds because a tracker locked at half or double tempo would otherwise double or halve the expected chord length.

The constants trade Tiny AAM score for the test suite; see the note under the Evaluation tables. Not done: NNLS note profiles bought about 1 pp of majmin in the paper, and the vocabulary (sevenths beyond `7`, sus, diminished) is the next stage, v4.

### Confidence is a rank, not a percentage

Template similarity is not a probability. Showing "GM7 81%" would claim precision the method doesn't have. Candidates are shown as a ranked list. Percentages appear only if a calibrated model produces them.

### Licenses

The project is MIT, so it takes no GPL or AGPL dependencies. That rules out Essentia (AGPL-3.0) and Chordino / NNLS Chroma (GPL); their ideas get reimplemented on librosa instead. librosa (ISC) and music21 (BSD-3) are fine. Demucs's code is MIT, but its pretrained weights are a separate question; see "Bass from DSP, not Demucs". Pretrained weights can carry terms separate from their code, such as non-commercial model files, so check both.

### Synthesized test fixtures

Tests build audio in code, for example additive tones for known chords at a known tempo. The fixtures are license-free, and the ground truth is exact.
