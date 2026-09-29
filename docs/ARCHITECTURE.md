# Architecture

The first slice is implemented: chords on the beat, with no Roman numerals yet. This records the design decided before the first line of code (2026-09-29) and the reasons behind it.

## Pipeline

```text
audio ─→ beat tracking ─→ chroma per beat ─→ template match + temporal smoothing
                                                        │
                                                        ↓
viewer ←── Roman-numeral analysis ←────────── chord-timeline JSON
```

- Chords are called per beat, not per frame, so a passing note doesn't become a chord change.
- The first version uses no ML: librosa chroma and beat tracking, then major / minor / 7th templates.
- Later, a Demucs bass stem supplies the actual bass note, which settles slash chords and inversions (`F#7/A#`). The chroma of the full mix can't tell you which note is in the bass.
- Analysis marks secondary dominants and borrowed chords. An LLM writes a short explanation for each one.
- A Python CLI (uv, Typer) writes the JSON. A static HTML viewer plays the audio, highlights the current chord, and lets you correct chords.

### Stages implemented

Audio is decoded to mono at 22050 Hz. The harmonic part is taken with HPSS, so drums don't leak into the chroma.

Beats come from `librosa.beat.beat_track` with `trim=False`, because the default trim dropped the last real beats of a synthesized clip. The tracker places no beats in leading or trailing silence. So the grid is extended at the median beat period in both directions. Without that, the final chord's last beat would swallow a silent tail, and leading silence would have no beats to label `N`. A tail beat is added only if at least half a period remains, to avoid a sliver interval. Beat tracking runs first, so a file with no beats fails before any chroma work.

Chroma is a CQT chroma with `norm=None`, reduced to the median over each beat. The default per-frame normalisation scales near-silent ringing up to full scale and gives a silent beat a random chord. After the median, 1 % of the loudest value is added to every bin. A beat far below that floor ends up nearly flat and matches `N`. A quiet chord well above the floor keeps its shape.

Templates are binary: 12 roots × {maj, min, 7}, plus a flat template for `N`. Each beat's chroma is scored against every template by cosine similarity.

Smoothing is a Viterbi decode over the per-beat similarities. Likelihoods are `exp((sim - 1) / 0.02)` and a state stays put with probability 0.5, the rest spread evenly over the other states. The cosine gap between a chord and its maj / 7 sibling is only about 0.1, so without the sharpening the transition prior swamps the observations and everything collapses to `N`. The self-loop is weak enough that a real change lasting two beats survives, and strong enough that a single beat where a chord flickers to its sibling does not.

Consecutive beats with the same state become one segment. Each segment carries three candidate labels: the smoothed chord first, then the labels with the highest mean similarity over the segment. Scores are not written out, per the confidence rule below.

## The chord-timeline JSON

This is the project's public seam. It carries beat positions, not just seconds, so another tool, or a notation stage someone else builds, can consume it. `chordotomy analyze` writes it as schema version 1.

| field | type | meaning |
| --- | --- | --- |
| `schema_version` | int, `1` | bumped on any change to the documented schema, added fields included |
| `generator.name` | `"chordotomy"` | |
| `generator.version` | str | the chordotomy version that wrote the file |
| `source.path` | str | the audio path as given on the command line |
| `source.duration` | float, seconds, 3 decimals | |
| `beats` | list of float seconds, 3 decimals, ascending | beat index = list position |
| `segments[].start_beat` | int | inclusive |
| `segments[].end_beat` | int | exclusive; may equal `len(beats)`, meaning the segment runs to the end of the audio |
| `segments[].start_time` | float | `beats[start_beat]` |
| `segments[].end_time` | float | `beats[end_beat]`, or `source.duration` when `end_beat == len(beats)` |
| `segments[].chord` | str | Harte label or `N` |
| `segments[].candidates` | list of 3 str | best first, `candidates[0] == chord`, no scores |

A chord label is `<root>:<quality>` in Harte syntax. The root is one of `C C# D D# E F F# G G# A A# B`, spelled with sharps only, and the quality is `maj`, `min`, or `7`. `N` means no chord.

Segments are contiguous: each `start_beat` equals the previous `end_beat`, and the first starts at beat 0. Leading and trailing silence is labeled `N`. The only unlabeled span is the sub-beat head between the start of the audio and `beats[0]`, which is shorter than one beat.

Manual correction, a later slice, edits `segments[].chord`. `candidates` are suggestions and stay as generated.

The schema is stable. Any change to the documented schema, an added field included, is breaking and bumps `schema_version`.

```json
{
  "schema_version": 1,
  "generator": {"name": "chordotomy", "version": "0.0.0"},
  "source": {"path": "song.mp3", "duration": 4.0},
  "beats": [0.116, 0.604, 1.092, 1.58, 2.068, 2.556, 3.044, 3.532],
  "segments": [
    {
      "start_beat": 0,
      "end_beat": 4,
      "start_time": 0.116,
      "end_time": 2.068,
      "chord": "C:maj",
      "candidates": ["C:maj", "C:7", "A:min"]
    },
    {
      "start_beat": 4,
      "end_beat": 8,
      "start_time": 2.068,
      "end_time": 4.0,
      "chord": "G:7",
      "candidates": ["G:7", "G:maj", "B:min"]
    }
  ]
}
```

## Design decisions

### An analyzer, not a transcriber

Chord timelines (Chordify, Moises) and audio → score (Klangio) are already commercial products. Automatic harmonic analysis with an explanation, the "why does this progression work" part, is the gap. So chordotomy stops at chords and their function. Staff notation, melody → MIDI, and section detection are out. The first two need note-level rhythm, meaning quantization and triplets, which is the hardest and least distinctive part of the problem. Section detection is a research problem of its own. Model training is out as well: DSP and pretrained models only.

Chord extraction will sometimes be wrong, and the analysis is only as good as the chords. That's why correcting chords and entering a progression by hand are core features rather than extras.

### Local-first

People will feed it commercial recordings. A hosted upload service would mean storing copyrighted audio, so audio never leaves the machine. Demucs is too heavy for the browser anyway.

### Confidence is a rank, not a percentage

Template similarity is not a probability. Showing "GM7 81%" would claim precision the method doesn't have. Candidates are shown as a ranked list. Percentages appear only if a calibrated model produces them.

### Licenses

The project is MIT, so it takes no GPL or AGPL dependencies. That rules out Essentia (AGPL-3.0) and Chordino / NNLS Chroma (GPL); their ideas get reimplemented on librosa instead. librosa (ISC), Demucs (MIT), and music21 (BSD-3) are fine. Pretrained weights can carry terms separate from their code, such as non-commercial model files, so check both.

### Synthesized test fixtures

Tests build audio in code, for example additive tones for known chords at a known tempo. The fixtures are license-free, and the ground truth is exact.
