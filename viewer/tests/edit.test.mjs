import assert from "node:assert/strict";
import { test } from "node:test";

import Core from "../core.js";
import Edit from "../edit.js";
import Harmony from "../harmony.js";

const { history, commit, undo, redo, merge, reanalyze, remove, setChord, setKey, split } = Edit;

// Frozen, so an edit that writes to its input throws (edit.js is strict mode) instead of passing.
function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value).forEach(deepFreeze);
  }
  return value;
}

// C, C/E, G7/B, Am, N on two beats each, as `chordotomy analyze` wrote it in schema 4: the
// numerals, roles and key are what Harmony.analyze gives for these chords.
const analysis = (numeral, role, fn) => ({ numeral, role, function: fn, target: null });
const v4 = deepFreeze({
  schema_version: 4,
  generator: { name: "chordotomy", version: "0.0.0" },
  source: { path: "song.mp3", duration: 5.0 },
  key: { label: "C:maj", source: "estimated", candidates: ["C:maj", "A:min", "F:maj"] },
  beats: [0.023, 0.523, 1.023, 1.523, 2.023, 2.523, 3.023, 3.523, 4.023, 4.523],
  segments: [
    {
      start_beat: 0,
      end_beat: 2,
      start_time: 0.023,
      end_time: 1.023,
      chord: "C:maj",
      candidates: ["C:maj", "C:maj7", "E:min"],
      bass: "C",
      inversion: "root",
      ...analysis("I", "diatonic", "tonic"),
    },
    {
      start_beat: 2,
      end_beat: 4,
      start_time: 1.023,
      end_time: 2.023,
      chord: "C:maj",
      candidates: ["C:maj", "A:min7", "E:min"],
      bass: "E",
      inversion: "first",
      ...analysis("I", "diatonic", "tonic"),
    },
    {
      start_beat: 4,
      end_beat: 6,
      start_time: 2.023,
      end_time: 3.023,
      chord: "G:7",
      candidates: ["G:7", "G:maj", "B:hdim7"],
      bass: "B",
      inversion: "first",
      ...analysis("V7", "diatonic", "dominant"),
    },
    {
      start_beat: 6,
      end_beat: 8,
      start_time: 3.023,
      end_time: 4.023,
      chord: "A:min",
      candidates: ["A:min", "A:min7", "C:maj"],
      bass: "A",
      inversion: "root",
      ...analysis("vi", "diatonic", "tonic"),
    },
    {
      start_beat: 8,
      end_beat: 10,
      start_time: 4.023,
      end_time: 5.0,
      chord: "N",
      candidates: ["N", "A:min", "C:maj"],
      bass: null,
      inversion: null,
      ...analysis(null, null, null),
    },
  ],
});
const base = deepFreeze(Edit.upgrade(v4));

// timeline.py's field order, which a saved file keeps.
const FIELDS = [
  "start_beat",
  "end_beat",
  "start_time",
  "end_time",
  "chord",
  "candidates",
  "bass",
  "inversion",
  "numeral",
  "role",
  "function",
  "target",
  "edited",
];
const assertFieldOrder = (timeline) => {
  for (const segment of timeline.segments) assert.deepEqual(Object.keys(segment), FIELDS);
};
const spans = (timeline) => timeline.segments.map((s) => [s.start_beat, s.end_beat]);

test("upgrade turns a schema-4 timeline into a 7 by the DSP with nothing edited", () => {
  assert.equal(base.schema_version, 7);
  assert.deepEqual(Object.keys(base), Object.keys(v4));
  // In the CLI's order: the engine follows the chordotomy version, which is the DSP's.
  assert.deepEqual(Object.entries(base.generator), [
    ["name", "chordotomy"],
    ["version", "0.0.0"],
    ["engine", { name: "dsp", version: "0.0.0" }],
  ]);
  assert.ok(base.segments.every((segment) => segment.edited === false));
  base.segments.forEach((segment, index) => {
    const { edited, ...rest } = segment;
    assert.deepEqual(rest, v4.segments[index]); // the analyzer's fields stand: no re-analysis
  });
  assertFieldOrder(base);
  assert.equal(Edit.upgrade(base), base);
});

