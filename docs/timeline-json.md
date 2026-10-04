# The chord-timeline JSON

This is the project's public seam. It carries beat positions, not just seconds, so another tool, or a notation stage someone else builds, can consume it. `chordotomy analyze` writes it as schema version 10.

| field | type | meaning |
| --- | --- | --- |
| `schema_version` | int, `10` | schema version of this file |
| `generator.name` | `"chordotomy"` | |
| `generator.version` | str | the chordotomy version that wrote the file |
| `generator.engine.name` | `"dsp"` or `"lv-chordia"` | the recognizer that produced `chord` and `candidates`: chordotomy's DSP front end, or the lv-chordia model |
| `generator.engine.version` | str | chordotomy's version for `dsp`, the lv-chordia package version otherwise |
| `source.path` | str | the audio path as given on the command line |
| `source.duration` | float, seconds, 3 decimals | |
| `source.url` | str or null | an `http://` or `https://` page the recording came from, as given to `--source-url`, which refuses only another scheme, a missing host, whitespace or control characters and what `urlsplit` can't parse (the `explain-harmony` skill passes the canonical page URL of a video it downloaded); `null` when none was given; the analyzer never fetches it; the viewer shows it as a link when the browser can parse it as http(s) |
| `beats` | list of float seconds, 3 decimals, ascending | beat index = list position |
| `key` | object or `null` | the whole song's key; `null` only when the timeline has no chord and no `--key` was given |
| `key.label` | str | `<root>:maj` or `<root>:min`, sharps only, e.g. `C:maj`, `A:min` |
| `key.source` | `"estimated"` or `"given"` | `given` when `--key` was passed or the user chose the key in the viewer |
| `key.candidates` | list of up to 3 str | the estimator's ranking, best first, no scores; `candidates[0] == label` when `source` is `estimated`; `[]` when the timeline has no chord |
| `keys` | list of objects | the key regions, in order: contiguous, the first `start_beat` 0 and the last `end_beat` `len(beats)`; every region starts where a segment starts, so a segment lies in one region; `[]` exactly when `key` is `null` |
| `keys[].start_beat` | int | inclusive |
| `keys[].end_beat` | int | exclusive; the next region's `start_beat`, or `len(beats)` for the last |
| `keys[].label` | str | the region's key, `<root>:maj` or `<root>:min`, sharps only; when `key.source` is `given`, `keys` holds exactly one region, labelled `key.label`; when it is `estimated`, the estimator's top key over the region's chords, so a lone region is labelled `key.label` too |
| `segments[].start_beat` | int | inclusive |
| `segments[].end_beat` | int | exclusive; may equal `len(beats)`, meaning the segment runs to the end of the audio |
| `segments[].start_time` | float | `beats[start_beat]` |
| `segments[].end_time` | float | `beats[end_beat]`, or `source.duration` when `end_beat == len(beats)` |
| `segments[].chord` | str | Harte label or `N`; always the root-position label; consecutive segments may repeat it when the bass changes under one chord |
| `segments[].candidates` | list of 3 str | best first by the recognizer's own scores over the segment, which aren't written; `candidates[0] == chord` when `edited` is false, and the analyzer's ranking for the span the segment came from when it is true; when a diminished or augmented chord was respelled by where it leads, `candidates[1]` is the recognizer's label for the same notes |
| `segments[].bass` | str or `null` | the segment's held bass, sharps only (`C` to `B`): the per-beat bass (on the DSP engine the lowest note sounding in the bass register; on the model engine the bass lv-chordia's bass head hears) that holds for at least 2 beats under the chord; when no value holds that long (a one-beat chord, a bass moving every beat), the most frequent per-beat value, silence included, ties to a tone of the segment's chord, then a note, then the earliest; a bass move shorter than 2 beats under an unchanged chord (a passing tone, an alternating C–E or C–G accompaniment) is not reported; a per-beat bass outside the chord that is judged unreliable (on the DSP, under `NONCHORD_SALIENCE` of the register's loudest note; on the model, under `BASS_SUPPORT` in the head) is replaced by the chord's root before the hold and the vote, so a root bass may be that fallback and not a measured note (when `resolve_twins` respells a chord, an inferred bass moves to the new chord's root); `null` for `N`, when no beat has a note in the bass register (DSP), and when the head hears no bass and the register is silent (model) |
| `segments[].inversion` | `"root"`, `"first"`, `"second"`, `"third"`, `"non_chord"`, or `null` | `chord` over `bass`, by the bass's place among the chord's tones from the root up: `root`; `first`, the third, the fourth of a `sus4` or `sus4(b7)` or the second of a `sus2`; `second`, the fifth; `third`, the seventh of a `7`, `maj7`, `min7`, `hdim7`, `dim7` or `sus4(b7)`, or the added sixth of a `min6`; `non_chord` when it is not a chord tone; `null` whenever `bass` is `null` |
| `segments[].numeral` | str or `null` | Roman numeral of the root-position chord relative to the key region containing the segment, `<accidental><roman><suffix>[/<target>]` (grammar in ["Harmonic analysis"](harmony.md)), e.g. `bVII`, `ii7`, `IVmaj7`, `#i°7`, `vii°`, `V+`, `V7sus4`, `viiø7/V`; `ø` and `°` are written as characters; `null` for `N` |
| `segments[].role` | `"diatonic"`, `"secondary_dominant"`, `"borrowed"`, `"chromatic"`, or `null` | the chord's role, relative to the key region containing the segment; `secondary_dominant` includes secondary leading-tone chords; `null` for `N` |
| `segments[].function` | `"tonic"`, `"predominant"`, `"dominant"`, or `null` | harmonic function, relative to the key region containing the segment; set only for `diatonic` chords |
| `segments[].target` | str or `null` | for `secondary_dominant`, the numeral of the chord it tonicizes, relative to the key region containing the segment (`V7/V` → `V`, `vii°7/ii` → `ii`); `null` otherwise |
| `segments[].edited` | bool | `false`: `chord` and `bass` are the analyzer's. `true`: the user set them in the viewer, either by choosing a chord or bass for this segment other than the one it had, or by a merge or removal that extended it over a neighbour with a different chord or bass, a span where the analyzer didn't hear it. A merge of neighbours with the same chord and bass is `true` only if either was; a split gives both halves the segment's flag |

