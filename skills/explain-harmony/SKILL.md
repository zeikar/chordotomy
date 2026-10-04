---
name: explain-harmony
description: This skill should be used when the user wants the harmony of a recording, a YouTube (or other yt-dlp-supported) link, or a chordotomy `.chords.json` timeline explained, e.g. "analyze the harmony of song.mp3", "explain the chords in this song", "why does the progression in this track work", "find the secondary dominants / borrowed chords in this recording", "Roman-numeral analysis of this audio file", "explain the harmony of this YouTube video <link>", "analyze the chords of https://youtu.be/…", "이 곡 화성 분석해줘", "이 노래 코드 진행 설명해줘", "차용화음 / 세컨더리 도미넌트 찾아줘", "이 유튜브 영상 화성 분석해줘". Runs the local chordotomy analyzer and explains the notable moves from its JSON. Not for a progression typed as text with no audio or timeline.
---

# Explain a song's harmony with chordotomy

chordotomy is a local analyzer. It turns a recording into a beat-aligned chord timeline with a key, Roman numerals, secondary dominants, borrowed chords, and bass notes with inversions. It writes no prose. This skill runs it, reads the JSON, and writes the short explanation of why the highlighted moves work.

Audio never leaves the machine. Run the analyzer locally, and never upload or send the audio anywhere.

## Step 1: Get the timeline

The input is an audio file, an existing `*.chords.json`, or a URL.

- **Given a `.chords.json`:** go to Step 2. If the user also states a key, follow "Analyzing in a stated key"; with no audio next to the timeline, the viewer is the only way to rekey it.
- **Given audio:** first look for `<audio stem>.edited.chords.json` next to it (the viewer saves corrections under that name), then `<audio stem>.chords.json`. If either exists, use the first one found and do not re-run, unless the user states a key (see "Analyzing in a stated key").
- **Given a URL:** follow "From a URL" below.
- **Re-extracting:** never pass `--force` on an existing timeline without asking the user first. `--force` extracts the chords from the audio again and discards any corrections.
- **Analyzing in a stated key:** this takes precedence over reusing an existing timeline. If the user states a key, or asks to re-analyze in another key, and a timeline already exists, check whether the viewer saved it (`<audio stem>.edited.chords.json`) or any segment has `edited: true`. A split or a merge can leave `edited` false, and only the saved name shows it; a copy renamed after only splits or merges looks untouched, and the new file then holds the chords as first extracted, while the copy itself is left as it is. If either holds, do not re-run `--key`, which extracts the chords again and drops the corrections: tell the user to set the key in the viewer's key select and save a copy, which keeps their corrections, then explain from that saved copy, and stop until it exists. If neither does, write to a new file next to the audio that names the key, rather than overwriting, e.g. `--key A:min -o "<audio dir>/<stem>.A-minor.chords.json"`. If that keyed file already exists, use it instead of re-running. `--key` takes `<root>:maj` or `<root>:min`, and flat roots such as `Bb:maj` are accepted.

Choose the command by what is installed, and run it once. An analysis error is not a reason to try another command.