test("upgrade turns a schema-5 timeline into a 7 by the DSP, keeping its edits", () => {
  const v5 = deepFreeze({
    ...setChord(base, 2, "D:7", "F#"),
    schema_version: 5,
    generator: { name: "chordotomy", version: "0.1.0" },
  });
  const upgraded = Edit.upgrade(v5);
  assert.equal(upgraded.schema_version, 7);
  assert.deepEqual(upgraded.generator, {
    name: "chordotomy",
    version: "0.1.0",
    engine: { name: "dsp", version: "0.1.0" },
  });
  assert.equal(upgraded.segments, v5.segments);
  assert.deepEqual(Object.keys(upgraded), Object.keys(v4));
});

test("upgrade turns a schema-6 timeline into a 7 that keeps its generator and segments", () => {
  const v6 = deepFreeze({ ...setChord(base, 2, "D:7", "F#"), schema_version: 6 });
  const upgraded = Edit.upgrade(v6);
  assert.equal(upgraded.schema_version, 7);
  assert.equal(upgraded.generator, v6.generator);
  assert.equal(upgraded.segments, v6.segments);
  assert.deepEqual(Object.keys(upgraded), Object.keys(v4));
});

test("reanalyze leaves an analyzer-written timeline as it was", () => {
  const again = reanalyze(base);
  assert.deepEqual(again, base);
  again.segments.forEach((segment, index) => assert.equal(segment, base.segments[index]));
});

test("setting D7 over F♯ before G7 makes a secondary dominant in first inversion", () => {
  const next = setChord(base, 1, "D:7", "F#");
  const segment = next.segments[1];
  assert.equal(segment.chord, "D:7");
  assert.equal(segment.bass, "F#");
  assert.equal(segment.inversion, "first");
  assert.equal(segment.numeral, "V7/V");
  assert.equal(segment.role, "secondary_dominant");
  assert.equal(segment.function, null);
  assert.equal(segment.target, "V");
  assert.equal(segment.edited, true);
  assert.equal(segment.candidates, base.segments[1].candidates); // what the analyzer heard
  // D7 is not diatonic to C major, so G major now outranks F major among the candidates.
  assert.deepEqual(next.key, {
    label: "C:maj",
    source: "estimated",
    candidates: ["C:maj", "A:min", "G:maj"],
  });
  // The segments the edit didn't touch, and whose analysis didn't change, are the same objects.
  for (const index of [0, 2, 3, 4]) assert.equal(next.segments[index], base.segments[index]);
  assertFieldOrder(next);
});

test("a bass on the root is root position", () => {
  const next = setChord(base, 2, "G:maj", "G");
  assert.equal(next.segments[2].inversion, "root");
  assert.equal(next.segments[2].numeral, "V");
});

test("setting N clears the bass, the inversion and the analysis", () => {
  const segment = setChord(base, 2, "N", "B").segments[2];
  assert.deepEqual(
    [segment.chord, segment.bass, segment.inversion, segment.numeral, segment.role],
    ["N", null, null, null, null],
  );
  assert.equal(segment.function, null);
  assert.equal(segment.target, null);
  assert.equal(segment.edited, true);
});

test("re-picking a segment's own chord and bass is no edit", () => {
  assert.equal(setChord(base, 1, "C:maj", "E"), base); // stays the analyzer's, not edited
  assert.equal(setChord(base, 4, "N", null), base);
  assert.equal(setChord(base, 4, "N", "C"), base); // N takes no bass, so this is N again
  assert.notEqual(setChord(base, 1, "C:maj", "C"), base); // a new bass is an edit
});

test("a diminished or sus2 triad is taken and analyzed", () => {
  const fields = (s) => [s.chord, s.bass, s.inversion, s.numeral, s.role, s.function, s.edited];
  const dim = setChord(base, 2, "B:dim", "D");
  assert.equal(dim.key.label, "C:maj");
  assert.deepEqual(fields(dim.segments[2]), ["B:dim", "D", "first", "vii°", "diatonic", "dominant", true]);
  const sus2 = setChord(base, 2, "C:sus2", "D");
  assert.deepEqual(fields(sus2.segments[2]), ["C:sus2", "D", "first", "Isus2", "diatonic", "tonic", true]);
});

