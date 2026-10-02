# chordotomy

Dissect a song's harmony. Give it a recording and it finds the chords on the beat, labels them with Roman numerals, and points out the moves worth noticing (the secondary dominant, the borrowed chord). In Claude Code, a skill adds a short note on why each one works.

It analyzes; it doesn't transcribe. There is no staff notation, on purpose.

Yes, chordotomy is also a spinal surgery. This one cuts chords.

> **Status:** everything on the roadmap below works. `chordotomy analyze` writes a chord timeline on detected beats, with the estimated key and Roman numerals. The chords come from the lv-chordia model when the `model` extra is installed, and from chordotomy's DSP front end otherwise. The model engine's chords are major, minor, dominant 7th, major 7th, minor 7th, half-diminished 7th, diminished 7th, sus4, dominant 7th sus4 (7sus4), augmented, diminished triad and sus2, with `N` for no chord; the DSP engine recognizes the same except sus2 and 7sus4, and also minor 6th. Secondary dominants, secondary leading-tone chords and borrowed chords are labeled. Each chord segment also carries its bass note and inversion. The DSP engine keeps a quiet passage's chords and calls most beats of drums alone `N` (81 % of them for the median drum stem). When the beat tracker locks at half tempo with the chord changes falling between its beats, the beat grid is doubled; a half-tempo grid whose beats fall on the chord changes is left as it is, since it costs no chord. In the viewer, chords can be corrected and entered on the analyzer's beat grid. The `explain-harmony` skill explains the highlighted moves in Claude Code.

Everything runs locally. Your audio never leaves your machine.

## What it won't do

- **Staff notation.** It doesn't produce MusicXML and doesn't work out note-level rhythm.
- **Melody transcription.** It doesn't produce melody → MIDI.
- **Song sections.** It doesn't label intro, verse, or chorus.

It stops at the chords and what they're doing. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#design-decisions) explains why.

## Roadmap

