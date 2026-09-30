# chordotomy

Dissect a song's harmony. Give it a recording and it finds the chords on the beat, labels them with Roman numerals, and points out the moves worth noticing (the secondary dominant, the borrowed chord). In Claude Code, a skill adds a short note on why each one works.

It analyzes; it doesn't transcribe. There is no staff notation, on purpose.

Yes, chordotomy is also a spinal surgery. This one cuts chords.

> **Status:** first three slices work. `chordotomy analyze` writes a chord timeline of maj / min / 7 chords and `N` on detected beats, with the estimated key and Roman numerals; secondary dominants and borrowed chords are labeled. Each chord segment also carries its bass note and inversion. The `explain-harmony` skill explains the highlighted moves in Claude Code.

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
- [x] Short explanations of the highlighted moves (a Claude Code skill)
- [x] Viewer: playback that highlights the current chord
- [ ] Chord editing and manual entry in the viewer

## Usage

```sh
uv run chordotomy analyze song.mp3            # writes song.chords.json
uv run chordotomy analyze song.mp3 -o out.json
uv run chordotomy analyze song.mp3 --key A:min   # analyze in A minor instead of the estimated key
```

`--key` takes `<root>:maj` or `<root>:min`, flats accepted; the JSON still lists the estimator's ranked candidates.

`analyze` refuses to overwrite an existing output unless you pass `--force`. An input with no detectable beats is reported as an error, not written as an empty timeline. The JSON format is described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#the-chord-timeline-json).

### Explanations in Claude Code

The repo is also a Claude Code plugin with one skill, `explain-harmony`. Install it once:

```text
/plugin marketplace add zeikar/chordotomy
/plugin install chordotomy@chordotomy
```

Then ask something like "explain the harmony of song.mp3". The skill runs `chordotomy analyze` locally with the plugin's own copy (it needs uv), reads the JSON, and explains the secondary dominants, borrowed chords, and bass lines. The audio stays on your machine; Claude reads only the chord timeline.

Working in this repo, `.claude/settings.json` registers the checkout itself as a directory marketplace and enables the plugin, so the skill runs from the working tree. The first session asks you to trust it; `claude plugin marketplace add .` does the same by hand.

## Viewer

The viewer plays a recording along with its chord timeline. It shows the current chord, its Roman numeral with figured bass, its role and bass note, and the other chords the analyzer heard, ranked. Chords are colored by role, so secondary dominants and borrowed chords stand out.

Open it at <https://zeikar.github.io/chordotomy/> once Pages is enabled, or open `viewer/index.html` from a checkout. Drop the recording and its `.chords.json` on the page, or pick them with **Open files**. The files stay in your browser. The page reads them locally and makes no network requests.

To check the chords by ear, turn on **Play chords**. The page plays each detected chord on every beat, with its bass note, under the recording. **Mute recording** leaves the chords on their own. The sound is synthesized in the browser.

Space plays and pauses. → goes to the next chord. ← goes back to the start of the current chord, or to the chord before when it is already within a second of the start, so pressing it twice steps back. C turns the chords on and off, M mutes the recording, and clicking a chord jumps to it. Editing chords comes later.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra dev
uv run chordotomy --version
uv run pytest
uv run ruff check . && uv run ruff format --check .
node --test viewer/tests/
```

The viewer is plain HTML, CSS, and JavaScript with no build step. Its tests need Node and no packages.

### Real-audio evaluation (opt-in)

`uv sync --extra dev --extra eval` adds mir_eval and pooch, which also enables the evaluation tests (skipped without it). Then:

```sh
uv run chordotomy evaluate tiny-aam [--limit N]
uv run chordotomy evaluate guitarset [--limit N]
```

Tiny AAM downloads 168 MB. GuitarSet downloads 39 MB of annotations plus 657 MB of audio, of which only the accompaniment takes being scored are extracted. Both datasets are CC BY 4.0. In a checkout they land in `datasets/`, which is gitignored; delete it to re-download. The default test run never touches the network. The scores are numbers for development only.

## License

MIT