test("a chord or bass outside the vocabulary changes nothing", () => {
  assert.equal(setChord(base, 1, "C:maj6", "C"), base);
  assert.equal(setChord(base, 1, "Db:maj", "C#"), base);
  assert.equal(setChord(base, 1, "C:maj", "Db"), base);
  assert.equal(setChord(base, 1, "C:maj", undefined), base);
  assert.equal(setChord(base, 9, "C:maj", "C"), base);
});

test("split cuts a segment at an inner beat into two with the parent's fields", () => {
  const next = split(base, 1, 3);
  assert.deepEqual(spans(next), [[0, 2], [2, 3], [3, 4], [4, 6], [6, 8], [8, 10]]);
  const [head, tail] = next.segments.slice(1, 3);
  for (const half of [head, tail]) {
    for (const field of ["chord", "bass", "inversion", "candidates", "edited", "numeral", "role"]) {
      assert.equal(half[field], base.segments[1][field], field);
    }
  }
  assert.equal(head.start_time, 1.023);
  assert.equal(head.end_time, base.beats[3]);
  assert.equal(tail.start_time, base.beats[3]);
  assert.equal(tail.end_time, 2.023);
  assert.equal(next.segments[0], base.segments[0]);
  assertFieldOrder(next);
});

test("the last segment's second half still runs to the end of the audio", () => {
  const next = split(base, 4, 9);
  assert.deepEqual(spans(next).slice(-2), [[8, 9], [9, 10]]);
  assert.equal(next.segments[4].end_time, base.beats[9]);
  assert.equal(next.segments[5].end_time, 5.0);
});

test("a split on or outside the segment's bounds changes nothing", () => {
  assert.equal(split(base, 1, 2), base); // its start beat
  assert.equal(split(base, 1, 4), base); // its end beat
  assert.equal(split(base, 1, 7), base);
  assert.equal(split(base, 1, 2.5), base);
  assert.equal(split(base, 9, 3), base);
});

test("merging keeps the surviving chord over both spans", () => {
  const right = merge(base, 1, 2);
  assert.deepEqual(spans(right), [[0, 2], [2, 6], [6, 8], [8, 10]]);
  const merged = right.segments[1];
  assert.deepEqual(
    [merged.chord, merged.bass, merged.inversion, merged.start_time, merged.end_time],
    ["C:maj", "E", "first", 1.023, 3.023],
  );
  assert.equal(merged.candidates, base.segments[1].candidates);
  assert.equal(merged.edited, true); // G7's span now sounds C
  assertFieldOrder(right);

  const left = merge(base, 2, 1);
  assert.deepEqual(spans(left), [[0, 2], [2, 6], [6, 8], [8, 10]]);
  assert.equal(left.segments[1].chord, "G:7");
  assert.equal(left.segments[1].bass, "B");
});

test("a merge is edited only when the chord or the bass changes over a span", () => {
  assert.equal(merge(base, 0, 1).segments[0].edited, true); // C over E becomes C over C
  const rejoined = merge(split(base, 1, 3), 1, 2);
  assert.equal(rejoined.segments[1].edited, false);
  assert.deepEqual(rejoined.segments[1], base.segments[1]);
  // An edited half carries its flag into the merge, whichever survives: changed and changed back,
  // its chord and bass are its twin's again but no longer the analyzer's.
  const halves = split(base, 1, 3);
  const edited = setChord(setChord(halves, 2, "G:maj", "G"), 2, "C:maj", "E");
  assert.equal(edited.segments[2].edited, true);
  assert.equal(merge(edited, 1, 2).segments[1].edited, true);
  assert.equal(merge(edited, 2, 1).segments[1].edited, true);
});

test("a merge with a neighbour off the ends or not adjacent changes nothing", () => {
  assert.equal(merge(base, 4, 5), base);
  assert.equal(merge(base, 0, -1), base);
  assert.equal(merge(base, 0, 2), base);
  assert.equal(merge(base, 1, 1), base);
});

