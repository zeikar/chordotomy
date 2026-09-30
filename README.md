# chordotomy

Dissect a song's harmony. Give it a recording and it finds the chords on the beat, labels them with Roman numerals, and points out the moves worth noticing (the secondary dominant, the borrowed chord). A short note on why each one works is planned.

It analyzes; it doesn't transcribe. There is no staff notation, on purpose.

Yes, chordotomy is also a spinal surgery. This one cuts chords.

> **Status:** first three slices work. `chordotomy analyze` writes a chord timeline of maj / min / 7 chords and `N` on detected beats, with the estimated key and Roman numerals; secondary dominants and borrowed chords are labeled. Each chord segment also carries its bass note and inversion.

Everything runs locally. Your audio never leaves your machine.

## What it won't do

- **Staff notation.** It doesn't produce MusicXML and doesn't work out note-level rhythm.
- **Melody transcription.** It doesn't produce melody → MIDI.
- **Song sections.** It doesn't label intro, verse, or chorus.

It stops at the chords and what they're doing. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#design-decisions) explains why.

## Roadmap

- [x] Chords on the beat from chroma + beat tracking (major / minor / dominant 7th)
- [x] Roman-numeral analysis, with highlights for secondary dominants and borrowed chords
- [x] Slash chords and inversions from the bass note (low-register DSP, no Demucs)
- [ ] Short explanations of the highlighted moves
- [ ] Viewer: playback that highlights the current chord, plus chord editing and manual entry

## Usage

```sh
uv run chordotomy analyze song.mp3            # writes song.chords.json
uv run chordotomy analyze song.mp3 -o out.json
uv run chordotomy analyze song.mp3 --key A:min   # analyze in A minor instead of the estimated key
```

`--key` takes `<root>:maj` or `<root>:min`, flats accepted; the JSON still lists the estimator's ranked candidates.

`analyze` refuses to overwrite an existing output unless you pass `--force`. An input with no detectable beats is reported as an error, not written as an empty timeline. The JSON format is described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#the-chord-timeline-json).

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra dev
uv run chordotomy --version
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## License

MIT
