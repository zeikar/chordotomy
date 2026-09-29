# Architecture

Nothing is implemented yet. This records the design decided before the first line of code (2026-09-29) and the reasons behind it.

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

## The chord-timeline JSON

This is the project's public seam. It carries beat positions, not just seconds, so another tool, or a notation stage someone else builds, can consume it. The schema is still to be designed. Once it exists, document it here and keep it stable.

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