test("remove lets the previous segment absorb it, or the next for the first", () => {
  const first = remove(base, 0);
  assert.deepEqual(spans(first), [[0, 4], [4, 6], [6, 8], [8, 10]]);
  assert.equal(first.segments[0].bass, "E");
  assert.equal(first.segments[0].start_time, 0.023);
  assert.equal(first.segments[0].edited, true);

  const middle = remove(base, 3);
  assert.deepEqual(spans(middle), [[0, 2], [2, 4], [4, 8], [8, 10]]);
  assert.equal(middle.segments[2].chord, "G:7");
  assert.equal(middle.segments[2].end_time, 4.023);

  const last = remove(base, 4);
  assert.equal(last.segments.at(-1).chord, "A:min");
  assert.equal(last.segments.at(-1).end_time, 5.0);
});

test("a lone segment survives remove", () => {
  const lone = deepFreeze({
    ...base,
    segments: [{ ...base.segments[0], end_beat: 10, end_time: 5.0 }],
  });
  assert.equal(remove(lone, 0), lone);
});

test("equal neighbours stay two segments, analyzed as the one chord they make", () => {
  // F♯ø7 leads to G only as a whole: alone, its first half would lead to its second half.
  let next = split(base, 1, 3);
  next = setChord(next, 1, "F#:hdim7", "F#");
  next = setChord(next, 2, "F#:hdim7", "A");
  assert.equal(next.segments.length, 6);
  assert.deepEqual(
    Harmony.chordRuns(next.segments).map((run) => run.length),
    [1, 2, 1, 1, 1],
  );
  assert.equal(Harmony.analyzeChord("F#:hdim7", "C:maj", "F#:hdim7").numeral, "#ivø7");
  for (const segment of next.segments.slice(1, 3)) {
    assert.equal(segment.numeral, "viiø7/V");
    assert.equal(segment.role, "secondary_dominant");
    assert.equal(segment.target, "V");
  }
  assert.equal(next.segments[2].inversion, "first");
  assert.equal(next.key.label, "C:maj");
});

test("a given key relabels every chord and keeps the estimator's candidates", () => {
  const minor = setKey(base, "A:min");
  assert.deepEqual(minor.key, { label: "A:min", source: "given", candidates: base.key.candidates });
  assert.deepEqual(
    minor.segments.map((s) => s.numeral),
    ["III", "III", "VII7", "i", null],
  );
  assert.equal(minor.segments[0].function, "tonic");
  assert.equal(minor.segments[4], base.segments[4]); // N's analysis didn't change
  assert.ok(minor.segments.every((segment) => segment.edited === false));

  const estimated = setKey(minor, null);
  assert.deepEqual(estimated.key, base.key);
  assert.deepEqual(estimated.segments, base.segments);
  assert.equal(setKey(base, "Bb:maj"), base);
});

test("setting the key it already has is no edit", () => {
  assert.equal(setKey(base, null), base); // estimated already
  const minor = setKey(base, "A:min");
  assert.equal(setKey(minor, "A:min"), minor);
  // Fixing the estimated key is an edit: later chord edits no longer move it.
  const fixed = setKey(base, "C:maj");
  assert.notEqual(fixed, base);
  assert.equal(fixed.key.source, "given");
  assert.equal(setChord(fixed, 0, "A:min", "A").key.label, "C:maj");
});

test("a timeline with no chord left has no key, and still takes every edit", () => {
  const silent = [0, 1, 2, 3].reduce(
    (timeline, index) => setChord(timeline, index, "N", null),
    base,
  );
  assert.equal(silent.key, null);
  assert.ok(silent.segments.every((segment) => segment.numeral === null));

  const halves = split(silent, 0, 1);
  assert.equal(halves.segments.length, 6);
  assert.equal(halves.key, null);

  const chord = setChord(silent, 0, "C:maj", "C");
  assert.deepEqual(chord.key, {
    label: "C:maj",
    source: "estimated",
    candidates: ["C:maj", "F:maj", "F:min"],
  });
  assert.equal(chord.segments[0].numeral, "I");

  const given = setKey(silent, "C:maj");
  assert.deepEqual(given.key, { label: "C:maj", source: "given", candidates: [] });
  assert.equal(setKey(given, null).key, null);
  assert.equal(setKey(silent, null), silent); // no key, and none given: nothing to change
});

