# Architecture

Implemented so far: chords on the beat, key estimation and Roman-numeral analysis, the bass note and inversions, explanations through the `explain-harmony` skill, a viewer that plays the recording with its chords, chord editing in that viewer, and an opt-in evaluation on real audio. The chord vocabulary is v4. This records the design decided before the first line of code (2026-09-29) and the reasons behind it.

## Pipeline

```text
audio ─→ beat tracking
           │
           ├─→ harmonic signal ─→ one tuning estimate ─┬─→ CQT, 36 bins per octave ─→ whitening
           │                                           │      ─→ treble and bass chroma, level, per beat
           │                                           │                    │
           │                                           │                    ↓
           │                                           │   template correlation + quality offsets
           │                                           │              + gated N + Viterbi
           │                                           │                    │
           │                                           └─→ CQT, 12 bins per octave ─→ bass note,
           │                                                                 segment cuts ─→ segments
           │                                                                                  │
           │                                                                                  ↓
           │                                                                  respell diminished twins
           │                                                                                  │
           │                                                                                  ↓
viewer ←── chord-timeline JSON ←────────────────────────────── key estimation + Roman numerals
```

- Chords are called per beat, not per frame, so a passing note doesn't become a chord change.
- There is no ML: a whitened chroma from librosa's CQT and beat tracking, then templates for nine chord qualities, from triads to sevenths, a minor sixth and sus4. See "Whitened chroma and an energy-gated N" and "Chord vocabulary v4" under Design decisions.
- The bass note comes from a low-register CQT of the mix. It settles slash chords and inversions (`F#7/A#`), which the chroma can't: it folds all octaves together and can't tell which note is lowest. See "Bass from DSP, not Demucs" under Design decisions.
- Analysis marks secondary dominants, secondary leading-tone chords and borrowed chords. The analyzer writes no prose: the explanations come from a Claude Code skill that reads the JSON. See "Explanations from an agent skill" under Design decisions.
- A Python CLI (uv, Typer) writes the JSON. A static HTML viewer (`viewer/`) plays the audio, highlights the current chord, and corrects chords on the analyzer's beats, re-analyzing them in the browser. See "Editing in the viewer".

### Stages implemented

Audio is decoded to mono at 22050 Hz. The harmonic part is taken with HPSS, so drums don't leak into the chroma.

