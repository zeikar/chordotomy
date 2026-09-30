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
  assert.equal(Core.bassName("D:7", "C:maj", "D"), "D");
  assert.equal(Core.bassName("A#:maj", "C:maj", "A#"), "B♭");
  assert.equal(Core.bassName("D:7", "C:maj", "F#"), "F♯");
  assert.equal(Core.bassName("D:7", "C:maj", null), null);
  assert.equal(Core.bassName("N", "C:maj", null), null);
});

test("a non-chord bass is spelled by its interval above the chord's root", () => {
  assert.equal(chordName("A:min", "C:maj", "D", "non_chord"), "Am/D");
  assert.equal(chordName("D#:maj", "A#:maj", "G#", "non_chord"), "E♭/A♭");
  assert.equal(chordName("B:min", "D:maj", "A#", "non_chord"), "Bm/A♯"); // not Bm/Bb
  assert.equal(chordName("A:maj", "D:maj", "D#", "non_chord"), "A/D♯"); // not A/Eb
  assert.equal(chordName("C:maj", "C:maj", "A#", "non_chord"), "C/B♭");
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

test("a candidate is spelled by its interval above the segment's chord", () => {
  const { alternativeName } = Core;
  assert.equal(alternativeName("G#:min", "E:7", "C:maj"), "G♯m"); // not Abm beside E7/G#
  assert.equal(alternativeName("A#:min", "F#:maj", "D:maj"), "A♯m");
  assert.equal(alternativeName("A#:min", "C#:maj", "D:maj"), "A♯m"); // not Bbm beside C#
  assert.equal(alternativeName("E:maj", "E:7", "C:maj"), "E");
  assert.equal(alternativeName("D:min", "G:7", "C:maj"), "Dm");
  assert.equal(alternativeName("A#:maj", "D:7", "C:maj"), "B♭");
  assert.equal(alternativeName("C#:maj", "F:min", "C:maj"), "D♭");
  assert.equal(alternativeName("N", "G:7", "C:maj"), "N.C.");
  assert.equal(alternativeName("C#:7", "N", "C:maj"), "D♭7"); // no chord: a degree of the key
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

test("left goes to the start of the chord, then to the one before; right to the next", () => {
  const segments = [
    { start_time: 0.5, end_time: 1.5 },
    { start_time: 1.5, end_time: 4.5 },
    { start_time: 4.5, end_time: 6.0 },
  ];
  const { stepIndex } = Core;
  assert.equal(stepIndex(segments, 3.0, -1), 1); // well into the chord: back to its start
  assert.equal(stepIndex(segments, 1.501, -1), 0); // at its start: the chord before
  assert.equal(stepIndex(segments, 2.3, -1), 0); // within its first second, as on a second press
  assert.equal(stepIndex(segments, 0.2, -1), 0); // before the first chord
  assert.equal(stepIndex(segments, 0.501, -1), 0); // at the first chord's start
  assert.equal(stepIndex(segments, 3.0, 1), 2);
  assert.equal(stepIndex(segments, 5.9, 1), 2); // the last chord stays put
  assert.equal(stepIndex(segments, 0.2, 1), 1);
  assert.equal(stepIndex([], 1, -1), -1);
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

test("chord and bass labels outside the schema are refused, not half-rendered", () => {
  const timeline = (segment) => ({ schema_version: 3, beats: [0], segments: [segment] });
  const ok = { chord: "C#:7", bass: "G#" };
  assert.equal(Core.timelineProblem(timeline(ok)), null);
  assert.equal(Core.timelineProblem(timeline({ chord: "N", bass: null })), null);
  assert.match(Core.timelineProblem(timeline({ ...ok, chord: "C:min7" })), /chord C:min7/);
  assert.match(Core.timelineProblem(timeline({ ...ok, bass: "Db" })), /bass Db/);
});

test("times format as m:ss", () => {
  assert.equal(formatTime(0), "0:00");
  assert.equal(formatTime(65.9), "1:05");
  assert.equal(formatTime(600), "10:00");
});

test("a label's pitch classes, root first", () => {
  assert.deepEqual(Core.pitchClasses("C:maj"), [0, 4, 7]);
  assert.deepEqual(Core.pitchClasses("A:min"), [9, 0, 4]);
  assert.deepEqual(Core.pitchClasses("G:7"), [7, 11, 2, 5]);
  assert.deepEqual(Core.pitchClasses("N"), []);
});

test("the first chord sits on middle C", () => {
  assert.deepEqual(Core.closestVoicing([0, 4, 7], null), [60, 64, 67]);
});

test("each chord takes the inversion closest to the one before", () => {
  const c = [60, 64, 67];
  assert.deepEqual(Core.closestVoicing(Core.pitchClasses("G:maj"), c), [59, 62, 67]);
  assert.deepEqual(Core.closestVoicing(Core.pitchClasses("F:maj"), c), [60, 65, 69]);
  assert.deepEqual(Core.closestVoicing(Core.pitchClasses("G:7"), c), [59, 62, 65, 67]);
  assert.deepEqual(Core.closestVoicing(Core.pitchClasses("C:maj"), c), c);
});

test("voicings don't drift out of the middle register", () => {
  // Round the circle of fifths twice, which would climb forever without a register window.
  const roots = ["C", "G", "D", "A", "E", "B", "F#", "C#", "G#", "D#", "A#", "F"];
  let previous = null;
  for (let i = 0; i < 24; i++) {
    previous = Core.closestVoicing(Core.pitchClasses(`${roots[i % 12]}:7`), previous);
    assert.ok(Math.min(...previous) >= 55 && Math.max(...previous) <= 77, previous.join(" "));
  }
});

test("segments get voicings in order, a bass below them, and silence for N", () => {
  const segment = (chord, bass) => ({ chord, bass });
  const [c, n, g, e] = Core.voicings([
    segment("C:maj", "E"),
    segment("N", null),
    segment("G:7", null),
    segment("E:7", "G#"),
  ]);
  assert.deepEqual(c, { notes: [60, 64, 67], bass: 40 }); // E2: the slash bass, not the root
  assert.equal(n, null);
  assert.deepEqual(g, { notes: [59, 62, 65, 67], bass: 43 }); // led from C across the N; G2 root
  assert.equal(e.bass, 44); // G#2
  assert.ok(e.bass < Math.min(...e.notes));
});

test("the bass takes the octave nearest the last one, so a stepwise line stays stepwise", () => {
  const line = ["G", "F#", "F", "E", "D#", "D", "C#", "C", "B", "A#"];
  const basses = Core.voicings(line.map((root) => ({ chord: `${root}:maj`, bass: null }))).map(
    (voicing) => voicing.bass,
  );
  assert.deepEqual(basses, [43, 42, 41, 40, 39, 38, 37, 36, 47, 46]); // wraps only at C2
});

test("every beat of a chord strikes it, and N stays silent", () => {
  const timeline = {
    beats: [0.5, 1, 1.5, 2, 2.5],
    segments: [
      { start_beat: 0, end_beat: 1, end_time: 1, chord: "N" },
      { start_beat: 1, end_beat: 3, end_time: 2, chord: "C:maj" },
      { start_beat: 3, end_beat: 5, end_time: 3, chord: "G:maj" },
    ],
  };
  assert.deepEqual(Core.strikes(timeline), [
    { time: 1, end: 1.5, segment: 1 },
    { time: 1.5, end: 2, segment: 1 },
    { time: 2, end: 2.5, segment: 2 },
    { time: 2.5, end: 3, segment: 2 }, // the last beat runs to the segment's end
  ]);
});

test("the strike to start from is the one still sounding, else the next", () => {
  const strikes = [
    { time: 1, end: 1.5 },
    { time: 1.5, end: 2 },
    { time: 3, end: 3.5 }, // after a gap of N
  ];
  assert.equal(Core.strikeIndexAt(strikes, 0), 0);
  assert.equal(Core.strikeIndexAt(strikes, 1.2), 0); // mid-beat: the chord sounds at once
  assert.equal(Core.strikeIndexAt(strikes, 1.5), 1);
  assert.equal(Core.strikeIndexAt(strikes, 2.5), 2);
  assert.equal(Core.strikeIndexAt(strikes, 9), 3);
});

test("due strikes are scheduled as audio-clock offsets from now", () => {
  const list = [
    { time: 1, end: 1.5, segment: 0 },
    { time: 1.5, end: 2, segment: 0 },
    { time: 2, end: 2.5, segment: 1 },
  ];
  const at = (media, options = {}) =>
    Core.dueStrikes(list, 0, { media, rate: 1, lookahead: 0.15, lag: 0, ...options });
  const round = ({ due, next }) => ({
    due: due.map((d) => [d.segment, +d.start.toFixed(3), +d.end.toFixed(3)]),
    next,
  });

  // Mid-beat: the chord under way starts now with what's left of it; the next isn't due yet.
  assert.deepEqual(round(at(1.2)), { due: [[0, 0, 0.3]], next: 1 });
  // Twice the speed: offsets halve, and the window reaches twice as far into the recording.
  assert.deepEqual(round(at(1.3, { rate: 2 })), { due: [[0, 0, 0.1], [0, 0.1, 0.35]], next: 2 });
  // Output latency: notes go out `lag` early, and the window widens by as much.
  assert.deepEqual(round(at(1.3, { lag: 0.1 })), { due: [[0, 0, 0.1], [0, 0.1, 0.6]], next: 2 });
  // A strike with under 80 ms left is skipped, not played as a blip; one that ended is too.
  assert.deepEqual(round(at(1.45)), { due: [[0, 0.05, 0.55]], next: 2 });
  assert.deepEqual(round(at(1.5)), { due: [[0, 0, 0.5]], next: 2 });
  // A stopped clock schedules nothing.
  assert.deepEqual(round(at(1.2, { rate: 0 })), { due: [], next: 0 });
});