test("undo returns the very timeline before the edit, and redo the edit", () => {
  const start = history(base);
  assert.deepEqual(start, { past: [], present: base, future: [] });
  assert.equal(undo(start), start);

  const edited = commit(start, split(base, 0, 1));
  assert.equal(redo(edited), edited);
  const undone = undo(edited);
  assert.equal(undone.present, base);
  assert.equal(redo(undone).present, edited.present);

  // A new edit after an undo drops the redo; an edit that changed nothing records no step.
  assert.deepEqual(commit(undone, remove(base, 2)).future, []);
  assert.equal(commit(edited, split(edited.present, 0, 0)), edited);
});

test("serialize writes the file as the CLI does", () => {
  const timeline = setChord(base, 1, "F#:hdim7", "F#");
  const text = Edit.serialize(timeline);
  assert.deepEqual(JSON.parse(text), timeline);
  assert.ok(text.startsWith('{\n  "schema_version": 7,\n'));
  assert.ok(text.endsWith("}\n"));
  assert.ok(text.includes('"numeral": "viiø7/V"'));
});

test("a 6 keeps the engine it was read with, through the upgrade and an edit to the saved file", () => {
  const generator = {
    name: "chordotomy",
    version: "0.0.0",
    engine: { name: "lv-chordia", version: "1.1.0" },
  };
  const model = deepFreeze({ ...base, schema_version: 6, generator });
  const upgraded = Edit.upgrade(model);
  assert.equal(upgraded.generator, generator);
  assert.equal(Edit.upgrade(upgraded), upgraded); // a 7 as it is
  const saved = JSON.parse(Edit.serialize(setChord(upgraded, 1, "F#:hdim7", "F#")));
  assert.equal(saved.schema_version, 7);
  assert.deepEqual(Object.entries(saved.generator), Object.entries(generator));
});

test("the save name is the audio stem plus .edited.chords.json", () => {
  const at = (path) => ({ source: { path } });
  const name = (path, opened = "x.chords.json") => Edit.saveName(at(path), opened);
  assert.equal(name("song.mp3"), "song.edited.chords.json");
  assert.equal(name("song.edited.mp3"), "song.edited.edited.chords.json");
  assert.equal(name("song.chords.mp3"), "song.chords.edited.chords.json");
  assert.equal(name("/music/dir.d/song.prototype.wav"), "song.prototype.edited.chords.json");
  assert.equal(name("C:\\Music\\My Songs\\song.mp3"), "song.edited.chords.json");
  assert.equal(name("song"), "song.edited.chords.json");
});

test("without a source path the save name follows the opened file's", () => {
  const name = (opened, source) => Edit.saveName({ source }, opened);
  for (const source of [undefined, {}, { path: "" }, { path: "/music/" }, { path: 5 }]) {
    assert.equal(name("song.chords.json", source), "song.edited.chords.json");
    assert.equal(name("song.edited.chords.json", source), "song.edited.chords.json");
    assert.equal(name("song.chords.chords.json", source), "song.chords.edited.chords.json");
    assert.equal(name("Song.Edited.Chords.json", source), "Song.edited.chords.json");
    assert.equal(name("out.json", source), "out.edited.chords.json");
    assert.equal(name("out", source), "out.edited.chords.json");
  }
});

test("a saved file passes the checks the viewer opens files with", () => {
  assert.equal(Core.timelineProblem(v4), null);
  // Every chord set to N: no key, no numerals.
  const silent = [0, 1, 2, 3].reduce((next, index) => setChord(next, index, "N", null), base);
  assert.equal(silent.key, null);
  const edits = [
    base,
    setChord(base, 2, "D:7", "F#"),
    split(base, 4, 9),
    merge(base, 0, 1),
    remove(base, 4),
    setKey(base, "A:min"),
    setKey(setKey(base, "A:min"), null),
    silent,
  ];
  for (const timeline of edits) {
    assert.equal(Core.timelineProblem(JSON.parse(Edit.serialize(timeline))), null);
  }
});
