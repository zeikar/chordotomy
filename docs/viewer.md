# The viewer

## Using it

The viewer plays a recording along with its chord timeline. It shows the current chord, its Roman numeral with figured bass, its role and bass note, and the other chords the analyzer heard, ranked. The key shown is the one at the playhead, and when the song changes key, the key panel lists each key with the time it starts. Chords are colored by role, so secondary dominants and borrowed chords stand out. Every beat gets the same width, so a chord's width is its length in beats; where the beats come faster or slower, the seconds on the ruler bunch up or spread out instead. The header names the engine that heard the chords (lv-chordia or the DSP).

Open it at <https://zeikar.dev/chordotomy/>, or open `viewer/index.html` from a checkout. Drop the recording and its `.chords.json` on the page, or pick them with **Open files**. The files stay in your browser. The page reads them locally and makes no network requests. Opened without its recording, a timeline still plays, with only the chords sounding. One analyzed with `--source-url` also shows a link to that page, so someone who received only the JSON can find the recording; following the link is a click, not a request the page makes.

To check the chords by ear, turn on **Play chords**. The page plays each detected chord on every beat, with its bass note, under the recording. **Chord volume** sets their level, and **Mute recording** leaves them on their own. The sound is synthesized in the browser.

Space plays and pauses. → goes to the next chord. ← goes back to the start of the current chord, or to the chord before when it is already within a second of the start, so pressing it twice steps back. C turns the chords on and off, M mutes the recording, and clicking a chord jumps to it.

The editor acts on the current chord. While you pick, it stays on that chord, even if playback moves on. **Root**, **Quality** and **Bass** set the chord and its bass note, and a pick applies at once. The chords the analyzer also heard are buttons: one click makes one of them the chord. **Split at beat** cuts the chord at the beat under the playhead. **Merge ←** and **Merge →** join it with the chord before or after, keeping its own chord and bass. **Delete** removes it, and a neighbour takes its beats. **Undo** and **Redo** step through the edits. The select under **Key** fixes one key for the whole song, and **Estimated** goes back to the estimate and its key changes. After every edit the page works out the key regions, numerals and roles again, as `chordotomy analyze` does, and marks the chords you changed.

Chords start and end on the analyzer's beats. To enter a chord it missed, split where the chord starts and pick it; over silence, one pick enters a chord. There is no entering a progression from scratch: the beat grid comes from `chordotomy analyze`, so a timeline needs a recording's analysis first.

**Save edited JSON** downloads the timeline with your edits, named after the recording it came from: `song.mp3`'s `song.chords.json` saves as `song.edited.chords.json`, wherever your browser puts downloads. The opened file is never changed. Put the saved file next to the recording, and the `explain-harmony` skill reads it in place of the analyzer's. Until you save, the page shows **Unsaved edits** and asks before it closes or opens another timeline.

S splits at the beat under the playhead, and Shift+← and Shift+→ step back or forward a beat to get there. Delete or Backspace deletes the chord. Ctrl+Z (⌘Z on a Mac) undoes, and Ctrl+Shift+Z (⌘⇧Z) or Ctrl+Y redoes. Held down, these keys act once. While a select has focus, keys go to it, not to the shortcuts.

## How editing works

The viewer corrects a timeline that `chordotomy analyze` wrote. The editing model is `viewer/edit.js`: pure functions that take a timeline and return a new one, sharing the segments they didn't change. `viewer/app.js` wires them to the page.

An edit acts on the current segment, the one under the playhead. A pick takes a moment, and playback may move on meanwhile. So while one of the Root, Quality and Bass selects has focus, or the pointer is pressed on it, the target is pinned to the segment that was current when that began. Split, Merge and Delete act on the segment that was current when their press began, for the same reason.

There are five operations:

- **Set a chord:** a chord and bass for one segment, from the selects or a candidate. `inversion` follows from the two. `candidates` stay what the analyzer heard, so its other readings stay on offer. Choosing the chord and bass the segment already has is not an edit.
- **Split** at a beat strictly inside a segment. Both halves keep everything the segment had, `edited` included, since neither half's chord changed.
- **Merge** a segment with the one before or after. It keeps its chord, bass and candidates over both spans.
- **Delete** a segment. The one before takes its span, or the next one for the first segment. A lone segment can't be deleted: nothing would take its span, and setting it to `N` silences it.
- **Set the key:** a key fixes it as `--key` does, with `source: given` and one region of that key over the whole song, and Estimated estimates it again from the chords, with the regions the chords give.

