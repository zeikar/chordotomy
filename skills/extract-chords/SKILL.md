---
name: extract-chords
description: This skill should be used when the user wants the chords of a recording, a YouTube (or other yt-dlp-supported) link, or a chordotomy `.chords.json` timeline written out or explained, e.g. "what are the chords of song.mp3", "get the chords of this YouTube video <link>", "chord chart for this recording", "what key is this song in", "explain the harmony of song.mp3", "why does the progression in this track work", "find the secondary dominants / borrowed chords in this recording", "Roman-numeral analysis of this audio file". Runs the local chordotomy analyzer, writes out the key and the chords on a timeline, and explains the harmony when asked. Not for a song named without a recording, link or timeline, a progression typed as text, sheet music, or a melody.
---

# Extract and explain a song's chords with chordotomy

chordotomy is a local analyzer. It turns a recording into a beat-aligned chord timeline with a key, Roman numerals, secondary dominants, borrowed chords, and bass notes with inversions. It writes no prose. This skill runs it, reads the JSON, and writes the chords out as a timed chart to play along with, or explains why the notable moves work.

Audio never leaves the machine. Run the analyzer locally, and never upload or send the audio anywhere.

Decide what to write from the request:

- **A chart** (Steps 3 and 4): the default, when the user asks for the chords, the key, or a chord chart.
- **An explanation** (`references/explain.md`, after Step 2): when the user asks about the harmony: why a progression works, Roman numerals, secondary dominants, borrowed chords, key changes, or to analyze or explain the chords.
- **Both,** when asked for both: the chart first.

## Step 1: Get the timeline

Follow **`references/get-timeline.md`**: it reuses an existing timeline, picks and runs the analyzer, and downloads a URL's audio. It needs two things from here:

- **Plugin root:** `${CLAUDE_PLUGIN_ROOT}`. If that is a directory with a `pyproject.toml` in it, this skill runs from the chordotomy Claude Code plugin, and that directory is the plugin's own copy of chordotomy. Otherwise (empty, still a `${…}` placeholder, or no `pyproject.toml` there) there is no plugin root.
- **Compact view:** the command in Step 2.

chordotomy's docs, named below, are in `<plugin root>/docs/` when there is a plugin root, and otherwise at https://github.com/zeikar/chordotomy/tree/main/docs.

**A key the user states.** The key line, the numerals, and with them how the chart spells its roots, all come from the timeline's key, so a stated key needs a timeline analyzed in it. This takes precedence over reusing an existing timeline. If the user states a key, or asks to re-analyze in another key, and a timeline already exists, check whether the viewer saved it (`<audio stem>.edited.chords.json`) or any segment has `edited: true`. A split or a merge can leave `edited` false, and only the saved name shows it; a copy renamed after only splits or merges looks untouched, and the new file then holds the chords as first extracted, while the copy itself is left as it is. If either holds, do not re-run `--key`, which extracts the chords again and drops the corrections: tell the user to set the key in the viewer's key select and save a copy, which keeps their corrections, then work from that saved copy, and stop until it exists. If neither does, write to a new file next to the audio that names the key, rather than overwriting, e.g. `--key A:min -o "<audio dir>/<stem>.A-minor.chords.json"`. If that keyed file already exists, use it instead of re-running. `--key` takes `<root>:maj` or `<root>:min`, and flat roots such as `Bb:maj` are accepted. Given only a `.chords.json` with no audio next to it, the viewer is the only way to rekey it.

## Step 2: Read the JSON

The file lists every beat, so it is long. A 4-minute song runs past 2,000 lines. Read a compact view instead of the raw file:

```bash
python3 -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); print("schema", d.get("schema_version"), "| generator", json.dumps(d.get("generator"), ensure_ascii=False), "| source", json.dumps(d.get("source"), ensure_ascii=False), "| global_key", json.dumps(d.get("global_key", d.get("key")), ensure_ascii=False), "| key_regions", json.dumps([[d["beats"][r["start_beat"]], r["label"]] for r in d.get("key_regions", d.get("keys")) or []], ensure_ascii=False)); [print(json.dumps([s.get(k) for k in ("start_time","end_time","chord","bass","inversion","numeral","role","function","target","edited","candidates")], ensure_ascii=False)) for s in d["segments"]]' "<file>.chords.json"
```

Check `schema_version`. This skill is written for version 11. In any other, tell the user that the timeline comes from a different chordotomy version, and use only the fields it has: an older file lacks some of those below (the compact view prints them as `null`), and a newer one may have fields this skill doesn't know. The field definitions are in chordotomy's `docs/timeline-json.md`.

The fields:

