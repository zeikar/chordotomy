# Explaining the harmony

How to explain a timeline's harmony once SKILL.md has read it (its Step 2 lists the fields). `moves.md`, next to this file, says how to explain each kind of move; `spelling.md` says how to spell keys and chords.

## Pick the moves worth noticing

Consecutive segments can repeat a `chord` when the bass changes under it. Treat such a stretch as one **chord run**, one highlight. The **next chord** after a run is the first following segment whose `chord` differs; `N` counts.

Highlight, in time order:

1. **Every key change,** when `key_regions` has more than one region: the time, the two keys, and the last chords before and the first after.
2. **Every secondary dominant or leading-tone run (`role: secondary_dominant`), with its next chord.** An `N` next means the chord did not resolve.
3. **Every `borrowed` run.**
4. **Every `chromatic` run.**
5. **Bass lines.** Look for three or more consecutive `bass` values, each 1 or 2 semitones from the last, with no `null` in between. The bass has no octave, so call a line descending or ascending only when every step goes the same way around the pitch-class circle.
6. **Every `non_chord` bass.**
7. **Inversions worth a word.** For example, a second-inversion tonic right before V, or a V7 in third inversion.

Group repeats. When the same run is followed by the same next chord again, explain it once and list where it recurs ("at 0:12, 0:44 and 1:30"). If there is nothing in categories 2–4, say the harmony stays diatonic, and point out the V → I and IV → I motions instead.

A section centred on vi inside one region: no key change was detected, which does not rule out a modulation to the relative key. Describe the vi emphasis (see `moves.md`, "Key changes").

## Explain each move

Consult **`moves.md`** for how to explain each kind of move, including key changes, and read a `non_chord` bass. It also covers resolutions and chains, and figured-bass numerals.

Rules:

- **Ground every claim in the JSON:** the numeral, role, target, next chord and bass. Music theory explains why those facts work. It never adds facts the JSON does not contain. The analyzer knows nothing about melody, lyrics, instrumentation or phrase boundaries, so claim none of them.
- **Be brief:** one to three sentences per move.
- **Flag shaky labels.** The chords are extracted automatically and can be wrong. When a highlight hinges on one label, and its segment is not `edited`, name that segment's `candidates[1]` (and `[2]`) as the alternative reading, e.g. a borrowed `iv` that could be a misheard `IV`. A candidate on the same notes as `chord` (`A:min6` beside `F#:hdim7`) is a spelling, not an alternative; see `moves.md`. Never state percentages or confidence numbers. The candidates are the recognizer's own ranking (the DSP's template scores or the model's), never probabilities.
- **Write chords the way musicians do:** `C:maj` → C, `A:min` → Am, `G:7` → G7, `F:maj7` → Fmaj7, `D:min7` → Dm7, `G:min6` → Gm6, `F#:hdim7` → F♯m7♭5, `C#:dim7` → C♯dim7, `G:sus4` → Gsus4, `C:aug` → Caug, `B:dim` → Bdim, `C:sus2` → Csus2, `A:sus4(b7)` → A7sus4, `C:maj(9)` → Cadd9, `A:min(9)` → Amadd9, and `C:maj` over bass `E` → C/E. Respell sharps as the key and numeral require. `A#:maj` is B♭ major, and a `bVII` in C is B♭, not A♯. The spelling rules are in `spelling.md`.
- **Write times as m:ss** from `start_time`.
- **Answer in the user's language.**

## Output

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

- **Key line:** the whole-song `global_key`, as in the shape above. When `key_regions` has several regions, add a line "Regions: E major → G major (0:47) → …"; `global_key` need not be any region's key.
- **Progression line:** the numerals of the chord runs in order, with each segment's inversion figure. Collapse immediate repeats. Mark each key change with the new key and its time in brackets: "… – V7 – I [G major, 0:47] vi – …". Numerals after a mark are relative to the new key. For a long song, show the first 16 and say that it continues.
- **Highlights:** list them in time order.
- **Caveat line:** `<engine>` comes from `generator.engine`: its name and `version` for `lv-chordia` ("extracted automatically by lv-chordia 1.1.0"), and "chordotomy's DSP front end" for `dsp` and for a file below schema 6.

Then offer follow-ups:

- re-analyzing in another key, written to a new file, if the estimate looks wrong (SKILL.md, "A key the user states");
- explaining any passage in more depth.
