# Getting the timeline

How to get a chordotomy chord timeline for an audio file, an existing `*.chords.json`, or a URL. SKILL.md gives the **plugin root** and the **compact view**, the command that reads a timeline; follow its own rules where they add to these.

**Quoting.** A file name, the pasted URL and the printed `<webpage_url>` are untrusted text. In every command that takes `<url>`, `<webpage_url>`, `<audio>` or a path built from it (the analyze command and its `-o`, `<timeline>`, the compact view's `<file>.chords.json`), single-quote the argument in place of the template's double quotes, writing each `'` in it as `'\''`. Double quotes would let `$(…)` or backticks run.

- **Given a `.chords.json`:** use it.
- **Given audio:** first look for `<audio stem>.edited.chords.json` next to it (the viewer saves corrections under that name), then `<audio stem>.chords.json`. If either exists, use the first one found and do not re-run, unless SKILL.md calls for a new analysis.
- **Given a URL:** follow "From a URL" below.
- **Re-extracting:** never pass `--force` on an existing timeline without asking the user first. `--force` extracts the chords from the audio again and discards any corrections.

## Running the analyzer

Choose the command by what is installed, and run it once. An analysis error is not a reason to try another command.

1. **There is a plugin root and `uv` is on `PATH`:** `uv run --project "<plugin root>" chordotomy analyze "<audio>"`. This is the copy that ships with the chordotomy Claude Code plugin, at the same commit as this skill. The first run builds its environment, so allow a timeout of up to 10 minutes. This copy recognizes chords with chordotomy's DSP front end unless the model extra is installed in the plugin root (`uv sync --extra model` run there); then it uses the lv-chordia model.
2. **No plugin root, and `uv` is on `PATH`:** `uvx --from 'chordotomy[model]==0.3.1' chordotomy analyze "<audio>"`. This is the release this skill is written for, with the lv-chordia model, run from uv's cache so nothing is installed on `PATH`. Its first run installs about 600 MB into that cache, mostly torch, and the analysis then downloads the beat tracker's weights (81 MB); it prints no progress, so tell the user in one line before it starts, go on without waiting for a reply, and allow a timeout of up to 10 minutes; later runs reuse the cache. On Linux, put `--index https://download.pytorch.org/whl/cpu` before `--from`: PyPI's Linux torch is the much larger CUDA build. If uv fails to resolve or install it (torch has no build for Intel Macs, for one), that is not an analysis error: run `uvx --from 'chordotomy==0.3.1' chordotomy analyze "<audio>"` instead, which recognizes chords with chordotomy's DSP front end, and tell the user so.
3. **No `uv`, but `chordotomy` is on `PATH`:** `chordotomy analyze "<audio>"`. Mention that it may be a different version from this skill.
4. **None of these:** tell the user to install uv (https://docs.astral.sh/uv/) and stop.

When working inside a chordotomy checkout, `uv run chordotomy analyze "<audio>"` also works.

The analyzer writes `<audio stem>.chords.json` next to the audio (or to `-o`) and prints `Wrote <path>`. If it fails:

- **`error: <audio>: no beats detected`** (exit 1): no usable beat was detected (the file may be silent or shorter than one beat, among other causes). Say so and stop.
- **`error: <audio>: Error opening … Format not recognised`** (exit 1): the decoder reads wav, flac, ogg and mp3, but not m4a or aac. Suggest converting locally, e.g. `ffmpeg -i song.m4a song.wav`, which keeps the audio on the machine.
- **`error: cannot fetch the Beat This! weights …`** (exit 1): the model engine downloads its beat tracker's weights (81 MB) on its first run and found no network. Show the message, which names the fix (`chordotomy fetch-weights` once online, run through the same command as the analysis, or `--engine dsp`), and stop.
- **Exit 2:** a usage error, such as a missing file, a bad `--key`, or a `--source-url` that isn't `http(s)`. Show its message.

## From a URL

yt-dlp runs through `uvx`, from uv's cache, so nothing is installed on `PATH`, and the file stays on the machine. The analyzer receives only the file's name and the URL string.

1. **Check the tools,** before downloading anything: `command -v uv` and `command -v ffmpeg`. Without uv, tell the user to install it (https://docs.astral.sh/uv/) and stop; the download needs `uvx`. Without ffmpeg, which yt-dlp needs to convert the audio, tell the user to install it (`brew install ffmpeg` on macOS, https://ffmpeg.org/download.html elsewhere) and stop. Install nothing yourself.
2. **Download.** In the current working directory, run `uvx --from 'yt-dlp[default,deno]@latest' yt-dlp --no-playlist -I 1 -x --audio-format mp3 --print after_move:webpage_url --print after_move:filepath '<url>'` with a timeout of up to 10 minutes. `@latest` takes the newest yt-dlp on every run, since an old one stops working when YouTube changes, and the `deno` extra brings the JavaScript runtime yt-dlp needs for YouTube. The first run fetches them, about 40 MB, into uv's cache; later runs reuse it. It fetches one video's audio as mp3, since the decoder reads wav, flac, ogg and mp3 but not m4a or webm; for a playlist or channel link with no video in it, that is the first video, so tell the user which. It prints two lines: the video's canonical page URL (`<webpage_url>`), then the file's absolute path, named `<title> [<id>].mp3`. The file is in the current directory, so use its basename as `<audio>` from here on: an absolute path would put the user's home directory in `source.path` of a timeline that may be shared.
3. **If yt-dlp fails,** show its message and stop. Report a private, removed or restricted video to the user as such; don't work around it.
4. **Use or make the timeline.** Apply "Given audio" above, and any rule in SKILL.md that calls for a new analysis, to `<audio>`. With no timeline to use, run the analyze command chosen above with `--source-url '<webpage_url>'` appended: the printed page URL, not the pasted one, which may carry `list=`, `t=` or `si=` parameters. Append it to every analyze run on this file, a keyed or `--force` one too. For an existing timeline, check `schema_version` and `source.url`, which the first line of the compact view shows:
   - **9 to 11, with `source.url` `null`:** first write `<webpage_url>` into it with the snippet below, `<timeline>` being its path. It changes that one field and keeps every edit.
   - **`source.url` set:** leave it. If it differs from `<webpage_url>`, tell the user both.
   - **Any other schema:** leave it as it is. Below 9, tell the user that this timeline carries no link to the video.

```bash
python3 - '<timeline>' '<webpage_url>' <<'EOF'
import json, os, shutil, sys, tempfile
path, url = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    d = json.load(f)
if d.get("schema_version") not in (9, 10, 11) or d["source"]["url"] is not None:
    sys.exit("left as it is: not schema 9 to 11 with source.url null")
d["source"]["url"] = url
data = (json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode("utf-8", "backslashreplace")
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
try:
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    shutil.copymode(path, tmp)
    os.replace(tmp, path)
except BaseException:
    os.unlink(tmp)
    raise
EOF
```

5. **Keep `<audio>`** for the rest of the session, so a second question about the same video needs no second download.