- **`generator.engine`:** the chord recognizer that produced `chord` and `candidates`: `name` (`dsp`, chordotomy's own DSP front end, or `lv-chordia`, a pretrained model) and `version` (chordotomy's version for `dsp`, the lv-chordia package version for `lv-chordia`).
- **`source`:** `path`, the audio, and `url`, the web page the recording came from (`null` for a local file).
- **`global_key`:** the whole-song estimate: `label` (`C:maj`, `A:min`), `source` (`estimated` or `given`), and `candidates` (the estimator's ranking, with no scores). In a song with several key regions it is the key that reads best over all of it, which can differ from every region's. `global_key: null` means the timeline has no chord to estimate a key from; say so. The `edited` flags don't show whether the analyzer found no chords or the user cleared them, so don't say which. With `source: given`, mention when `candidates[0]` differs from the given key.
- **`key_regions`:** the key regions, contiguous over the beats: `start_beat`, `end_beat`, `label`. The compact view prints each as `[start_time, label]`. One region when `global_key.source` is `given`; `[]` when `global_key` is `null`.
- **Per segment:**
  - `start_time`, `end_time`, in seconds.
  - `chord` (a Harte label, always root position), `candidates` (this segment's ranking, best first, with no scores; `candidates[0] == chord` unless `edited`). Both draw on fifteen qualities: `maj`, `min`, `7`, `maj7`, `min7`, `min6`, `hdim7`, `dim7`, `sus4`, `aug`, `dim`, `sus2`, `sus4(b7)`, `maj(9)` and `min(9)`. The last two, the added ninths, come only from a correction in the viewer: no recognizer writes them. Consecutive segments repeat a `chord` when the bass changes under it.
  - `bass`, `inversion`: the held bass note and its place in the chord (`root`, `first`, `second`, `third`, or `non_chord` when it is not a chord tone); `null` when no bass was heard.
  - `edited` (`true` when the user corrected `chord` or `bass` in the viewer, or merged a segment over a neighbour with a different one; `candidates` is then only what the analyzer heard, so `candidates[0]` may differ from `chord`)
  - `numeral`, `role` (`diatonic`, `secondary_dominant`, `borrowed` or `chromatic`), `function`, `target`, all relative to the key region that contains the segment. `secondary_dominant` also covers secondary leading-tone chords: numeral `vii°/x`, `vii°7/x` or `viiø7/x`, with `target` set. A chart uses only `numeral`, to spell the root.
- **`N`:** a segment with no chord: silence, or a passage with no clear harmony, such as a drum break.

For an explanation, go on with **`references/explain.md`**. For a chart, go on here.

## Step 3: Write the chart

- **One symbol per segment.** Spell it as **`references/spelling.md`** says: the quality as a pop chart writes it (`A:min7` → Am7, `F#:hdim7` → F♯m7♭5, `A:sus4(b7)` → A7sus4), the root by its numeral's degree in the segment's key region (a `bVII` in C is B♭, not A♯), and the bass after a slash when `inversion` is not `root` or `null` (`C:maj` over `E` → C/E). Spell a `non_chord` bass as the key spells that note. Write `N` as N.C., but leave it out at the very start and end of the song. Merge neighbours that come out as the same symbol.
- **Lines.** Start each line with the time of its first chord, as m:ss rounded down. Break lines where the progression starts over, so that a progression that comes back lines up with its first appearance; a line usually holds 4 to 8 chords, and N.C. doesn't count toward them.
- **Repeats.** When a line repeats back to back with exactly the same symbols, write it once with its time span and the count: `0:14–0:58  G  D  Em  C  (×4)`. Write out a near repeat (another seventh or bass) in full. A progression that returns later, after something else, is written again where it returns, so the chart reads top to bottom like the song.
- **Key changes.** Before the first line of a new key region, write the new key and its time: `[A major, 1:12]`.
- **Only what the timeline holds.** It has beats but no downbeats, so draw no bar lines and name no time signature. The analyzer doesn't find sections, so don't label a verse or a chorus. It knows nothing of the melody, lyrics or rhythm, so write no strumming pattern, fingering or tab.
- **Answer in the user's language.**

## Step 4: Output the chart

Use this shape, with headings in the user's language:

```
Key: G major (estimated; next in the ranking: E minor, D major)

0:00         G  D/F♯  Em  C
0:14–0:58    G  D  Em  C  (×4)
0:58         Am  C  D  D7sus4
[A major, 1:12]
1:12         A  E  F♯m  D
…

(Extracted automatically by <engine>; <corrections>. Check by ear before you rely on it.)
```

- **Key line:** `global_key`, spelled, with its ranking. When `key_regions` has several regions, add a line "Regions: G major → A major (1:12) → …"; `global_key` need not be any region's key. With `source: given`, say the key was given.
- **Caveat line:** `<engine>` comes from `generator.engine`: its name and `version` for `lv-chordia` ("lv-chordia 1.1.0"), and "chordotomy's DSP front end" for `dsp` and for a file below schema 6. `<corrections>`: when any segment is `edited`, "except the chords you corrected"; otherwise leave it out.
- **The timeline:** name the `.chords.json` path. chordotomy's viewer at https://zeikar.dev/chordotomy/ plays the recording with these chords and lets the user correct them; they drop the audio and the `.chords.json` on the page, and the files stay in their browser.

Then offer follow-ups:

- the alternatives for any chord they doubt: that segment's `candidates`, spelled, as a ranked list. Never state percentages or confidence numbers; the candidates carry none. A candidate on the same notes as the chord (Am6 beside F♯m7♭5, or the dim7s a minor third apart) is the same sound spelled from another root, not a different reading;
- an explanation of the harmony: why the progression works, its secondary dominants and borrowed chords.

## Additional Resources

- **`references/get-timeline.md`:** getting the timeline, from audio or a URL.
- **`references/spelling.md`:** spelling keys, chord symbols, roots and basses.
- **`references/explain.md`:** explaining the harmony: which moves to pick, and the output.
- **`references/moves.md`:** how to explain each kind of move, and figured bass.
- **chordotomy's `docs/timeline-json.md`** (see Step 1): the full JSON schema, and how the held bass is decided.
- **chordotomy's `docs/harmony.md`:** the analysis rules (how keys, roles and the secondary-dominant look-ahead are decided).
