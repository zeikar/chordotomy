import assert from "node:assert/strict";
import { test } from "node:test";

import Core from "../core.js";

const { chordName, formatTime, keyName, numeralText, segmentIndexAt, targetName } = Core;

test("keys with a sharp tonic take their conventional flat spelling", () => {
  assert.equal(keyName("A#:maj"), "B♭ major");
  assert.equal(keyName("D#:maj"), "E♭ major");
  assert.equal(keyName("G#:maj"), "A♭ major");
  assert.equal(keyName("C#:maj"), "D♭ major");
  assert.equal(keyName("A#:min"), "B♭ minor");
  assert.equal(keyName("D#:min"), "E♭ minor");
});

test("other keys are spelled as written", () => {
  assert.equal(keyName("F#:maj"), "F♯ major");
  assert.equal(keyName("C#:min"), "C♯ minor");
  assert.equal(keyName("G#:min"), "G♯ minor");
  assert.equal(keyName("A:min"), "A minor");
  assert.equal(keyName(null), null);
});

test("chord names use lead-sheet symbols", () => {
  assert.equal(chordName("C:maj", "C:maj"), "C");
  assert.equal(chordName("A:min", "C:maj"), "Am");
  assert.equal(chordName("G:7", "C:maj"), "G7");
  assert.equal(chordName("N", "C:maj"), "N.C.");
  assert.equal(chordName("C:maj", "C:maj", "C", "root"), "C");
  assert.equal(chordName("C:maj", "C:maj", "E", "first"), "C/E");
  assert.equal(chordName("C:maj", "C:maj", null, null), "C");
});

test("a root takes its letter from the numeral's degree", () => {
  assert.equal(chordName("A#:maj", "C:maj"), "B♭"); // bVII
  assert.equal(chordName("F#:maj", "C:maj"), "F♯"); // #IV
  assert.equal(chordName("C#:maj", "C:maj"), "D♭"); // bII
  assert.equal(chordName("G#:maj", "C:maj"), "A♭"); // bVI
  assert.equal(chordName("D#:maj", "A#:maj"), "E♭"); // IV in Bb
  assert.equal(chordName("G:7", "A#:maj"), "G7"); // V7/ii in Bb
  assert.equal(chordName("C#:maj", "D#:min"), "D♭"); // VII in Eb minor
  assert.equal(chordName("G#:maj", "C#:min"), "G♯"); // V in C# minor
  assert.equal(chordName("C#:maj", "A:min"), "C♯"); // #III in A minor
});

test("a secondary dominant's root is a fifth above its target", () => {
  assert.equal(chordName("D:7", "C:maj"), "D7"); // V7/V
  assert.equal(chordName("E:maj", "C:maj"), "E"); // V/vi
  assert.equal(chordName("B:7", "C:maj"), "B7"); // V7/iii
  assert.equal(chordName("A#:maj", "D#:min"), "B♭"); // V/iv in Eb minor
  assert.equal(chordName("G#:7", "C#:maj"), "A♭7"); // V7 in Db, the key's own spelling
});

test("the bass is spelled as the chord member its inversion names", () => {
  assert.equal(chordName("D:7", "C:maj", "F#", "first"), "D7/F♯");
  assert.equal(chordName("G:7", "C:maj", "F", "third"), "G7/F");
  assert.equal(chordName("A#:7", "C:maj", "G#", "third"), "B♭7/A♭");
  assert.equal(chordName("C:maj", "C:maj", "G", "second"), "C/G");
  assert.equal(chordName("G#:maj", "C#:min", "C", "first"), "G♯/B♯");
  assert.equal(chordName("D#:maj", "A#:maj", "G", "first"), "E♭/G");
});

test("the bass alone, for the now-playing panel", () => {
  assert.equal(Core.bassName("D:7", "C:maj", "D", "root"), "D");
  assert.equal(Core.bassName("A#:maj", "C:maj", "A#", "root"), "B♭");
  assert.equal(Core.bassName("D:7", "C:maj", "F#", "first"), "F♯");
  assert.equal(Core.bassName("D:7", "C:maj", null, null), null);
  assert.equal(Core.bassName("N", "C:maj", null, null), null);
});

test("a non-chord bass is spelled as a degree of the key", () => {
  assert.equal(chordName("A:min", "C:maj", "D", "non_chord"), "Am/D");
  assert.equal(chordName("D#:maj", "A#:maj", "G#", "non_chord"), "E♭/A♭");
});

