# Installing

```sh
uv tool install "chordotomy[model]"   # with the lv-chordia model (recommended)
uv tool install chordotomy            # the DSP engine only; pipx install and pip install work too
```

Without `[model]` you get the DSP engine only. With it, `--engine auto`, the default, uses the model engine. In a checkout, `uv sync --extra model` installs it.

## The model engine

The `model` extra adds lv-chordia, Beat This! and torch. On macOS the environment grows by about 600 MB, 526 MB of it torch; beat-this and the packages it brings add a few MB. On an Apple M4 the model engine takes 4.4 to 4.6 s per minute of audio and peaks at 2.59 GB of RAM on a 3-minute song and 3.37 GB on a 6-minute one, against the DSP's 2.2 to 2.3 s per minute and 1.02 and 1.77 GB, measured in one session. Both models run on the CPU even when torch sees a GPU, and both read the audio chordotomy has already decoded.

lv-chordia's weights, five files of about 5.7 MB each, come inside its wheel. Beat This! (Foscarin, Schlüter and Widmer, ISMIR 2024) tracks the model engine's beats. Its `final0` weights, 81 MB and MIT, are downloaded on the first run from the authors' server to `~/.cache/chordotomy` (`$XDG_CACHE_HOME/chordotomy` when set) and kept there. They are checked against a pinned SHA-256 on every load, and a file that fails the check is replaced. `chordotomy fetch-weights` downloads them ahead of time. Without network and without the file, `analyze` stops with an error that names the URL, the cache path, `chordotomy fetch-weights` and `--engine dsp`; it never falls back to librosa's beats. The download is a plain request for a fixed URL and carries nothing about your audio, which stays on your machine. ["The model engine"](recognition.md#the-model-engine) has how it works.

On Linux, PyPI's torch is the build with CUDA. For the CPU build, add `--index https://download.pytorch.org/whl/cpu` to `uv tool install`, or `--extra-index-url https://download.pytorch.org/whl/cpu` to `pip install`; in a checkout, `uv sync` already takes it from there, as `pyproject.toml` sets it up. Python 3.13 dropped the `audioop` module that pydub, one of lv-chordia's dependencies, needs; the extra includes `audioop-lts` in its place.

## Training data

lv-chordia on PyPI is Open MIR Lab's packaging of the authors' original code and weights, which it ships unchanged. The weights are MIT, like the code. lv-chordia's authors trained them on 1217 songs from Isophonics, Billboard, RWC-Pop and USPOP, public chord annotations over commercial recordings. Beat This!'s authors trained `final0` on 15 beat-annotated datasets, all of theirs but GTZAN, which they kept for testing: ASAP, Ballroom, Beatles, Candombe, Filosax, Groove MIDI, GuitarSet, Hainsworth, Harmonix, HJDB, JAAH, RWC, SIMAC, SMC and TapCorrect. GuitarSet's accompaniment takes, which chordotomy is scored on, are among them; [Evaluation](evaluation.md#other-chord-recognizers) accounts for that. Their README notes that some of the training files are fully copyrighted or under limited Creative Commons licenses, and leaves it to the user to judge whether that matters for their use. If you would rather not use models trained that way, leave the extra out: the DSP front end recognizes the chords, and librosa tracks the beats.