- [x] Chords on the beat from chroma + beat tracking (major / minor / dominant 7th / major 7th / minor 7th / minor 6th / half-diminished 7th / diminished 7th / sus4 / augmented / diminished triad / sus2 / 7sus4; the DSP does not call sus2 or 7sus4, which come from the model or a manual edit)
- [x] A pretrained model as the recognizer when installed (`uv sync --extra model`)
- [x] Roman-numeral analysis, with highlights for secondary dominants and borrowed chords
- [x] Slash chords and inversions from the bass note (low-register DSP, or lv-chordia's bass head with the model; no Demucs)
- [x] Short explanations of the highlighted moves (a Claude Code skill)
- [x] Viewer: playback that highlights the current chord
- [x] Chord editing and manual entry in the viewer

## Usage

```sh
uv run chordotomy analyze song.mp3            # writes song.chords.json
uv run chordotomy analyze song.mp3 -o out.json
uv run chordotomy analyze song.mp3 --key A:min   # analyze in A minor instead of the estimated key
uv run chordotomy analyze song.mp3 --engine dsp  # the DSP front end, even with the model installed
```

`--key` takes `<root>:maj` or `<root>:min`, flats accepted; the JSON still lists the estimator's ranked candidates.

`--engine` picks the chord recognizer. `auto`, the default, takes the lv-chordia model when it is installed and the DSP front end otherwise; `model` takes the model, and `dsp` the DSP. `--engine model` without the model installed is an error that names the install command. A broken model install is an error too, naming the reinstall and `--engine dsp`; it never quietly falls back to the DSP. The beats and the harmonic analysis are chordotomy's own with either engine; the bass note comes from the low-register CQT with the DSP and from lv-chordia's bass head with the model, and a weak bass outside the chord is shown at root position, not as a measured note. The JSON records which engine heard the chords.

`analyze` refuses to overwrite an existing output unless you pass `--force`. An input with no detectable beats is reported as an error, not written as an empty timeline. The JSON format is described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#the-chord-timeline-json).

### The model engine (optional)

```sh
uv sync --extra model
```

This adds lv-chordia, the chord recognizer of Jiang, Chen, Li and Xia (ISMIR 2019), and torch. On macOS the environment grows by about 630 MB, 542 MB of it torch. On an Apple M4 the model engine takes 6.3 to 6.8 s per minute of audio and peaks at 2.36 GB of RAM on a 3-minute song and 3.17 GB on a 6-minute one, against the DSP's 3.1 to 3.3 s per minute and 1.00 and 1.77 GB. The weights, five files of about 5.7 MB, come inside the lv-chordia wheel, so nothing is downloaded at run time. The model runs on the CPU even when torch sees a GPU, and it reads the audio chordotomy has already decoded, so your audio stays on your machine. It scores above the DSP on both evaluation datasets; the numbers are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#model-engine).

On Linux, uv takes torch from the PyTorch CPU index, as `pyproject.toml` sets it up, rather than PyPI's build with CUDA. With pip, add `--extra-index-url https://download.pytorch.org/whl/cpu` to the install command. Python 3.13 dropped the `audioop` module that pydub, one of lv-chordia's dependencies, needs; the extra includes `audioop-lts` in its place.

The weights are MIT, like lv-chordia's code. lv-chordia's authors trained them on 1217 songs from Isophonics, Billboard, RWC-Pop and USPOP, public chord annotations over commercial recordings. If you would rather not use a model trained that way, leave the extra out, and the DSP front end recognizes the chords.

### Explanations in Claude Code

The repo is also a Claude Code plugin with one skill, `explain-harmony`. Install it once:

```text
/plugin marketplace add zeikar/chordotomy
/plugin install chordotomy@chordotomy
```

Then ask something like "explain the harmony of song.mp3". The skill runs `chordotomy analyze` locally with the plugin's own copy (it needs uv), reads the JSON, and explains the secondary dominants, borrowed chords, and bass lines. The audio stays on your machine; Claude reads only the chord timeline.

Working in this repo, `.claude/settings.json` registers the checkout itself as a directory marketplace and enables the plugin, so the skill runs from the working tree. The first session asks you to trust it; `claude plugin marketplace add .` does the same by hand.

## Viewer

The viewer plays a recording along with its chord timeline. It shows the current chord, its Roman numeral with figured bass, its role and bass note, and the other chords the analyzer heard, ranked. Chords are colored by role, so secondary dominants and borrowed chords stand out. Every beat gets the same width, so a chord's width is its length in beats; where the beats come faster or slower, the seconds on the ruler bunch up or spread out instead. The header names the engine that heard the chords (lv-chordia or the DSP).

Open it at <https://zeikar.github.io/chordotomy/>, or open `viewer/index.html` from a checkout. Drop the recording and its `.chords.json` on the page, or pick them with **Open files**. The files stay in your browser. The page reads them locally and makes no network requests.

To check the chords by ear, turn on **Play chords**. The page plays each detected chord on every beat, with its bass note, under the recording. **Mute recording** leaves the chords on their own. The sound is synthesized in the browser.

Space plays and pauses. → goes to the next chord. ← goes back to the start of the current chord, or to the chord before when it is already within a second of the start, so pressing it twice steps back. C turns the chords on and off, M mutes the recording, and clicking a chord jumps to it.

### Editing

The editor acts on the current chord. While you pick, it stays on that chord, even if playback moves on. **Root**, **Quality** and **Bass** set the chord and its bass note, and a pick applies at once. The chords the analyzer also heard are buttons: one click makes one of them the chord. **Split at beat** cuts the chord at the beat under the playhead. **Merge ←** and **Merge →** join it with the chord before or after, keeping its own chord and bass. **Delete** removes it, and a neighbour takes its beats. **Undo** and **Redo** step through the edits. The select under **Key** fixes the key, and **Estimated** goes back to the estimate. After every edit the page works out the key, numerals and roles again, as `chordotomy analyze` does, and marks the chords you changed.

Chords start and end on the analyzer's beats. To enter a chord it missed, split where the chord starts and pick it; over silence, one pick enters a chord. There is no entering a progression from scratch: the beat grid comes from `chordotomy analyze`, so a timeline needs a recording's analysis first.

**Save edited JSON** downloads the timeline with your edits, named after the recording it came from: `song.mp3`'s `song.chords.json` saves as `song.edited.chords.json`, wherever your browser puts downloads. The opened file is never changed. Put the saved file next to the recording, and the `explain-harmony` skill reads it in place of the analyzer's. Until you save, the page shows **Unsaved edits** and asks before it closes or opens another timeline.

S splits at the beat under the playhead, and Shift+← and Shift+→ step back or forward a beat to get there. Delete or Backspace deletes the chord. Ctrl+Z (⌘Z on a Mac) undoes, and Ctrl+Shift+Z (⌘⇧Z) or Ctrl+Y redoes. Held down, these keys act once. While a select has focus, keys go to it, not to the shortcuts.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync --extra dev
uv run chordotomy --version
uv run pytest
uv run ruff check . && uv run ruff format --check .
node --test viewer/tests/
```

The model tests need the extra and skip without it; the rest of the suite runs the DSP either way. `uv sync` installs exactly the extras it is given, so name every one you want, as in `uv sync --extra dev --extra model`.

The viewer is plain HTML, CSS, and JavaScript with no build step. Its tests need Node and no packages.

The viewer re-analyzes edited chords with a JavaScript port of the Python harmonic analysis, and `tests/harmony_vectors.json` pins the port to it. After changing the analysis in Python, regenerate that file; pytest fails until you do:

```sh
uv run python tests/harmony_vectors.py
```

### Real-audio evaluation (opt-in)

`uv sync --extra dev --extra eval` adds mir_eval and pooch, which also enables the evaluation tests (skipped without it). Then:

```sh
uv run chordotomy evaluate tiny-aam [--limit N]
uv run chordotomy evaluate guitarset [--limit N]
```

Tiny AAM downloads 168 MB. GuitarSet downloads 39 MB of annotations plus 657 MB of audio, of which only the accompaniment takes being scored are extracted. `--engine` works as for `analyze`, so with the model installed the scores are the model's unless you pass `--engine dsp`. Both datasets are CC BY 4.0. In a checkout they land in `datasets/`, which is gitignored; delete it to re-download. The default test run never touches the network. Besides the chord scores, the table scores the beat grid against the annotated beats, and the `N` calls against the reference's `N`, and the bass with four more columns (`bass_ref`, `inv_prec`, `inv_rec` and `nonchord`); [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#evaluation) explains each column. The scores are numbers for development only.

## License

MIT