A chord label is `<root>:<quality>` in Harte syntax. The root is one of `C C# D D# E F F# G G# A A# B`, spelled with sharps only, and the quality is one of `maj`, `min`, `7`, `maj7`, `min7`, `min6`, `hdim7`, `dim7`, `sus4`, `aug`, `dim`, `sus2` and `sus4(b7)`. `N` means no chord. A key label is the label of its tonic triad, `<root>:maj` or `<root>:min`, sharps only. `bass` is spelled the same way, as a bare root.

`chord` and `numeral` stay root-position labels. A slash chord is `chord` over `bass`: `C:maj` with bass `E` is C/E. Figured-bass numerals (`I6`, `V65`) are not written, since they follow from `numeral` and `inversion` by a fixed table. A bass move shorter than 2 beats under an unchanged chord is neither reported nor cut on, because it would turn a held chord into a flicker of inversions without changing the harmony. Consecutive segments may repeat a `chord` when the bass changes under it; in v1 and v2 they never did.

Segments are contiguous: each `start_beat` equals the previous `end_beat`, and the first starts at beat 0. Leading and trailing silence is labeled `N`. The only unlabeled span is the sub-beat head between the start of the audio and `beats[0]`, which is shorter than one beat.

The file is UTF-8, and non-ASCII characters are written as themselves rather than as `\u` escapes: the numerals' `ø` and `°`, and a non-ASCII `source.path`. A path that is not valid UTF-8 keeps `\u` escapes for the bytes that don't decode.

The schema is stable. Any change to the documented schema, an added field included, is breaking and bumps `schema_version`. Schema 4 kept schema 3's fields and widened what they hold: the chord qualities, the numerals, what `third` means in `inversion`, which chords `secondary_dominant` covers, and what `candidates[1]` means after a respelling. Schema 5 added `segments[].edited`, so a corrected chord is told apart from a heard one. Schema 6 added `generator.engine`; a file below 6 was written by the DSP. Schema 7 widened the chord vocabulary (`aug`, `dim`, `sus2`) and the numerals (`+`, `°`, `sus2`). Schema 8 widened the chord vocabulary (`sus4(b7)`) and the numerals (`7sus4`). Schema 9 added `source.url`, the web page the recording came from. Schema 10 added `keys`, the key regions, and made `numeral`, `role`, `function` and `target` relative to the region containing the segment; `key` stays the whole song's key. The viewer reads 4 to 10 and saves a 10: below 10 it fills in `keys` as one region of `key.label` over the beats (`[]` when `key` is `null`), `source.url: null` below 9, `edited: false` on a 4, and on a 4 or 5 the engine `{"name": "dsp", "version": <generator.version>}`. A file below 10 was analyzed in its one `key`, so that region is the key its numerals are relative to.

```json
{
  "schema_version": 10,
  "generator": {"name": "chordotomy", "version": "0.0.0", "engine": {"name": "dsp", "version": "0.0.0"}},
  "source": {"path": "song.mp3", "duration": 5.0, "url": null},
  "key": {"label": "C:maj", "source": "estimated", "candidates": ["C:maj", "F:maj", "G:maj"]},
  "keys": [{"start_beat": 0, "end_beat": 10, "label": "C:maj"}],
  "beats": [0.023, 0.534, 1.045, 1.533, 2.043, 2.531, 3.042, 3.529, 4.04, 4.528],
  "segments": [
    {
      "start_beat": 0, "end_beat": 2, "start_time": 0.023, "end_time": 1.045,
      "chord": "C:maj", "candidates": ["C:maj", "C:7", "C:maj7"],
      "bass": "C", "inversion": "root",
      "numeral": "I", "role": "diatonic", "function": "tonic", "target": null, "edited": false
    },
    {
      "start_beat": 2, "end_beat": 4, "start_time": 1.045, "end_time": 2.043,
      "chord": "C:maj", "candidates": ["C:maj", "C:7", "A:min7"],
      "bass": "E", "inversion": "first",
      "numeral": "I", "role": "diatonic", "function": "tonic", "target": null, "edited": false
    },
    {
      "start_beat": 4, "end_beat": 6, "start_time": 2.043, "end_time": 3.042,
      "chord": "F:maj7", "candidates": ["F:maj7", "F:maj", "F:7"],
      "bass": "F", "inversion": "root",
      "numeral": "IVmaj7", "role": "diatonic", "function": "predominant", "target": null, "edited": false
    },
    {
      "start_beat": 6, "end_beat": 8, "start_time": 3.042, "end_time": 4.04,
      "chord": "F#:hdim7", "candidates": ["F#:hdim7", "A:min6", "A:min"],
      "bass": "F#", "inversion": "root",
      "numeral": "viiø7/V", "role": "secondary_dominant", "function": null, "target": "V", "edited": false
    },
    {
      "start_beat": 8, "end_beat": 10, "start_time": 4.04, "end_time": 5.0,
      "chord": "G:7", "candidates": ["G:7", "G:maj", "E:min"],
      "bass": "B", "inversion": "first",
      "numeral": "V7", "role": "diatonic", "function": "dominant", "target": null, "edited": false
    }
  ]
}
```
