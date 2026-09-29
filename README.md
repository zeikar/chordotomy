# chordotomy

Dissect a song's harmony. Give it a recording and it finds the chords on the beat, labels them with Roman numerals, and points out the moves worth noticing (the secondary dominant, the borrowed chord) with a short note on why they work.

It analyzes; it doesn't transcribe. There is no staff notation, on purpose.

Yes, chordotomy is also a spinal surgery. This one cuts chords.

> **Status:** skeleton. Nothing works yet.

Everything runs locally. Your audio never leaves your machine.

## What it won't do

- **Staff notation.** It doesn't produce MusicXML and doesn't work out note-level rhythm.
- **Melody transcription.** It doesn't produce melody → MIDI.
- **Song sections.** It doesn't label intro, verse, or chorus.

It stops at the chords and what they're doing. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#design-decisions) explains why.

## Roadmap

- [ ] Chords on the beat from chroma + beat tracking (major / minor / 7th), with Roman-numeral analysis
- [ ] Slash chords from a Demucs bass stem, highlights for secondary dominants and borrowed chords, short explanations
- [ ] Viewer: playback that highlights the current chord, plus chord editing and manual entry

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
