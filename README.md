# chordotomy

[![PyPI](https://img.shields.io/pypi/v/chordotomy.svg)](https://pypi.org/project/chordotomy/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/zeikar/chordotomy/blob/main/LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)
[![Viewer](https://img.shields.io/badge/viewer-zeikar.dev%2Fchordotomy-5b4bb7.svg)](https://zeikar.dev/chordotomy/)

Dissect a song's harmony. Give it a recording (mp3, wav, flac or ogg) and it recognizes the chords on the beat, finds the key and its changes, labels the chords with Roman numerals, and points out the moves worth noticing (the secondary dominant, the borrowed chord). In Claude Code, a skill adds a short note on why each one works.

It analyzes; it doesn't transcribe. There is no staff notation, on purpose.

Yes, chordotomy is also a spinal surgery. This one cuts chords.

Everything runs locally. Your audio never leaves your machine.

![The chordotomy viewer: a borrowed Fm (iv) in C major, with its role, bass and alternatives, the key, the editor, and a chord strip colored by role](https://raw.githubusercontent.com/zeikar/chordotomy/main/docs/images/viewer.png)

*The viewer on a synthesized progression in C major, analyzed with `--engine dsp`. The current chord is a borrowed Fm (`iv`); earlier, E7/G♯ is the secondary dominant of Am (`V⁶₅/vi`).*

## What it does

- **Chords on the beat.** Major, minor, dominant 7th, major 7th, minor 7th, half-diminished 7th, diminished 7th, sus4, 7sus4, augmented, diminished triad, sus2 and minor 6th, with `N` for no chord. The model calls all of them but minor 6th; the DSP all but sus2 and 7sus4. Corrections can also enter add9 and minor add9, which neither engine calls.
- **Two engines.** The lv-chordia model (Jiang, Chen, Li and Xia, ISMIR 2019) when its optional extra is installed, chordotomy's DSP front end otherwise. The model engine's beats come from Beat This!, the DSP's from librosa, and both share the same harmonic analysis.
- **Key and Roman numerals.** Key changes are found from the chords, and each passage is analyzed in its own key. Secondary dominants, secondary leading-tone chords and borrowed chords are labeled and highlighted; the viewer adds figured bass for inversions.
- **The bass note and inversion** of each chord where a bass is heard, so slash chords (C/E, D/F♯) come out as such. A weak bass outside the chord is shown at root position instead of as a doubtful slash chord.
- **A viewer** that plays the recording with its chords, plays the chords themselves to check them by ear, and lets you correct and enter chords.
- **Explanations in Claude Code** of the highlighted moves, from a recording or a YouTube link, through the `explain-harmony` skill.

## Quick start

```sh
uv tool install "chordotomy[model]"   # with the lv-chordia model (recommended), about 600 MB
chordotomy analyze song.mp3           # writes song.chords.json
```

Then open the [viewer](https://zeikar.dev/chordotomy/) and drop `song.mp3` and `song.chords.json` on the page. Without `[model]`, `uv tool install chordotomy`, `pipx install chordotomy` or `pip install chordotomy` installs the DSP engine only.

## Usage

```sh
chordotomy analyze song.mp3                 # writes song.chords.json
chordotomy analyze song.mp3 -o out.json
chordotomy analyze song.mp3 --key A:min     # analyze the whole song in A minor, with no key changes
chordotomy analyze song.mp3 --engine dsp    # the DSP front end, even with the model installed
chordotomy analyze song.mp3 --source-url https://www.youtube.com/watch?v=…   # record where the recording came from
chordotomy fetch-weights                    # model extra: download and verify Beat This!'s weights once
```

`--key` takes `<root>:maj` or `<root>:min`, flats accepted. `--source-url` only records the page in the JSON; nothing is downloaded. `--engine auto`, the default, takes the lv-chordia model when it is installed and the DSP front end otherwise; a missing or broken model install is an error that names the fix, never a silent fallback. `analyze` overwrites an existing output only with `--force`.

The output, `song.chords.json` (schema 11), lists every beat, the estimated key, the key regions and the chord segments, each analyzed in its region's key. One segment of the screenshot's timeline:

```json
{
  "start_beat": 4,
  "end_beat": 6,
  "start_time": 2.438,
  "end_time": 3.646,
  "chord": "E:7",
  "candidates": ["E:7", "G#:dim", "E:maj"],
  "bass": "G#",
  "inversion": "first",
  "numeral": "V7/vi",
  "role": "secondary_dominant",
  "function": null,
  "target": "vi",
  "edited": false
}
```

Chords are Harte labels, and `candidates` is a ranking, never a percentage. [docs/timeline-json.md](https://github.com/zeikar/chordotomy/blob/main/docs/timeline-json.md) has every field.

### The model engine (optional)

The `model` extra adds lv-chordia, Beat This! and torch, and takes about twice the DSP's time per minute of audio, on the CPU. lv-chordia's weights come inside its wheel; Beat This!'s, 81 MB, are downloaded on the first run and checked against a pinned SHA-256. Both models were trained on commercial recordings: lv-chordia on 1217 songs with public chord annotations (Isophonics, Billboard, RWC-Pop and USPOP), Beat This! on 15 beat-annotated datasets. If you would rather not use models trained that way, leave the extra out. [docs/install.md](https://github.com/zeikar/chordotomy/blob/main/docs/install.md) has the size, speed and memory, the weights' cache, the CPU build of torch on Linux, and the full training data.

## Accuracy

`chordotomy evaluate` scores both engines on two public datasets with mir_eval, weighted by duration, beside other open-source chord recognizers run on the same audio. `root` asks for the right root, `majmin` for the right major or minor triad, and `sevenths` for the right seventh chord too.

| | Tiny AAM root | majmin | sevenths | GuitarSet root | majmin | sevenths |
|---|---|---|---|---|---|---|
| **chordotomy, model engine** | 0.955 | 0.950 | 0.914 | 0.854 | 0.900 | 0.847 |
| lv-chordia, its own output | 0.951 | 0.947 | 0.911 | 0.846 | 0.893 | 0.839 |
| BTC (Park et al., 2019) | 0.931 | 0.920 | 0.880 | 0.809 | 0.864 | 0.775 |
| ChordMini BTC (Phan et al., 2026) | 0.921 | 0.908 | 0.844 | 0.818 | 0.869 | 0.798 |
| ChordMini 2E1D (Phan et al., 2026) | 0.924 | 0.913 | 0.836 | 0.742 | 0.801 | 0.746 |
| crema (McFee and Bello, 2017) | 0.898 | 0.893 | 0.794 | 0.816 | 0.873 | 0.785 |
| **chordotomy, DSP front end** | 0.842 | 0.803 | 0.768 | 0.722 | 0.696 | 0.583 |

Tiny AAM is 20 mixed tracks annotated in major and minor; GuitarSet is 180 solo-guitar accompaniment takes, which Beat This! trained on, so each take is scored with the Beat This! checkpoint that did not. These are numbers for development, not a benchmark claim; [docs/evaluation.md](https://github.com/zeikar/chordotomy/blob/main/docs/evaluation.md) has every column, the versions and settings, and the caveats.

## Viewer

The [viewer](https://zeikar.dev/chordotomy/) plays a recording with its chord timeline: the current chord with its Roman numeral, bass and ranked alternatives, the key at the playhead, and a chord strip colored by role. **Play chords** sounds the detected chords to check them by ear. You can correct chords, enter ones the analyzer missed, and save the edited JSON, which the skill then reads. Drop the recording and its `.chords.json` on the page, or open `viewer/index.html` from a checkout. The files stay in your browser, and the page makes no network requests. [docs/viewer.md](https://github.com/zeikar/chordotomy/blob/main/docs/viewer.md) has the controls and keyboard shortcuts.

## Explanations in Claude Code

The repo is also a Claude Code plugin with one skill, `explain-harmony`. Install it once:

```text
/plugin marketplace add zeikar/chordotomy
/plugin install chordotomy@chordotomy
```

Then ask something like "explain the harmony of song.mp3", or give it a YouTube link. The skill runs `chordotomy analyze` locally with the plugin's own copy (it needs uv; a link also needs ffmpeg, and yt-dlp runs through `uvx`), reads the JSON, and explains the key changes, secondary dominants, borrowed chords and bass lines. The audio stays on your machine; Claude reads only the chord timeline.

## What it won't do

- **Staff notation.** It doesn't produce MusicXML and doesn't work out note-level rhythm.
- **Melody transcription.** It doesn't produce melody → MIDI.
- **Song sections.** It doesn't label intro, verse, or chorus. Key changes are marked from the chords, without section names.

It stops at the chords and what they're doing. [docs/decisions.md](https://github.com/zeikar/chordotomy/blob/main/docs/decisions.md) explains why.

## Roadmap

Everything on the original roadmap works. Known gaps, none scheduled:

- Some slash chords still come out in root position: in one chart check, a C♯7/E♯ read as C♯7 under both engines.
- A chart may name a different chord over the same bass (D/A where the analyzer hears Bm/A); the bass is right, the chord is the recognizer's call.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/zeikar/chordotomy && cd chordotomy
uv sync --extra dev
uv run chordotomy --version
uv run pytest
uv run ruff check . && uv run ruff format --check .
node --test viewer/tests/
```

`uv sync` installs exactly the extras it is given, so name every one you want, as in `uv sync --extra dev --extra model`. The model tests skip without the extra, and those that run Beat This! also without its verified weights (`uv run chordotomy fetch-weights`); the suite never downloads. The viewer is plain HTML, CSS and JavaScript with no build step, and re-analyzes edits with a JavaScript port of the harmonic analysis that `tests/harmony_vectors.json` pins to the Python: after changing the analysis, regenerate it with `uv run python tests/harmony_vectors.py`. In a checkout, `.claude/settings.json` registers the checkout as a plugin marketplace, so the skill runs from the working tree once the first session's trust prompt is accepted; `claude plugin marketplace add .` does the same by hand. [docs/ARCHITECTURE.md](https://github.com/zeikar/chordotomy/blob/main/docs/ARCHITECTURE.md) has the pipeline and links the rest of `docs/`.

The evaluation is opt-in:

```sh
uv sync --extra dev --extra eval
uv run chordotomy evaluate tiny-aam [--limit N] [--cache]
uv run chordotomy evaluate guitarset [--limit N] [--cache]
uv run chordotomy evaluate local work/ [--cache]   # your recordings, each with <name>.chart.txt
```

The datasets are downloaded on demand into the gitignored `datasets/`: 168 MB for Tiny AAM, about 700 MB for GuitarSet. `--cache` keeps the slow stages of each analysis, so a change after them rescores both datasets in seconds. `local` scores your own recordings against chord charts you type in. [docs/evaluation.md](https://github.com/zeikar/chordotomy/blob/main/docs/evaluation.md) has the chart format and what each column measures.

## Acknowledgements

- The model engine is the work of Junyan Jiang, Ke Chen, Wei Li and Gus Xia, ["Large-Vocabulary Chord Transcription via Chord Structure Decomposition"](https://archives.ismir.net/ismir2019/paper/000078.pdf), ISMIR 2019, with its [original code and weights](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition) (MIT), as packaged for PyPI by [Open MIR Lab](https://github.com/openmirlab/lv-chordia) (`lv-chordia`, MIT).
- The model engine's beats come from Beat This!, the work of Francesco Foscarin, Jan Schlüter and Gerhard Widmer, ["Beat this! Accurate beat tracking without DBN postprocessing"](https://arxiv.org/abs/2407.21658), ISMIR 2024, with its [code and weights](https://github.com/CPJKU/beat_this) (MIT).
- [librosa](https://librosa.org/) for the audio front end and beat tracking (the DSP engine's beats, and the one-tempo dynamic programming that places the model engine's on Beat This!'s activation), and [mir_eval](https://github.com/mir-evaluation/mir_eval) for scoring.
- The DSP front end's chroma whitening follows Matthias Mauch and Simon Dixon's 2010 chord recognition paper, implemented from the paper.
- Evaluation data: [Tiny AAM](https://zenodo.org/records/6771120) and [GuitarSet](https://zenodo.org/records/3371780), both CC BY 4.0.

## License

[MIT](https://github.com/zeikar/chordotomy/blob/main/LICENSE)
