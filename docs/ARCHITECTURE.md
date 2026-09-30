# Architecture

The first two slices are implemented: chords on the beat, then key estimation and Roman-numeral analysis. This records the design decided before the first line of code (2026-09-29) and the reasons behind it.

## Pipeline

```text
audio ─→ beat tracking ─→ chroma per beat ─→ template match + temporal smoothing
                                                        │
                                                        ↓
viewer ←── chord-timeline JSON ←── key estimation + Roman numerals
```

- Chords are called per beat, not per frame, so a passing note doesn't become a chord change.
- The first version uses no ML: librosa chroma and beat tracking, then major / minor / 7th templates.
- Later, a Demucs bass stem supplies the actual bass note, which settles slash chords and inversions (`F#7/A#`). The chroma of the full mix can't tell you which note is in the bass.
- Analysis marks secondary dominants and borrowed chords. An LLM writes a short explanation for each one.
- A Python CLI (uv, Typer) writes the JSON. A static HTML viewer plays the audio, highlights the current chord, and lets you correct chords.

### Stages implemented

Audio is decoded to mono at 22050 Hz. The harmonic part is taken with HPSS, so drums don't leak into the chroma.

Beats come from `librosa.beat.beat_track` with `trim=False`, because the default trim dropped the last real beats of a synthesized clip. The tracker places no beats in leading or trailing silence. So the grid is extended at the median beat period (the tracker's tempo when only one beat is found) in both directions. Without that, the final chord's last beat would swallow a silent tail, and leading silence would have no beats to label `N`. A tail beat is added only if at least half a period remains, to avoid a sliver interval. Beat tracking runs first, so a file with no beats fails before any chroma work.

Chroma is a CQT chroma with `norm=None`, reduced to the median over each beat. The default per-frame normalisation scales near-silent ringing up to full scale and gives a silent beat a random chord. After the median, 1 % of the loudest value is added to every bin. A beat far below that floor ends up nearly flat and matches `N`. A quiet chord well above the floor keeps its shape.

Templates are binary: 12 roots × {maj, min, 7}, plus a flat template for `N`. Each beat's chroma is scored against every template by cosine similarity.

Smoothing is a Viterbi decode over the per-beat similarities. Likelihoods are `exp((sim - 1) / 0.02)` and a state stays put with probability 0.5, the rest spread evenly over the other states. The cosine gap between a chord and its maj / 7 sibling is only about 0.1, so without the sharpening the transition prior swamps the observations and everything collapses to `N`. The self-loop is weak enough that a real change lasting two beats survives, and strong enough that a single beat where a chord flickers to its sibling does not.

Consecutive beats with the same state become one segment. Each segment carries three candidate labels: the smoothed chord first, then the labels with the highest mean similarity over the segment. Scores are not written out, per the confidence rule below.

### Harmonic analysis

The analysis is a pure function of the chord segments (label and beat count) and an optional key. It takes no audio (see "Key from chords, not audio" under Design decisions). It lives in `harmony.py`.

A chord is diatonic when every chord tone (root, third, fifth, and the seventh of a `7` chord) lies in the key's scale: major, or natural minor. Minor admits one more case, `maj` and `7` on the dominant degree, the harmonic-minor V and V7. The raised leading tone is admitted nowhere else, so `F:min` in A minor is chromatic, not diatonic. The resulting sets are major: `I ii iii IV V V7 vi`; minor: `i III iv v V V7 VI VII VII7`. `VII7` is there because `G:7` in A minor is G–B–D–F, all natural minor. `C:7` in C major is not diatonic, since Bb is outside the scale.

The key is one global key per file. Each of the 24 keys scores the sum over chords of beats times a weight. A non-diatonic chord weighs 0. A diatonic chord weighs 3 on the tonic, 2 on the subdominant or dominant degree, and 1 on any other degree. Beats are used rather than seconds because they are the musical duration and the segments carry them. Relative keys share six triads, so the choice between them comes down to where the time goes: `Am–F–C–G` with equal beats is C major, and the same loop with `Am` twice as long is A minor. Ties break on beats spent on the key's own tonic triad, then on whether the first chord is that triad, then on the fixed key order. A timeline of only `N` has no key. The top 3 keys are written out.

`--key` replaces the estimated key. The estimator still runs, so `key.candidates` keeps showing what the chords suggest, and you can see how far an override is from it.

A numeral is the root's offset from the tonic, spelled with accidentals relative to the key's own scale (major scale, or natural minor). `maj` and `7` chords are uppercase, `min` chords lowercase, and `7` chords append `7`. Accidentals describe the root only, so `E:7` in A minor is `V7`, never with a raised leading tone. Diminished triads are not in the chord vocabulary, so `vii°` in major and `ii°` in minor are never detected and never appear.

Each chord gets one role. The first match wins:

1. `diatonic`, by the test above in the key's own mode.
2. `secondary_dominant`, for a `maj` or `7` chord whose root a perfect fifth below is a tonicizable diatonic triad. Major targets are `ii iii IV V vi`; minor targets are `III iv V VI VII`. Never the tonic, never a diminished degree. The numeral is `V/<target>` or `V7/<target>`, and `target` names the tonicized numeral. The rule is the pitch relationship, so a `V7/V` that resolves elsewhere is still labeled.
3. `borrowed`, when the chord is diatonic in the parallel mode (same tonic, other mode). The seventh counts, so `A#:7` (Bb7) is a borrowed `bVII7` in C major, while `D#:7` and `G#:7` (Eb7, Ab7) are not borrowed, because Db and Gb are outside C minor.
4. `chromatic`, everything else, with the plain numeral.

Two chords satisfy both rule 2 and rule 3, both in minor keys: the major triads on the tonic and the subdominant. `A:maj` in A minor is either `V/iv` or a borrowed `I`, and `D:maj` is either `V/VII` or a borrowed `IV`. Here the label looks one segment ahead. The chord is a secondary dominant only when the immediately following segment is diatonic in the key and has the target's root: `D:min` after `A:maj` (`D:7` and `D:maj` are not diatonic in A minor), `G:maj` or `G:7` after `D:maj`. Any other chord, a non-diatonic chord on that root, an `N`, or the end of the track makes it borrowed. Silence is not a resolution, however long. Every other label depends on the chord and key alone.

The function is set for diatonic chords only: `I`, `III`, `VI` are `tonic`; `II`, `IV` are `predominant`; `V`, `VII` are `dominant`. `iii` and `vi` are tonic substitutes, and `VII` in minor is the subtonic dominant. Other roles have no function.

## The chord-timeline JSON

This is the project's public seam. It carries beat positions, not just seconds, so another tool, or a notation stage someone else builds, can consume it. `chordotomy analyze` writes it as schema version 2.

| field | type | meaning |
| --- | --- | --- |
| `schema_version` | int, `2` | schema version of this file |
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
| `segments[].chord` | str | Harte label or `N` |
| `segments[].candidates` | list of 3 str | best first, `candidates[0] == chord`, no scores |
| `segments[].numeral` | str or `null` | Roman numeral relative to `key` (grammar above); `null` for `N` |
| `segments[].role` | `"diatonic"`, `"secondary_dominant"`, `"borrowed"`, `"chromatic"`, or `null` | how the chord relates to the key; `null` for `N` |
| `segments[].function` | `"tonic"`, `"predominant"`, `"dominant"`, or `null` | harmonic function; set only for `diatonic` chords |
| `segments[].target` | str or `null` | for `secondary_dominant`, the numeral of the chord it tonicizes (`V7/V` → `V`); `null` otherwise |

A chord label is `<root>:<quality>` in Harte syntax. The root is one of `C C# D D# E F F# G G# A A# B`, spelled with sharps only, and the quality is `maj`, `min`, or `7`. `N` means no chord. A key label is the label of its tonic triad, `<root>:maj` or `<root>:min`, sharps only.

Segments are contiguous: each `start_beat` equals the previous `end_beat`, and the first starts at beat 0. Leading and trailing silence is labeled `N`. The only unlabeled span is the sub-beat head between the start of the audio and `beats[0]`, which is shorter than one beat.

The schema is stable. Any change to the documented schema, an added field included, is breaking and bumps `schema_version`.

```json
{
  "schema_version": 2,
  "generator": {"name": "chordotomy", "version": "0.0.0"},
  "source": {"path": "song.mp3", "duration": 4.0},
  "key": {"label": "C:maj", "source": "estimated", "candidates": ["C:maj", "G:maj", "F:maj"]},
  "beats": [0.116, 0.604, 1.092, 1.58, 2.068, 2.556, 3.044, 3.532],
  "segments": [
    {
      "start_beat": 0,
      "end_beat": 4,
      "start_time": 0.116,
      "end_time": 2.068,
      "chord": "C:maj",
      "candidates": ["C:maj", "C:7", "A:min"],
      "numeral": "I",
      "role": "diatonic",
      "function": "tonic",
      "target": null
    },
    {
      "start_beat": 4,
      "end_beat": 6,
      "start_time": 2.068,
      "end_time": 3.044,
      "chord": "D:7",
      "candidates": ["D:7", "D:maj", "B:min"],
      "numeral": "V7/V",
      "role": "secondary_dominant",
      "function": null,
      "target": "V"
    },
    {
      "start_beat": 6,
      "end_beat": 8,
      "start_time": 3.044,
      "end_time": 4.0,
      "chord": "G:7",
      "candidates": ["G:7", "G:maj", "B:min"],
      "numeral": "V7",
      "role": "diatonic",
      "function": "dominant",
      "target": null
    }
  ]
}
```

## Design decisions

### An analyzer, not a transcriber

Chord timelines (Chordify, Moises) and audio → score (Klangio) are already commercial products. Automatic harmonic analysis with an explanation, the "why does this progression work" part, is the gap. So chordotomy stops at chords and their function. Staff notation, melody → MIDI, and section detection are out. The first two need note-level rhythm, meaning quantization and triplets, which is the hardest and least distinctive part of the problem. Section detection is a research problem of its own. Model training is out as well: DSP and pretrained models only.

Chord extraction will sometimes be wrong, and the analysis is only as good as the chords. That's why correcting chords and entering a progression by hand are core features rather than extras.

### Key from chords, not audio

The key is estimated from the chord segments, not from the recording. Corrected or hand-entered chords then get the same analysis as extracted ones, and the estimator can be tested with plain progressions instead of synthesized audio.

### Local-first

People will feed it commercial recordings. A hosted upload service would mean storing copyrighted audio, so audio never leaves the machine. Demucs is too heavy for the browser anyway.

### Confidence is a rank, not a percentage

Template similarity is not a probability. Showing "GM7 81%" would claim precision the method doesn't have. Candidates are shown as a ranked list. Percentages appear only if a calibrated model produces them.

### Licenses

The project is MIT, so it takes no GPL or AGPL dependencies. That rules out Essentia (AGPL-3.0) and Chordino / NNLS Chroma (GPL); their ideas get reimplemented on librosa instead. librosa (ISC), Demucs (MIT), and music21 (BSD-3) are fine. Pretrained weights can carry terms separate from their code, such as non-commercial model files, so check both.

### Synthesized test fixtures

Tests build audio in code, for example additive tones for known chords at a known tempo. The fixtures are license-free, and the ground truth is exact.