An edit never merges neighbours that end up with the same chord. The analyzer writes such neighbours itself when the bass changes under a chord, a split would undo itself before the user could change one half, and the analysis already reads them as one chord run. Merging is explicit.

Boundaries only move onto beats the analyzer found, so the viewer can correct a timeline but not start one. Segment times are read from `beats`, or `source.duration` at the end, as `chordotomy analyze` writes them. Nothing is computed, so an edit adds no rounding.

Every edit ends in a re-analysis. The segments are grouped into chord runs, and `viewer/harmony.js`, the port of ["Harmonic analysis"](harmony.md), estimates the key and the key regions again and recomputes every segment's numeral, role, function and target. The path over the keys is global, so an edit can move or remove a boundary away from the edited chord: after 64 beats of E major's I–V–IV–V, F–C–Bb–C once in two-beat chords and F for 4 are an F region from beat 64, and changing that last F to E takes the region away, and with it the boundary 8 beats before the edited chord. A given key keeps its label and its one region, and only its candidates follow the chords. Diminished and augmented twins are not respelled: a chord the user picks is spelled as picked, and the others keep the analyzer's spelling. Opening a file doesn't re-analyze, so the analyzer's fields stand until the first edit.

Undo keeps whole timelines, not inverse edits. They are small, and each snapshot shares the segments its edit didn't change. Undoing back to the timeline as opened or last saved gives back that very object, which is how the page knows nothing is unsaved. An edit that changes nothing adds no step.

`edited` keeps the provenance: it marks a segment whose chord and bass are the user's, not the analyzer's. The field's row in ["The chord-timeline JSON"](timeline-json.md) says what each operation does to it. The `explain-harmony` skill reads it, so it doesn't present an edited chord's candidates as alternative readings.

Saving downloads the timeline as `<stem>.edited.chords.json`, where `<stem>` is the basename of `source.path` without its extension, so `song.edited.mp3` saves as `song.edited.edited.chords.json`, the name the skill looks for next to the recording. Without a usable `source.path`, `<stem>` is the opened file's name without `.edited.chords.json`, `.chords.json` or `.json`. The file is a `Blob` downloaded through an `<a download>` link, because that works from `file://` in every browser and sends nothing anywhere. The timeline counts as saved once the download starts; if the user cancels a browser's save dialog, the page can't tell.

A batch of dropped or picked files opens whole or not at all, so the recording and the timeline shown are always a pair the user chose together. The timeline is read and validated before anything changes, every field of every segment included, so whatever opens can be drawn and edited. With unsaved edits the viewer asks once before it replaces them, and the browser asks before the page closes. A batch with only a recording replaces the recording and keeps the edits.

A timeline opened without its recording still plays. The player gets a silent WAV as long as `source.duration`, built in the page (`Core.silentWav`, 8-bit mono at 8 kHz, about half a megabyte a minute) and loaded from a `blob:` URL, which the CSP's `media-src blob:` already allows. The playhead, seeking, the rate and the chord sound then run on the player's clock as they do with a recording, so there is no second clock to keep in step with the first. A timeline opened later remakes the stand-in at its own length, unless a recording is open, and a recording opened later replaces it. Play chords turns on with the first stand-in, since the stand-in alone plays nothing; a remade one keeps the user's choice, and a recording that replaces it turns the chords off, as when the recording is opened first. Mute recording is hidden while the stand-in plays. Turned on without the toggle, the chords get their `AudioContext` on the next press of a key or the pointer, since Safari starts one only inside a user gesture and the player's `playing` event comes after it.

Beside the stand-in, the hint to open the recording carries a link to `source.url` when there is one. It is a plain `<a>`, set only when the browser's own URL parser reads the string as `http` or `https` (`Core.isHttpUrl`); anything else leaves the plain hint and no link, and `Edit.upgrade` nulls the field below schema 9. The link opens in a new tab with `rel="noopener noreferrer"`. It is not an embed, so the CSP stays as it is and the page still makes no request of its own; a click is the user's own navigation. Once a recording is open, the hint and its link go.
