# chordotomy

Dissect a song's harmony. Give it a recording and it finds the chords on the beat, labels them with Roman numerals, and points out the moves worth noticing (the secondary dominant, the borrowed chord) with a short note on why they work.

It analyzes; it doesn't transcribe. There is no staff notation, on purpose.

Yes, chordotomy is also a spinal surgery. This one cuts chords.

> **Status:** first slice works. `chordotomy analyze` writes a chord timeline of maj / min / 7 chords and `N` on detected beats. No Roman numerals yet.

Everything runs locally. Your audio never leaves your machine.

## What it won't do

- **Staff notation.** It doesn't produce MusicXML and doesn't work out note-level rhythm.
- **Melody transcription.** It doesn't produce melody → MIDI.
- **Song sections.** It doesn't label intro, verse, or chorus.

It stops at the chords and what they're doing. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#design-decisions) explains why.

## Roadmap

- [x] Chords on the beat from chroma + beat tracking (major / minor / dominant 7th)
- [ ] Roman-numeral analysis
- [ ] Slash chords from a Demucs bass stem, highlights for secondary dominants and borrowed chords, short explanations
- [ ] Viewer: playback that highlights the current chord, plus chord editing and manual entry

## Usage

```sh
uv run chordotomy analyze song.mp3            # writes song.chords.json
uv run chordotomy analyze song.mp3 -o out.json
```

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