test("spellings that would need a double accidental move to the next letter", () => {
  assert.equal(chordName("D:maj", "C#:maj"), "D"); // bII in Db would be Ebb
  assert.equal(chordName("G:maj", "G#:min"), "G"); // #VII in G# minor would be F##
  assert.equal(chordName("D#:maj", "G#:min", "G", "first"), "D♯/G"); // not D#/F##
});

test("without a key, roots are spelled as written", () => {
  assert.equal(chordName("A#:7", null), "A♯7");
  assert.equal(chordName("C:maj", null, "E", "first"), "C/E");
});

test("a candidate on a tone of the segment's chord keeps that tone's letter", () => {
  const { alternativeName } = Core;
  assert.equal(alternativeName("G#:min", "E:7", "C:maj"), "G♯m"); // not Abm beside E7/G#
  assert.equal(alternativeName("A#:min", "F#:maj", "D:maj"), "A♯m");
  assert.equal(alternativeName("E:maj", "E:7", "C:maj"), "E");
  assert.equal(alternativeName("D:min", "G:7", "C:maj"), "Dm");
  assert.equal(alternativeName("A#:maj", "D:7", "C:maj"), "B♭"); // not a tone of D7: key degree
  assert.equal(alternativeName("N", "G:7", "C:maj"), "N.C.");
  assert.equal(alternativeName("C#:7", "N", "C:maj"), "D♭7");
});

test("numerals take figured bass from the inversion", () => {
  assert.equal(numeralText("I", "root"), "I");
  assert.equal(numeralText("I", "first"), "I6");
  assert.equal(numeralText("I", "second"), "I64");
  assert.equal(numeralText("V7", "root"), "V7");
  assert.equal(numeralText("V7", "first"), "V65");
  assert.equal(numeralText("V7", "second"), "V43");
  assert.equal(numeralText("V7", "third"), "V42");
  assert.equal(numeralText("ii", "non_chord"), "ii");
  assert.equal(numeralText("V7", null), "V7");
  assert.equal(numeralText("IV7", "non_chord"), "IV7");
});

test("a secondary dominant puts the figure before the slash", () => {
  assert.equal(numeralText("V7/V", "first"), "V65/V");
  assert.equal(numeralText("V7/vi", "root"), "V7/vi");
  assert.equal(numeralText("V/V", "first"), "V6/V");
  assert.equal(numeralText("V/ii", "second"), "V64/ii");
});

test("numeral accidentals become glyphs", () => {
  assert.equal(numeralText("bVII7", "root"), "♭VII7");
  assert.equal(numeralText("#iv", "first"), "♯iv6");
  assert.equal(numeralText("bII", "first"), "♭II6");
});

test("a secondary dominant's target chord is a fifth below it", () => {
  assert.equal(targetName("D:7", "V", "C:maj"), "G");
  assert.equal(targetName("E:maj", "vi", "C:maj"), "Am");
  assert.equal(targetName("G:7", "ii", "A#:maj"), "Cm");
  assert.equal(targetName("G:maj", "III", "A:min"), "C");
  assert.equal(targetName("A#:maj", "iv", "D#:min"), "E♭m");
});

test("the segment at a time is the last one starting at or before it", () => {
  const segments = [
    { start_time: 0.5, end_time: 1.5 },
    { start_time: 1.5, end_time: 2.5 },
    { start_time: 2.5, end_time: 4.0 },
  ];
  assert.equal(segmentIndexAt(segments, 0.2), -1);
  assert.equal(segmentIndexAt(segments, 0.5), 0);
  assert.equal(segmentIndexAt(segments, 1.49), 0);
  assert.equal(segmentIndexAt(segments, 1.5), 1);
  assert.equal(segmentIndexAt(segments, 3.9), 2);
  assert.equal(segmentIndexAt(segments, 4.0), 2);
  assert.equal(segmentIndexAt([], 1), -1);
});

test("only schema version 3 is accepted", () => {
  const ok = { schema_version: 3, beats: [], segments: [] };
  assert.equal(Core.timelineProblem(ok), null);
  assert.match(Core.timelineProblem({ ...ok, schema_version: 2 }), /schema version 2.*analyze again/);
  assert.match(Core.timelineProblem({ ...ok, schema_version: 4 }), /newer chordotomy/);
  assert.match(Core.timelineProblem({ key: null }), /no schema_version/);
  assert.match(Core.timelineProblem([]), /no schema_version/);
  assert.match(Core.timelineProblem({ schema_version: 3 }), /no beats or segments/);
});

test("times format as m:ss", () => {
  assert.equal(formatTime(0), "0:00");
  assert.equal(formatTime(65.9), "1:05");
  assert.equal(formatTime(600), "10:00");
});