1. `uv` is on `PATH`: `uv run --project "${CLAUDE_PLUGIN_ROOT}" chordotomy analyze "<audio>"`. This is the copy that ships with this plugin, at the same commit as this skill. The first run builds its environment, so allow a timeout of up to 10 minutes. This copy recognizes chords with chordotomy's DSP front end unless the model extra is installed in the plugin root (`uv sync --extra model` run in `${CLAUDE_PLUGIN_ROOT}`); then it uses the lv-chordia model.
2. There is no `uv`, but `chordotomy` is on `PATH`: `chordotomy analyze "<audio>"`. Mention that it may be a different version from this skill.
3. Neither is installed: tell the user to install uv (https://docs.astral.sh/uv/) and stop.

When working inside a chordotomy checkout, `uv run chordotomy analyze "<audio>"` also works.

The analyzer writes `<audio stem>.chords.json` next to the audio (or to `-o`) and prints `Wrote <path>`. If it fails:

- **`error: <audio>: no beats detected`** (exit 1): no usable beat was detected (the file may be silent or shorter than one beat, among other causes). Say so and stop.
- **`error: <audio>: Error opening … Format not recognised`** (exit 1): the decoder reads wav, flac, ogg and mp3, but not m4a or aac. Suggest converting locally, e.g. `ffmpeg -i song.m4a song.wav`, which keeps the audio on the machine.
- **`error: cannot fetch the Beat This! weights …`** (exit 1): the model engine downloads its beat tracker's weights (81 MB) on its first run and found no network. Show the message, which names the fix (`chordotomy fetch-weights` once online, or `--engine dsp`), and stop.
- **Exit 2:** a usage error, such as a missing file, a bad `--key`, or a `--source-url` that isn't `http(s)`. Show its message.

### From a URL

yt-dlp runs through `uvx`, from uv's cache, so nothing is installed on `PATH`, and the file stays on the machine. The analyzer receives only the file's name and the URL string.

**Quoting.** The pasted URL, the printed `<webpage_url>`, and a title-derived file name are untrusted text. In every command that takes `<url>`, `<webpage_url>`, `<audio>` or a path built from it (the analyze command and its `-o`, `<timeline>`, Step 2's `<file>.chords.json`), single-quote the argument in place of the template's double quotes, writing each `'` in it as `'\''`. Double quotes would let `$(…)` or backticks run.

1. **Check the tools,** before downloading anything: `command -v uv` and `command -v ffmpeg`. Without uv, tell the user to install it (https://docs.astral.sh/uv/) and stop; the download needs `uvx`. Without ffmpeg, which yt-dlp needs to convert the audio, tell the user to install it (`brew install ffmpeg` on macOS, https://ffmpeg.org/download.html elsewhere) and stop. Install nothing yourself.
2. **Download.** In the current working directory, run `uvx --from 'yt-dlp[default,deno]@latest' yt-dlp --no-playlist -I 1 -x --audio-format mp3 --print after_move:webpage_url --print after_move:filepath '<url>'` with a timeout of up to 10 minutes. `@latest` takes the newest yt-dlp on every run, since an old one stops working when YouTube changes, and the `deno` extra brings the JavaScript runtime yt-dlp needs for YouTube. The first run fetches them, about 40 MB, into uv's cache; later runs reuse it. It fetches one video's audio as mp3, since the decoder reads wav, flac, ogg and mp3 but not m4a or webm; for a playlist or channel link with no video in it, that is the first video, so tell the user which. It prints two lines: the video's canonical page URL (`<webpage_url>`), then the file's absolute path, named `<title> [<id>].mp3`. The file is in the current directory, so use its basename as `<audio>` from here on: an absolute path would put the user's home directory in `source.path` of a timeline that may be shared.
3. **If yt-dlp fails,** show its message and stop. Report a private, removed or restricted video to the user as such; don't work around it.
4. **Use or make the timeline.** Apply Step 1's "Given audio" and "Analyzing in a stated key" rules to `<audio>`. With no timeline to use, run the analyze command chosen above with `--source-url '<webpage_url>'` appended: the printed page URL, not the pasted one, which may carry `list=`, `t=` or `si=` parameters. Append it to every analyze run on this file, a keyed or `--force` one too. For an existing timeline, check `schema_version` and `source.url`, which the first line of Step 2's compact view shows:
   - **9 or 10, with `source.url` `null`:** first write `<webpage_url>` into it with the snippet below, `<timeline>` being its path. It changes that one field and keeps every edit.
   - **`source.url` set:** leave it. If it differs from `<webpage_url>`, tell the user both.
   - **Any other schema:** leave it as it is. Below 9, tell the user that this timeline carries no link to the video.

```bash
python3 - '<timeline>' '<webpage_url>' <<'EOF'
import json, os, shutil, sys, tempfile
path, url = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    d = json.load(f)
if d.get("schema_version") not in (9, 10) or d["source"]["url"] is not None:
    sys.exit("left as it is: not schema 9 or 10 with source.url null")
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

## Step 2: Read the JSON

The file lists every beat, so it is long. A 4-minute song runs past 2,000 lines. Read a compact view instead of the raw file:

```bash
python3 -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); print("schema", d.get("schema_version"), "| generator", json.dumps(d.get("generator"), ensure_ascii=False), "| source", json.dumps(d.get("source"), ensure_ascii=False), "| key", json.dumps(d.get("key"), ensure_ascii=False), "| keys", json.dumps([[d["beats"][r["start_beat"]], r["label"]] for r in d.get("keys") or []], ensure_ascii=False)); [print(json.dumps([s.get(k) for k in ("start_time","end_time","chord","bass","inversion","numeral","role","function","target","edited","candidates")], ensure_ascii=False)) for s in d["segments"]]' "<file>.chords.json"
```

Check `schema_version`. This skill is written for version 10:

- **Below 10:** there is no `keys`; every numeral is relative to the one `key`.
- **Below 9:** there is no `source.url`.
- **Below 8:** there is no `sus4(b7)` and no `7sus4` numeral; an lv-chordia timeline below 8 wrote a 7sus4 as `sus4`.
- **Below 7:** there is no `aug`, `dim` (the triad) or `sus2`, and no `+`, bare `°` or `sus2` numerals; an lv-chordia timeline below 7 wrote a diminished triad as `dim7`, an augmented chord as `maj` and a sus2 as the sus4 a fifth up.
- **Below 6:** there is no `generator.engine`; the chords are the DSP recognizer's.
- **Below 5:** there is no `edited`; every chord is the analyzer's.
- **Below 4:** the chords are only `maj`, `min` and `7`, and the numerals carry no `maj7`, `ø7`, `°7`, `add6` or `sus4`.
- **Below 3:** there is no `bass` and no `inversion`.
- **Below 2:** there is no key and there are no numerals either.
- **Above 10:** this skill may be out of date. Explain only the fields listed here.

In every case other than 10, tell the user that the timeline comes from a different chordotomy version. The field definitions are in `${CLAUDE_PLUGIN_ROOT}/docs/timeline-json.md`.

The fields:

- **`generator.engine`:** the chord recognizer that produced `chord` and `candidates`: `name` (`dsp`, chordotomy's own DSP front end, or `lv-chordia`, a pretrained model) and `version` (chordotomy's version for `dsp`, the lv-chordia package version for `lv-chordia`).
- **`source.url`:** the web page the recording came from, `null` for a local file.
- **`key`:** the whole-song estimate: `label` (`C:maj`, `A:min`), `source` (`estimated` or `given`), and `candidates` (the estimator's ranking, with no scores). `key: null` means the timeline has no chord to estimate a key from; say so. The `edited` flags don't show whether the analyzer found no chords or the user cleared them, so don't say which. With `source: given`, mention when `candidates[0]` differs from the given key.
- **`keys`:** the key regions, contiguous over the beats: `start_beat`, `end_beat`, `label`. The compact view prints each as `[start_time, label]`. One region when `key.source` is `given`; `[]` when `key` is `null`.
- **Per segment:**
  - `start_time`, `end_time`
  - `chord` (a Harte label, always root position), `candidates` (this segment's ranking, `candidates[0] == chord` unless `edited`). Both draw on thirteen qualities: `maj`, `min`, `7`, `maj7`, `min7`, `min6`, `hdim7`, `dim7`, `sus4`, `aug`, `dim`, `sus2` and `sus4(b7)`.
  - `bass`, `inversion`
  - `edited` (`true` when the user corrected `chord` or `bass` in the viewer, or merged a segment over a neighbour with a different one; `candidates` is then only what the analyzer heard, so `candidates[0]` may differ from `chord`)
  - `numeral`, `role` (`diatonic`, `secondary_dominant`, `borrowed` or `chromatic`), `function`, `target`, all relative to the key region that contains the segment. `secondary_dominant` also covers secondary leading-tone chords: numeral `vii°/x`, `vii°7/x` or `viiø7/x`, with `target` set.
- **`N`:** a segment with no chord: silence, or a passage with no clear harmony, such as a drum break.

## Step 3: Pick the moves worth noticing

Consecutive segments can repeat a `chord` when the bass changes under it. Treat such a stretch as one **chord run**, one highlight. The **next chord** after a run is the first following segment whose `chord` differs; `N` counts.

Highlight, in time order:

1. **Every key change,** when `keys` has more than one region: the time, the two keys, and the last chords before and the first after.
2. **Every secondary dominant or leading-tone run (`role: secondary_dominant`), with its next chord.** An `N` next means the chord did not resolve.
3. **Every `borrowed` run.**
4. **Every `chromatic` run.**
5. **Bass lines.** Look for three or more consecutive `bass` values, each 1 or 2 semitones from the last, with no `null` in between. The bass has no octave, so call a line descending or ascending only when every step goes the same way around the pitch-class circle.
6. **Every `non_chord` bass.**
7. **Inversions worth a word.** For example, a second-inversion tonic right before V, or a V7 in third inversion.

Group repeats. When the same run is followed by the same next chord again, explain it once and list where it recurs ("at 0:12, 0:44 and 1:30"). If there is nothing in categories 2–4, say the harmony stays diatonic, and point out the V → I and IV → I motions instead.

A section centred on vi inside one region: no key change was detected, which does not rule out a modulation to the relative key. Describe the vi emphasis (see `references/moves.md`, "Key changes").

## Step 4: Explain each move

Consult **`references/moves.md`** for how to explain each kind of move, including key changes, and read a `non_chord` bass. It also covers resolutions and chains, spelling, and figured-bass numerals.

Rules:

- **Ground every claim in the JSON:** the numeral, role, target, next chord and bass. Music theory explains why those facts work. It never adds facts the JSON does not contain. The analyzer knows nothing about melody, lyrics, instrumentation or phrase boundaries, so claim none of them.
- **Be brief:** one to three sentences per move.
- **Flag shaky labels.** The chords are extracted automatically and can be wrong. When a highlight hinges on one label, and its segment is not `edited`, name that segment's `candidates[1]` (and `[2]`) as the alternative reading, e.g. a borrowed `iv` that could be a misheard `IV`. A candidate on the same notes as `chord` (`A:min6` beside `F#:hdim7`) is a spelling, not an alternative; see `references/moves.md`. Never state percentages or confidence numbers. The candidates are the recognizer's own ranking (the DSP's template scores or the model's), never probabilities.
- **Write chords the way musicians do:** `C:maj` → C, `A:min` → Am, `G:7` → G7, `F:maj7` → Fmaj7, `D:min7` → Dm7, `G:min6` → Gm6, `F#:hdim7` → F♯m7♭5, `C#:dim7` → C♯dim7, `G:sus4` → Gsus4, `C:aug` → Caug, `B:dim` → Bdim, `C:sus2` → Csus2, `A:sus4(b7)` → A7sus4, and `C:maj` over bass `E` → C/E. Respell sharps as the key and numeral require. `A#:maj` is B♭ major, and a `bVII` in C is B♭, not A♯. The spelling rules are in `references/moves.md`.
- **Write times as m:ss** from `start_time`.
- **Answer in the user's language.**

## Step 5: Output

Use this shape, with headings in the user's language:

```
Key: C major (estimated; next in the ranking: G major, F major)
Progression: I – V6 – vi – I64 – IV – I6 – ii – V7 – I

Moves worth noticing
- 0:00–0:14 bass C–B–A–G–F–E–D: …
- 0:08 D7 → G7 (V7/V → V7): …why it works…
- 0:24 Fm (iv, borrowed from C minor): …

(The labels were extracted automatically by <engine>, except the segments the user corrected; <any caveat worth making>.)
```

- **Key line:** the whole-song `key`, as in the shape above. When `keys` has several regions, add a line "Regions: E major → G major (0:47) → …"; `key` need not be the first region's key.
- **Progression line:** the numerals of the chord runs in order, with each segment's inversion figure. Collapse immediate repeats. Mark each key change with the new key and its time in brackets: "… – V7 – I [G major, 0:47] vi – …". Numerals after a mark are relative to the new key. For a long song, show the first 16 and say that it continues.
- **Highlights:** list them in time order.
- **Caveat line:** `<engine>` comes from `generator.engine`: its name and `version` for `lv-chordia` ("extracted automatically by lv-chordia 1.1.0"), and "chordotomy's DSP front end" for `dsp` and for a file below schema 6.

Then offer follow-ups:

- re-analyzing in another key, written to a new file, if the estimate looks wrong;
- explaining any passage in more depth.

## Additional Resources

- **`references/moves.md`:** how to explain each kind of move, spelling, and figured bass.
- **`${CLAUDE_PLUGIN_ROOT}/docs/timeline-json.md`:** the full JSON schema, and how the held bass is decided.
- **`${CLAUDE_PLUGIN_ROOT}/docs/harmony.md`:** the analysis rules (how keys, roles and the secondary-dominant look-ahead are decided).