Beats come from `librosa.beat.beat_track` with `trim=False`, because the default trim dropped the last real beats of a synthesized clip. The tracker places no beats in leading or trailing silence. So the grid is extended at the median beat period (the tracker's tempo when only one beat is found) in both directions. Without that, the final chord's last beat would swallow a silent tail, and leading silence would have no beats to label `N`. A tail beat is added only if at least half a period remains, to avoid a sliver interval. Beat tracking runs first, so a file with no beats fails before any chroma work.

The chord CQT starts at C1 and spans 252 bins, seven octaves at 36 bins per octave (a third of a semitone), the resolution of Mauch & Dixon. Its tuning is one `estimate_tuning` value on the harmonic signal, shared with the bass CQT below.

Each frame is then whitened along the frequency axis. A bin becomes its excess over the Hamming-weighted running mean of its octave (37 bins, k-18 to k+18), in running standard deviations; a bin at or below the mean is 0. So a chord's own tones cannot dominate their background, and a broadband, loud mix stops looking flat. The window edges repeat the edge value, and digital silence (sigma 0) whitens to 0. No max-normalisation follows, because the correlation below is scale-free.

Two pitch windows fold the whitened bins to twelve pitch classes: each class takes the bin on its pitch and one either side, which absorbs what the tuning estimate leaves. Both windows are raised cosines. The treble window fades in from E2 to C3 (MIDI 40 to 48) and out from C6 to C7 (MIDI 84 to 96). It starts above the bass line and the kick, which would flatten the chroma, and ends below the hi-hat and sibilance octaves. The bass window is flat up to B2 (MIDI 47) and fades out by B3 (MIDI 59). Each beat takes the median of its frames, for both chromas.

The level is the median RMS of the harmonic signal per beat, in dB relative to the 95th-percentile beat. A high percentile rather than the maximum, so one loud hit cannot push a quiet intro under the gate below.

There are 108 chord labels, 12 roots × 9 qualities: `maj`, `min`, `7`, `maj7`, `min7`, `min6`, `hdim7`, `dim7` and `sus4` (see "Chord vocabulary v4" under Design decisions). A chord's template is the sum, over its tones, of each tone's first four partials: the fundamental, the octave, the twelfth and the double octave, 0, +12, +19 and +24 semitones folded to pitch classes. Partial k weighs `PARTIAL_DECAY`^(k-1), with `PARTIAL_DECAY` = 0.8. A chord's score is the Pearson correlation of the treble chroma with its template, in [-1, 1], plus `BASS_WEIGHT` = 0.3 times the correlation of the bass chroma with the chord's bass profile, plus its quality's offset. The bass profile is on the chord tones alone, without partials: 1.0 on the root and `BASS_TONE` = 0.7 on the chord's other tones. Both sides of each correlation are centred and unit-normed over the twelve classes, so a flat or silent chroma has no shape and scores 0 against every chord.

The offsets (`QUALITY_OFFSET`) are 0 for `maj`, `min` and `7`, -0.1 for `maj7`, `min7`, `min6`, `hdim7` and `dim7`, and -0.25 for `sus4`. So the other tetrads and `sus4` have to beat the triads by evidence. "Chord vocabulary v4" says why; "Tuning the v4 constants" under Evaluation says how the values were found.

Some labels share a pitch set. `G:min6` and `E:hdim7` are both G–Bb–D–E, and a `dim7`'s four tones are the roots of four `dim7` labels on the same notes. Their templates are the same, so only the bass profile, which favours the root, tells these twins apart. Without bass evidence they tie exactly, and the decoder keeps the label that comes first: qualities in the order above, then roots from C. So `G:min6` wins over `E:hdim7`, and `C:dim7` over `D#:dim7`, `F#:dim7` and `A:dim7`. That choice says nothing about the music; the respelling step at the end of this section revisits it.

`N` is not a template. Its score is the constant `N_SCORE` = 0.3, which a chord has to beat. A beat more than `N_GATE_DB` = 40 dB below the loud beats can only be `N`, because whitening is scale-free and would turn a silent beat's residual ringing into a chord.

Smoothing is a Viterbi decode over these scores. Likelihoods are `exp((score - best) / TEMPERATURE)` with `TEMPERATURE` = 0.03, so a gap of g on one beat is worth g / 0.03 nats against the transition cost. A state stays put with probability p = exp(-period / `CHORD_SECONDS`), with `CHORD_SECONDS` = 2.8, and the rest is spread evenly over the other 108 states. So the cost of a switch grows with the label count: it is ln(108 p / (1 - p)) nats against staying, about 6.3 at a period of 0.5 s, and leaving a chord for one beat and coming back costs about 12.6. With v3's 37 states each switch cost ln 3, about 1.1 nats, less at the same p; that is why the decode constants were retuned with the vocabulary. Chord length is in seconds, not beats, so a tracker locked at half or double tempo does not halve or double it. The temperature is low enough that a real change lasting two beats survives, and the self-loop is strong enough that a single beat where a chord flickers to its sibling does not.

Consecutive beats with the same state become one chord run. A run is also cut where the per-beat bass changes to a value that holds for two beats (see the bass paragraphs below). Each resulting segment carries three candidate labels, computed over its own beats: the smoothed chord first, then the labels with the highest mean score over the segment. Scores are not written out, per the confidence rule below. Consecutive segments may therefore share a chord.

The cut rule governs a bass move under a held chord only, because a chord change already cuts. So a one-beat slash chord that comes with a chord change (C → G/B → Am) is its own segment. A one-beat bass move under an unchanged chord is almost always a passing or walking tone, and cutting on it would fragment the timeline without changing the harmony. An alternating bass under a held chord (C–E–C–E, C–G–C–G) is a root-position accompaniment pattern, not a series of inversions: no value holds two beats, so it stays one segment. A segment's bass is the value held inside it. A move shorter than two beats is excluded from that choice, so three C beats and one loud E beat read C. A segment with no held value takes the most frequent per-beat value, silence included, ties to a note and then to the earliest, so `null` when most beats are silent. The first held value cuts at its own start when at least two beats precede it in the run (`C–E–C–E–G–G` is two segments, the first by that vote); with fewer, it absorbs them. A bass-register silence held for two or more beats under one chord (a bass player resting while the chord is voiced above the register) also cuts: the middle segment has bass `null`, and the chord on either side keeps its own bass. `N` runs are never cut and have no bass.

The bass note is by definition the lowest sounding note, so it is read from a CQT that keeps octaves apart. Folding it into a chroma would lose that: a chord played alone ties its tones on an argmax, and any low chord tone louder than the bass would win. The CQT is taken from the same harmonic signal as the chroma. It starts at C1 (32.7 Hz) and spans 84 bins, seven octaves at 12 bins per octave, the same span as the chord CQT. Bin k is k semitones above C1. The lowest 36 bins (C1–B3, 32.7–246.9 Hz) are the bass register. The bins above it are context for the peak test and give the silence floor the file's level.

Twelve bins per octave rather than the chroma's 36, because the CQT window at C1 is then 0.53 s instead of 1.59 s, so beats stay separable. The cost is that a note leaks into its neighbouring semitone bins at 0.50 to 0.60 of its peak. The pick rule below is built around that. The magnitude is reduced to the median over each beat, on the same grid as the chroma.

For tuning, both CQTs take the same `estimate_tuning` value, measured at 36 bins per octave on the harmonic signal. The bass CQT divides it by three for its 12-bin grid. So the bass bins line up with the chord chroma's, and on a recording detuned by half a semitone the chroma's root and the bass note fall on the same side.

A beat column is zeroed when its register maximum is below 1 % (`SILENCE_FLOOR`) of the loudest bin of the whole matrix, the file's loudest note anywhere. A file with nothing in the register never sets its own reference this way: what survives there is leakage under real notes above, which the peak test rejects. The column is zeroed rather than lifted by an additive floor, because a flat column would make C1 the lowest peak.

On each column the bass is the lowest local maximum inside the register that is at least half the register's maximum. Its pitch class is the bin mod 12. Local maxima are tested over the whole 84-bin profile, so a note just above the register (C4 leaks into B3 at half its height) is a slope, not a peak. Leakage is never a local maximum, and a bass note's harmonics all lie above it. Taking the lowest peak rather than the loudest is the definition of a bass; the price is that a fundamental weaker than half the loudest register bin is not picked. A zero column, or one with no qualifying peak, has no bass.

The bass also feeds the chord choice, through the bass chroma and its weight in the score. The treble chroma starts at E2, so the bass line no longer flattens it. The bass chroma is not a root vote: a chord's bass profile is 1.0 on its root and 0.7 on its other tones. A bass pedal now argues for every chord that contains it, most for the chord rooted on it. A loud pedal outside the chord still pulls the label toward chords that contain it. A bass on the third or fifth still supports its chord, so the treble decides between a first inversion and the chord rooted on the bass (`A:min/C` against `C:maj`, `G:maj/B` against `B:min`). A root bass breaks the ties the treble cannot, like `G:min6` against `E:hdim7`. The bass note that goes into the segments is still the CQT pick above, not this chroma.

The bass chroma is zeroed on beats where that pick finds no note. The correlation is scale-free, so otherwise the leakage under a chord voiced above the register would vote at full strength; it pulled a bass-less `C:maj` toward `C:maj7`.

Last, a diminished chord is respelled by where it leads (`resolve_twins`). This works on chord runs, consecutive segments with the same chord, and the next chord is the following run's. A `dim7` run becomes the twin whose root is a semitone below the next chord's root whenever one exists, whatever its bass. A `dim7` is symmetric, so the bass profile roots it on its lowest tone, and that tone is its inversion, not its root: a `C#:dim7` played over E decodes as `E:dim7`, and before `D:min` it is respelled `C#:dim7` in first inversion. A `dim7` run followed by a `dim7` on the same notes is one chord over a moved bass, and takes the following run's label. A `min6` run becomes its `hdim7` twin when that twin leads into the next chord, so a bass-less `A:min6` before `G:maj` is `F#:hdim7`. It stays `min6` if any of its segments has the bass on the `min6`'s root, the evidence for that reading. An `hdim7` is never respelled. A run with no twin that leads, and a run before `N` or at the end, keeps the recognizer's label. The runs are taken from the last back, so each one leads into the next chord as that chord will be written. A respelled segment's candidates lead with the new label, then the recognizer's, and its `inversion` follows the new label.

### Harmonic analysis

The analysis is a pure function of the chord runs and an optional key. A chord run is consecutive segments with the same chord, with their beats summed, so a bass change under a chord changes neither the key weights nor the look-ahead below. It takes no audio (see "Key from chords, not audio" under Design decisions). It lives in `harmony.py`.

A chord is diatonic when every chord tone lies in the key's scale: major, or natural minor. Minor admits two harmonic-minor cases on top, both with the raised leading tone: `maj` and `7` on the dominant degree (V and V7), and `dim7` on the leading tone (`#vii°7`). The raised leading tone is admitted nowhere else, so `F:min` in A minor is chromatic, not diatonic. The resulting sets are:

- major: `I ii iii IV V vi`; `Imaj7 ii7 iii7 IVmaj7 V7 vi7 viiø7`; `iiadd6`; `Isus4 IIsus4 IIIsus4 Vsus4 VIsus4`
- minor: `i III iv v V VI VII`; `i7 IIImaj7 iv7 v7 V7 VImaj7 VII7 iiø7 #vii°7`; `ivadd6`; `Isus4 IIIsus4 IVsus4 Vsus4 VIIsus4`

`VII7` is there because `G:7` in A minor is G–B–D–F, all natural minor. `C:7` in C major is not diatonic, since Bb is outside the scale.

The key is one global key per file. Each of the 24 keys scores the sum over chords of beats times a weight. A non-diatonic chord weighs 0. A diatonic chord weighs 3 on the tonic, 2 on the subdominant or dominant degree, and 1 on any other degree. The diatonic test takes the full label, seventh included, not its triad. Reduced to triads, `C – Am – D7 – G7` would be G major, where D and G are V and I; with its sevenths it is C major, because the F of `G:7` is outside G major. A seventh detected where there is none can take its chord out of the key, which costs that one chord's vote and no more. Beats are used rather than seconds because they are the musical duration and the segments carry them. Relative keys share six triads, so the choice between them comes down to where the time goes: `Am–F–C–G` with equal beats is C major, and the same loop with `Am` twice as long is A minor. Ties break on beats spent on the key's own tonic chord, then on whether the first chord is that chord, where the tonic chord is the tonic triad or its `maj7` or `min7` (`Am7 – Cmaj7` with equal beats is A minor, as `Am – C` is), then on the fixed key order. A timeline of only `N` has no key. The top 3 keys are written out.

`--key` replaces the estimated key. The estimator still runs, so `key.candidates` keeps showing what the chords suggest, and you can see how far an override is from it.

A numeral is `<accidental><roman><suffix>`, followed by `/<target>` for a secondary chord. The roman is the root's offset from the tonic, spelled with accidentals relative to the key's own scale (major scale, or natural minor). Case shows the third: uppercase for a major third or none, lowercase for a minor one. The suffix comes from the quality:

| quality | case | suffix | in C major |
| --- | --- | --- | --- |
| `maj` | upper | | `F:maj` is `IV` |
| `min` | lower | | `F:min` is `iv` |
| `7` | upper | `7` | `G:7` is `V7` |
| `maj7` | upper | `maj7` | `F:maj7` is `IVmaj7` |
| `min7` | lower | `7` | `D:min7` is `ii7` |
| `min6` | lower | `add6` | `F:min6` is `ivadd6` |
| `hdim7` | lower | `ø7` | `D:hdim7` is `iiø7` |
| `dim7` | lower | `°7` | `B:dim7` is `vii°7` |
| `sus4` | upper | `sus4` | `G:sus4` is `Vsus4` |

`min6` is `add6` because `iv6` would read as the first-inversion figure. `ø` and `°` are the characters U+00F8 and U+00B0, not ASCII stand-ins; the accidentals stay ASCII `b` and `#`. Accidentals describe the root only, so `E:7` in A minor is `V7`, never with a raised leading tone.

The two diminished qualities have one exception. A `dim7` or `hdim7` root on a degree spelled flat is spelled as the raised degree below, because a diminished seventh leads up a semitone. `C#:dim7` in C major is `#i°7`, pointing at `ii`, never `bii°7`; likewise `#ii°7`, `#v°7` and `#vi°7` in major and `#i°7` in minor. Every other chord keeps the plain spelling, so `C#:maj` in C major is `bII`. The viewer spells the chord name the same way, C♯dim7 rather than D♭dim7, except where that would need a double sharp, where it takes the enharmonic letter (`G:dim7` in F# major is Gdim7 under `#i°7`).

The vocabulary has no diminished triad, so `vii°` in major and `ii°` in minor never appear. Their seventh chords do: `viiø7` in major, `iiø7` and `#vii°7` in minor.

Each chord gets one role. The first match wins:

1. `diatonic`, by the test above in the key's own mode.
2. `secondary_dominant`, for a `maj` or `7` chord whose root a perfect fifth below is a tonicizable diatonic triad. Major targets are `ii iii IV V vi`; minor targets are `III iv V VI VII`. Never the tonic, never a diminished degree. The numeral is `V/<target>` or `V7/<target>`, and `target` names the tonicized numeral. The rule is the pitch relationship, so a `V7/V` that resolves elsewhere is still labeled. Only `maj` and `7` count: a `maj7` has no tritone, and a `sus4` no leading tone.
3. `secondary_dominant` as well, for a secondary leading-tone chord: a `dim7` or `hdim7` whose root is a semitone below one of the same targets, when the next chord is diatonic in the key and has the target's root. The numeral is `vii°7/<target>` or `viiø7/<target>`, and `target` is set: in C major, `C#:dim7` before `D:min7` is `vii°7/ii`, and `F#:hdim7` before `G:maj` is `viiø7/V`. A dominant is known by its fifth relation alone, a leading-tone chord only by where it goes, so this rule always looks ahead: `F#:hdim7` before `F:maj` is a chromatic `#ivø7`.
4. `borrowed`, when the chord is diatonic in the parallel mode (same tonic, other mode). The seventh counts, so `A#:7` (Bb7) is a borrowed `bVII7` in C major, while `D#:7` and `G#:7` (Eb7, Ab7) are not borrowed, because Db and Gb are outside C minor. An added sixth counts the same way, and so does the parallel minor's `#vii°7`: `F:min6` (F–Ab–C–D) is a borrowed `ivadd6` in C major, and `B:dim7` a borrowed `vii°7`.
5. `chromatic`, everything else, with the plain numeral.

Two chords satisfy both rule 2 and rule 4, both in minor keys: the major triads on the tonic and the subdominant. `A:maj` in A minor is either `V/iv` or a borrowed `I`, and `D:maj` is either `V/VII` or a borrowed `IV`. Here the label looks one chord ahead. The chord is a secondary dominant only when the immediately following chord is diatonic in the key and has the target's root: `D:min` after `A:maj` (`D:7` and `D:maj` are not diatonic in A minor), `G:maj` or `G:7` after `D:maj`. Any other chord, a non-diatonic chord on that root, an `N`, or the end of the track makes it borrowed. Silence is not a resolution, however long. A leading-tone chord (rule 3) takes the same test, always. Every other label depends on the chord and key alone.

The function is set for diatonic chords only, by the degree, whatever the quality: `I`, `III`, `VI` are `tonic`; `II`, `IV` are `predominant`; `V`, `VII` are `dominant`. So `viiø7` and `#vii°7` are dominant, and `Vsus4` and `iiadd6` take their degree's function. `iii` and `vi` are tonic substitutes, and `VII` in minor is the subtonic dominant. Other roles have no function.

The viewer re-analyzes edited chords with a JavaScript port of this analysis, `viewer/harmony.js`, pinned to the Python by golden vectors that `uv run python tests/harmony_vectors.py` writes to `tests/harmony_vectors.json`: pytest fails when the file no longer matches the Python, and `node --test viewer/tests/` replays every case through the port (see "Re-analysis in the browser, Python as the reference" under Design decisions).

## The chord-timeline JSON

This is the project's public seam. It carries beat positions, not just seconds, so another tool, or a notation stage someone else builds, can consume it. `chordotomy analyze` writes it as schema version 6.

| field | type | meaning |
| --- | --- | --- |
| `schema_version` | int, `6` | schema version of this file |
| `generator.name` | `"chordotomy"` | |
| `generator.version` | str | the chordotomy version that wrote the file |
| `generator.engine.name` | `"dsp"` or `"lv-chordia"` | the recognizer that produced `chord` and `candidates`: chordotomy's DSP front end, or the lv-chordia model |
| `generator.engine.version` | str | chordotomy's version for `dsp`, the lv-chordia package version otherwise |
| `source.path` | str | the audio path as given on the command line |
| `source.duration` | float, seconds, 3 decimals | |
| `beats` | list of float seconds, 3 decimals, ascending | beat index = list position |
| `key` | object or `null` | the key the numerals are relative to; `null` only when the timeline has no chord and no `--key` was given |
| `key.label` | str | `<root>:maj` or `<root>:min`, sharps only, e.g. `C:maj`, `A:min` |
| `key.source` | `"estimated"` or `"given"` | `given` when `--key` was passed or the user chose the key in the viewer |
| `key.candidates` | list of up to 3 str | the estimator's ranking, best first, no scores; `candidates[0] == label` when `source` is `estimated`; `[]` when the timeline has no chord |
| `segments[].start_beat` | int | inclusive |
| `segments[].end_beat` | int | exclusive; may equal `len(beats)`, meaning the segment runs to the end of the audio |
| `segments[].start_time` | float | `beats[start_beat]` |
| `segments[].end_time` | float | `beats[end_beat]`, or `source.duration` when `end_beat == len(beats)` |
| `segments[].chord` | str | Harte label or `N`; always the root-position label; consecutive segments may repeat it when the bass changes under one chord |
| `segments[].candidates` | list of 3 str | best first by the recognizer's own scores over the segment, which aren't written; `candidates[0] == chord` when `edited` is false, and the analyzer's ranking for the span the segment came from when it is true; when a diminished chord was respelled by where it leads, `candidates[1]` is the recognizer's label for the same notes |
| `segments[].bass` | str or `null` | the segment's held bass, sharps only (`C` to `B`): the per-beat bass (the lowest note sounding in the bass register) that holds for at least 2 beats under the chord; when no value holds that long (a one-beat chord, a bass moving every beat), the most frequent per-beat value, silence included, ties to a note and then to the earliest; a bass move shorter than 2 beats under an unchanged chord (a passing tone, an alternating C–E or C–G accompaniment) is not reported; `null` for `N` and when no beat has a note in the bass register |
| `segments[].inversion` | `"root"`, `"first"`, `"second"`, `"third"`, `"non_chord"`, or `null` | `chord` over `bass`, by the bass's place among the chord's tones from the root up: `root`; `first`, the third, or the fourth of a `sus4`; `second`, the fifth; `third`, the seventh of a `7`, `maj7`, `min7`, `hdim7` or `dim7`, or the added sixth of a `min6`; `non_chord` when it is not a chord tone; `null` whenever `bass` is `null` |
| `segments[].numeral` | str or `null` | Roman numeral of the root-position chord relative to `key`, `<accidental><roman><suffix>[/<target>]` (grammar above), e.g. `bVII`, `ii7`, `IVmaj7`, `#i°7`, `viiø7/V`; `ø` and `°` are written as characters; `null` for `N` |
| `segments[].role` | `"diatonic"`, `"secondary_dominant"`, `"borrowed"`, `"chromatic"`, or `null` | how the chord relates to the key; `secondary_dominant` includes secondary leading-tone chords; `null` for `N` |
| `segments[].function` | `"tonic"`, `"predominant"`, `"dominant"`, or `null` | harmonic function; set only for `diatonic` chords |
| `segments[].target` | str or `null` | for `secondary_dominant`, the numeral of the chord it tonicizes (`V7/V` → `V`, `vii°7/ii` → `ii`); `null` otherwise |
| `segments[].edited` | bool | `false`: `chord` and `bass` are the analyzer's. `true`: the user set them in the viewer, either by choosing a chord or bass for this segment other than the one it had, or by a merge or removal that extended it over a neighbour with a different chord or bass, a span where the analyzer didn't hear it. A merge of neighbours with the same chord and bass is `true` only if either was; a split gives both halves the segment's flag |

A chord label is `<root>:<quality>` in Harte syntax. The root is one of `C C# D D# E F F# G G# A A# B`, spelled with sharps only, and the quality is one of `maj`, `min`, `7`, `maj7`, `min7`, `min6`, `hdim7`, `dim7` and `sus4`. `N` means no chord. A key label is the label of its tonic triad, `<root>:maj` or `<root>:min`, sharps only. `bass` is spelled the same way, as a bare root.

`chord` and `numeral` stay root-position labels. A slash chord is `chord` over `bass`: `C:maj` with bass `E` is C/E. Figured-bass numerals (`I6`, `V65`) are not written, since they follow from `numeral` and `inversion` by a fixed table. A bass move shorter than 2 beats under an unchanged chord is neither reported nor cut on, because it would turn a held chord into a flicker of inversions without changing the harmony. Consecutive segments may repeat a `chord` when the bass changes under it; in v1 and v2 they never did.

Segments are contiguous: each `start_beat` equals the previous `end_beat`, and the first starts at beat 0. Leading and trailing silence is labeled `N`. The only unlabeled span is the sub-beat head between the start of the audio and `beats[0]`, which is shorter than one beat.

The file is UTF-8, and non-ASCII characters are written as themselves rather than as `\u` escapes: the numerals' `ø` and `°`, and a non-ASCII `source.path`. A path that is not valid UTF-8 keeps `\u` escapes for the bytes that don't decode.

The schema is stable. Any change to the documented schema, an added field included, is breaking and bumps `schema_version`. Schema 4 kept schema 3's fields and widened what they hold: the chord qualities, the numerals, what `third` means in `inversion`, which chords `secondary_dominant` covers, and what `candidates[1]` means after a respelling. Schema 5 added `segments[].edited`, so a corrected chord is told apart from a heard one. Schema 6 added `generator.engine`; a file below 6 was written by the DSP. The viewer reads 4 to 6 and saves a 6: it fills in `edited: false` on a 4, and on a 4 or 5 the engine `{"name": "dsp", "version": <generator.version>}`.

```json
{
  "schema_version": 6,
  "generator": {"name": "chordotomy", "version": "0.0.0", "engine": {"name": "dsp", "version": "0.0.0"}},
  "source": {"path": "song.mp3", "duration": 5.0},
  "key": {"label": "C:maj", "source": "estimated", "candidates": ["C:maj", "F:maj", "G:maj"]},
  "beats": [0.023, 0.534, 1.045, 1.533, 2.043, 2.531, 3.042, 3.529, 4.04, 4.528],
  "segments": [
    {
      "start_beat": 0, "end_beat": 2, "start_time": 0.023, "end_time": 1.045,
      "chord": "C:maj", "candidates": ["C:maj", "C:7", "C:maj7"],
      "bass": "C", "inversion": "root",
      "numeral": "I", "role": "diatonic", "function": "tonic", "target": null, "edited": false
    },
    {
      "start_beat": 2, "end_beat": 4, "start_time": 1.045, "end_time": 2.043,
      "chord": "C:maj", "candidates": ["C:maj", "C:7", "A:min7"],
      "bass": "E", "inversion": "first",
      "numeral": "I", "role": "diatonic", "function": "tonic", "target": null, "edited": false
    },
    {
      "start_beat": 4, "end_beat": 6, "start_time": 2.043, "end_time": 3.042,
      "chord": "F:maj7", "candidates": ["F:maj7", "F:maj", "F:7"],
      "bass": "F", "inversion": "root",
      "numeral": "IVmaj7", "role": "diatonic", "function": "predominant", "target": null, "edited": false
    },
    {
      "start_beat": 6, "end_beat": 8, "start_time": 3.042, "end_time": 4.04,
      "chord": "F#:hdim7", "candidates": ["F#:hdim7", "A:min6", "A:min"],
      "bass": "F#", "inversion": "root",
      "numeral": "viiø7/V", "role": "secondary_dominant", "function": null, "target": "V", "edited": false
    },
    {
      "start_beat": 8, "end_beat": 10, "start_time": 4.04, "end_time": 5.0,
      "chord": "G:7", "candidates": ["G:7", "G:maj", "E:min"],
      "bass": "B", "inversion": "first",
      "numeral": "V7", "role": "diatonic", "function": "dominant", "target": null, "edited": false
    }
  ]
}
```

## Editing in the viewer

The viewer corrects a timeline that `chordotomy analyze` wrote. The editing model is `viewer/edit.js`: pure functions that take a timeline and return a new one, sharing the segments they didn't change. `viewer/app.js` wires them to the page.

An edit acts on the current segment, the one under the playhead. A pick takes a moment, and playback may move on meanwhile. So while one of the Root, Quality and Bass selects has focus, or the pointer is pressed on it, the target is pinned to the segment that was current when that began. Split, Merge and Delete act on the segment that was current when their press began, for the same reason.

There are five operations:

- **Set a chord:** a chord and bass for one segment, from the selects or a candidate. `inversion` follows from the two. `candidates` stay what the analyzer heard, so its other readings stay on offer. Choosing the chord and bass the segment already has is not an edit.
- **Split** at a beat strictly inside a segment. Both halves keep everything the segment had, `edited` included, since neither half's chord changed.
- **Merge** a segment with the one before or after. It keeps its chord, bass and candidates over both spans.
- **Delete** a segment. The one before takes its span, or the next one for the first segment. A lone segment can't be deleted: nothing would take its span, and setting it to `N` silences it.
- **Set the key:** a key fixes it as `--key` does, with `source: given`, and Estimated estimates it again from the chords.

An edit never merges neighbours that end up with the same chord. The analyzer writes such neighbours itself when the bass changes under a chord, a split would undo itself before the user could change one half, and the analysis already reads them as one chord run. Merging is explicit.

Boundaries only move onto beats the analyzer found, so the viewer can correct a timeline but not start one. Segment times are read from `beats`, or `source.duration` at the end, as `chordotomy analyze` writes them. Nothing is computed, so an edit adds no rounding.

Every edit ends in a re-analysis. The segments are grouped into chord runs, and `viewer/harmony.js`, the port of "Harmonic analysis", estimates the key again and recomputes every segment's numeral, role, function and target. A given key keeps its label, and only its candidates follow the chords. Diminished twins are not respelled: a chord the user picks is spelled as picked, and the others keep the analyzer's spelling. Opening a file doesn't re-analyze, so the analyzer's fields stand until the first edit.

Undo keeps whole timelines, not inverse edits. They are small, and each snapshot shares the segments its edit didn't change. Undoing back to the timeline as opened or last saved gives back that very object, which is how the page knows nothing is unsaved. An edit that changes nothing adds no step.

`edited` keeps the provenance: it marks a segment whose chord and bass are the user's, not the analyzer's. The field's row above says what each operation does to it. The `explain-harmony` skill reads it, so it doesn't present an edited chord's candidates as alternative readings.

Saving downloads the timeline as `<stem>.edited.chords.json`, where `<stem>` is the basename of `source.path` without its extension, so `song.edited.mp3` saves as `song.edited.edited.chords.json`, the name the skill looks for next to the recording. Without a usable `source.path`, `<stem>` is the opened file's name without `.edited.chords.json`, `.chords.json` or `.json`. The file is a `Blob` downloaded through an `<a download>` link, because that works from `file://` in every browser and sends nothing anywhere. The viewer never writes to the file it opened, so what the analyzer wrote stays as it was, and the skill looks for the edited name first. The timeline counts as saved once the download starts; if the user cancels a browser's save dialog, the page can't tell.

A batch of dropped or picked files opens whole or not at all, so the recording and the timeline shown are always a pair the user chose together. The timeline is read and validated before anything changes, every field of every segment included, so whatever opens can be drawn and edited. With unsaved edits the viewer asks once before it replaces them, and the browser asks before the page closes. A batch with only a recording replaces the recording and keeps the edits.

## Evaluation

`chordotomy evaluate {tiny-aam,guitarset} [--limit N]` scores the analyzer on real audio. It is opt-in and for development (the `eval` extra). Nothing in it reaches the timeline JSON. Both datasets are CC BY 4.0 on Zenodo. They are downloaded on demand into the checkout's gitignored `datasets/`, never committed.

- **Tiny AAM**: 20 mixed tracks with one chord per beat, reduced to major, minor and `N`. Its annotation has no bass, so its `majmin_inv` assumes every reference chord is in root position; read it as bass agreement with that assumption, not as inversion accuracy.
- **GuitarSet**: the 180 accompaniment takes (`_comp`, mono mic), scored against the performed chord annotation, which carries the bass.

Scoring is `mir_eval`, and the table is per track with an `overall` row weighted by duration. These things matter when reading it:

- `majmin` reduces sevenths and sixths to the triad. It leaves out power chords, sus and diminished chords, so those intervals are not counted at all.
- `N` against `N` counts as correct. A track the analyzer calls all `N` is scored right wherever the reference is also `N`, so `N_est` and `N_ref`, the shares of duration labeled `N`, are printed beside the scores.
- `sevenths` scores only references that are `maj`, `min`, `7`, `maj7`, `min7` or `N`, and needs the seventh to match. On Tiny AAM, whose references are all major, minor or `N`, it is therefore a false-positive check (see "Tuning the v4 constants").
- `tetrads` needs the root and the whole pitch set to match. It is the metric that checks the full pitch set of a half-diminished, diminished-seventh, minor-sixth or sus4 reference: `root` scores only their roots, `majmin` leaves out half-diminished, diminished-seventh and sus4 references (it compares a minor-sixth one by its minor triad), and `sevenths` leaves out all four.
- `majmin_inv` compares the bass as a scale degree above the root, so a right chord over the wrong bass, or over no detected bass (`bass` null), fails it.
- A segment whose bass is not its root is scored as a slash chord (`C:maj/3`), and mir_eval reads the slash's degree into the estimate's pitch set. A bass on a chord tone adds nothing, but a bass outside the chord adds a tone: `C:maj/2` is C–D–E–G. So a `non_chord` bass costs `sevenths` and `tetrads`, and `majmin` too when it lies within a perfect fifth above the root, the part of the pitch set `majmin` compares. `root` ignores the bass.

Baseline, front end at `b70fb50`:

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.773 | 0.738 | 0.725 | — | 0.653 | 0.123 | 0.015 |
| GuitarSet (180 takes) | 0.485 | 0.519 | 0.460 | — | 0.335 | 0.450 | 0.000 |

On Tiny AAM the analyzer calls 12% of the duration `N` against 1.5% in the reference, and most of that is two tracks: 2720 (77% `N`) and 2990 (56%).

Whitened front end, at the commit that adds these rows. The root, majmin, sevenths and majmin_inv values reproduce the ones printed before `tetrads` existed. The decode constants were tuned on Tiny AAM; GuitarSet was held out. `BASS_WEIGHT`, `BASS_TONE`, `TEMPERATURE` and `CHORD_SECONDS` were the best Tiny AAM majmin among the values that kept the default test suite green. The suite is a hard constraint: two-beat chord changes and first-inversion chords must survive. Without it the best Tiny AAM majmin was about 0.823. The 0.788 below is the price of that constraint, chosen deliberately.

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.848 | 0.788 | 0.760 | 0.760 | 0.691 | 0.011 | 0.015 |
| GuitarSet (180 takes) | 0.688 | 0.619 | 0.492 | 0.317 | 0.373 | 0.007 | 0.000 |

v4 vocabulary, at the commit that adds these rows:

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.839 | 0.793 | 0.748 | 0.748 | 0.690 | 0.011 | 0.015 |
| GuitarSet (180 takes) | 0.720 | 0.661 | 0.531 | 0.347 | 0.395 | 0.007 | 0.000 |

GuitarSet's sevenths rise from 0.492 to 0.531, its majmin from 0.619 to 0.661 and its tetrads from 0.317 to 0.347, while Tiny AAM, annotated in major and minor only, gives up 0.9 pp of root and 1.2 pp of sevenths and calls a quality new in v4 on 3.7 % of its duration. The tuning signal was a sweep over cached features scored on the labels alone, without the bass. Those scores sit above these rows, because the CLI's scores also pay for basses outside the chord, as noted above for slash chords. At stage 1 the gap was up to 2.2 pp on Tiny AAM and 7.4 pp on GuitarSet, and the sweep raised each floor below by it. Under v4 it is larger, 2.5 pp of Tiny AAM sevenths and 9.0 pp of GuitarSet sevenths, and the sweep also checked every floor on the CLI's own scoring, reproduced from the cache.

### Tuning the v4 constants

The quality offsets, `TEMPERATURE`, `CHORD_SECONDS`, `BASS_WEIGHT`, `BASS_TONE` and `PARTIAL_DECAY` were tuned together by coordinate descent on the planned grid, the offsets and then the decode constants in turn until the point stopped moving. The objective is the highest GuitarSet sevenths over all 180 takes, whose two halves differ a lot. Tiny AAM is the false-positive guard: annotated in major and minor only, it scores a sus4 call as a majmin miss and a tetrad call as a sevenths miss. Its floors (root ≥ 0.835, majmin ≥ 0.775, sevenths ≥ 0.730, `N_est` within 0.02 of `N_ref`) bound how much of the vocabulary the decoder may use; GuitarSet has to keep majmin ≥ 0.60 and sevenths ≥ 0.512. The synthesized suite was a hard constraint on every point, the suspension test included: the offsets the datasets alone prefer, `sus4` at -0.3 or -0.4, smooth its four-beat `G:sus4` into the `G:maj` after it.

Each constant was then moved one grid step either way, and margin on the suite came first, because stage 1's point was one step from breaking an inversion test. At the descent's point, with `PARTIAL_DECAY` 0.6, one step of `TEMPERATURE` up, `BASS_WEIGHT` up, `BASS_TONE` down or `PARTIAL_DECAY` down smoothed away the two-beat `A:min/C` inside `C:maj`, the stage-1 binding case. Moving `PARTIAL_DECAY` to 0.8 was a cost: 0.3 pp of label-only GuitarSet sevenths, and Tiny AAM's root, majmin and sevenths from 0.844, 0.799 and 0.754 to 0.839, 0.793 and 0.748. It is what keeps the suite green at every one-step neighbour. `7`, `maj7`/`min7`, `min6`/`hdim7`, `dim7` and `CHORD_SECONDS` also hold every floor at both neighbours. Elsewhere Tiny AAM's root floor binds, cleared by 0.4 pp: one step of `sus4` up, `TEMPERATURE` down, `BASS_WEIGHT` down, `BASS_TONE` up or `PARTIAL_DECAY` up takes it to between 0.822 and 0.834. `sus4` is pinned from both sides, since at -0.3 the suspension test fails.

The chosen point is therefore not the objective's best. One step outside the grid, three neighbours score higher with the suite green and every floor held (GuitarSet sevenths on the CLI): `TEMPERATURE` 0.035 (0.534) and `BASS_TONE` 0.6 (0.532) were not taken because each uses up the `A:min/C` case's margin, which fails at `TEMPERATURE` 0.040 and with both moves together. `maj7`/`min7` at -0.05 (0.540) was not taken because it calls more sevenths on major and minor material: Tiny AAM sevenths falls to 0.744, and at the next step, 0, to 0.715, under its floor.

## Design decisions

### An analyzer, not a transcriber

Chord timelines (Chordify, Moises) and audio → score (Klangio) are already commercial products. Automatic harmonic analysis with an explanation, the "why does this progression work" part, is the gap. So chordotomy stops at chords and their function. Staff notation, melody → MIDI, and section detection are out. The first two need note-level rhythm, meaning quantization and triplets, which is the hardest and least distinctive part of the problem. Section detection is a research problem of its own. Model training is out as well: DSP and pretrained models only.

Chord extraction will sometimes be wrong, and the analysis is only as good as the chords. That's why correcting chords and entering a progression by hand are core features rather than extras.

### Key from chords, not audio

The key is estimated from the chord segments, not from the recording. Corrected or hand-entered chords then get the same analysis as extracted ones, and the estimator can be tested with plain progressions instead of synthesized audio.

### Re-analysis in the browser, Python as the reference

A corrected chord changes the key estimate, the numerals and the roles around it, and the viewer shows that at once. So the viewer runs the harmonic analysis itself, in a JavaScript port. It has to work opened from `file://`, with no build step and a CSP that allows no network, and the alternatives don't fit that. Pyodide would run the Python itself, but it is a large runtime loaded over the network and needs `wasm-unsafe-eval`. A local server would be one more thing to install and run. Saving the edits unanalyzed for the CLI to finish would not show the analysis while editing.

The port is small: key estimation, numerals and roles, inversions, and the grouping into chord runs. Python stays the reference, and a rule changes there first. The golden vectors make drift a test failure on whichever side changed: pytest fails until the vectors are regenerated from the Python, and node fails until the port agrees with them.

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

The constants trade Tiny AAM score for the test suite; see the notes under the Evaluation tables. The wider vocabulary came next, as v4 (below). Not done: a gate that weighs tonal evidence as well as level, since the -40 dB gate can force a very quiet tonal passage to `N`; beat tracking, which locks Tiny AAM track 0080 at half tempo; and the qualities "Chord vocabulary v4" leaves out.

### Chord vocabulary v4

Through v3 the qualities were `maj`, `min` and `7`. Pop harmony leans on more than that: major and minor sevenths as colour, the minor sixth on the subdominant, passing diminished and half-diminished sevenths, and suspensions. v3 had to name each of them by a triad, often the wrong one. v4 adds `maj7`, `min7`, `min6`, `hdim7`, `dim7` and `sus4`, written on a chart as Cmaj7, Cm7, Cm6, Cm7♭5, Cdim7 and Csus4.

Left out:

- `maj6`: its pitch set is `min7`'s (C6 is Am7), and an `I6` numeral would read as a first inversion.
- `sus2`: its pitch set is `sus4`'s (Csus2 is Gsus4).
- The augmented and diminished triads: rare in pop, and "dim" on a pop chart usually means the diminished seventh.
- Extensions (9, 11, 13, add9): beyond a beat-median chroma. The ninth is where the fifth's own twelfth lands.

The new qualities bring pitch-set twins: a `min6` has the notes of the `hdim7` a minor third below (Gm6 and Em7♭5 are both G–Bb–D–E), and a `dim7` the notes of three other `dim7`s. The treble can't tell twins apart; only the bass profile, which favours the root, can. So `min6` and `hdim7` share one offset, and the bass, not the offset, decides between them. Without a bass on one of their roots they tie, and label order picks one, which is arbitrary. A musician spells a diminished chord by where it leads, its root a half step below the next chord's root, so the analyzer respells twins that way after segmentation (see Stages implemented). For a `dim7` the bass can't settle the root at all: the chord is symmetric, so its bass is its inversion. An `hdim7` is never respelled, because it only wins over its `min6` twin on bass evidence; a tie goes to the `min6`.

Tetrads and `sus4` pay an offset because without one, extended chords win by default. A triad's own partials land on tetrad tones: the third's twelfth on the seventh (E → B under C, C → G under A:min), the fifth's twelfth on the ninth. Whitening lifts a lone partial in a sparse region, so a played triad shows a trace of its seventh, and a tetrad's template, the triad plus one tone, collects it. Templates with partials (below) take some of that back; the offsets take the rest. Played chords clear their triads by different margins, so each group has its own offset. The `7` needs none to hold Tiny AAM's floors. `sus4` has the largest: Tiny AAM, annotated in major and minor only, scores every sus4 call as a majmin miss, and a played sus4 clears its triad by more than a played seventh does.

Templates carry partials. Through v3 they were binary: 1 on each chord tone, 0 elsewhere. Now each tone also has its octave, twelfth and double octave, weighted by `PARTIAL_DECAY`, so a template expects a triad's own partials and stops reading them as a tetrad. In the planning sweep, at a decay of 0.6 and the same offsets, partials gained 2 to 3 pp of root, majmin and sevenths on GuitarSet and moved Tiny AAM by up to 0.5 pp either way. The bass profiles and `inversion` keep the binary chord tones: they ask which tone the bass is, not what it sounds like.

NNLS note profiles (Mauch & Dixon 2010, from the paper, not the GPL plugin) were tried during planning and rejected. Each frame of the whitened spectrum was decomposed into 84 note profiles with partials by non-negative least squares, then folded through the same pitch windows. On Tiny AAM that cost 2 pp of majmin at every offset tried; on GuitarSet it gained 2 pp. This stage's bar was to lift sevenths without costing majmin, so no code implements it.

### Confidence is a rank, not a percentage

Template similarity is not a probability. Showing "GM7 81%" would claim precision the method doesn't have. Candidates are shown as a ranked list. Percentages appear only if a calibrated model produces them.

### Licenses

The project is MIT, so it takes no GPL or AGPL dependencies. That rules out Essentia (AGPL-3.0) and Chordino / NNLS Chroma (GPL); their ideas get reimplemented on librosa instead. librosa (ISC) and music21 (BSD-3) are fine. Demucs's code is MIT, but its pretrained weights are a separate question; see "Bass from DSP, not Demucs". Pretrained weights can carry terms separate from their code, such as non-commercial model files, so check both.

### Synthesized test fixtures

Tests build audio in code, for example additive tones for known chords at a known tempo. The fixtures are license-free, and the ground truth is exact.
