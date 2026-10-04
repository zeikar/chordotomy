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

test("sevenths, sixths, diminished and sus chords use pop-chart symbols", () => {
  assert.equal(chordName("F:maj7", "C:maj"), "Fmaj7");
  assert.equal(chordName("D:min7", "C:maj"), "Dm7");
  assert.equal(chordName("G:min6", "C:maj"), "Gm6");
  assert.equal(chordName("F#:hdim7", "C:maj"), "F♯m7♭5");
  assert.equal(chordName("C#:dim7", "C:maj"), "C♯dim7");
  assert.equal(chordName("G:sus4", "C:maj"), "Gsus4");
  assert.equal(chordName("G:min6", "C:maj", "E", "third"), "Gm6/E");
  assert.equal(chordName("G:sus4", "C:maj", "C", "first"), "Gsus4/C");
});

test("augmented, diminished and sus2 triads are spelled out in letters", () => {
  assert.equal(chordName("C:aug", "C:maj"), "Caug");
  assert.equal(chordName("B:dim", "C:maj"), "Bdim");
  assert.equal(chordName("C:sus2", "C:maj"), "Csus2");
  assert.equal(chordName("C:sus2", "C:maj", "D", "first"), "Csus2/D");
  assert.equal(chordName("C:aug", "C:maj", "G#", "second"), "Caug/G♯");
});

test("a 7sus4 is named with its seventh and a bass on any of its tones", () => {
  assert.equal(chordName("A:sus4(b7)", "D:maj"), "A7sus4");
  assert.equal(chordName("A:sus4(b7)", "D:maj", "G", "third"), "A7sus4/G");
  assert.equal(chordName("A:sus4(b7)", "D:maj", "D", "first"), "A7sus4/D");
  assert.equal(chordName("A#:sus4(b7)", "F:maj"), "B♭7sus4");
});

test("an added ninth is named add9, its ninth a letter above the root", () => {
  assert.equal(chordName("A:maj(9)", "E:maj"), "Aadd9");
  assert.equal(chordName("C#:min(9)", "E:maj"), "C♯madd9");
  assert.equal(chordName("A#:maj(9)", "F:maj"), "B♭add9");
  assert.equal(chordName("C:maj(9)", "C:maj", "D", "third"), "Cadd9/D");
  // F♯m's ninth is G♯, not A♭.
  assert.equal(chordName("F#:min(9)", "E:maj", "G#", "third"), "F♯madd9/G♯");
});

test("a diminished root on a lowered degree is spelled raised, as its numeral is", () => {
  assert.equal(chordName("C#:dim7", "C:maj"), "C♯dim7"); // #i°7, not bii°7
  assert.equal(chordName("D#:hdim7", "C:maj"), "D♯m7♭5"); // #iiø7
  assert.equal(chordName("G#:dim7", "C:maj"), "G♯dim7"); // #v°7
  assert.equal(chordName("A#:dim7", "A:min"), "A♯dim7"); // #i°7 in A minor
  assert.equal(chordName("F:dim7", "E:maj"), "E♯dim7"); // #i°7 in E major, though F is natural
  // A flat that is the key's own degree is no lowered degree: iv°7 in F, iii°7 in C minor.
  assert.equal(chordName("A#:dim7", "F:maj"), "B♭dim7");
  assert.equal(chordName("D#:dim7", "C:min"), "E♭dim7");
  // Where agreement would take a double sharp, the enharmonic letter, as for any root: #i°7 in F♯.
  assert.equal(chordName("G:dim7", "F#:maj"), "Gdim7");
  // A diminished triad leads up too: C♯dim under #i°; iv° in F is plain, B♭dim.
  assert.equal(chordName("C#:dim", "C:maj"), "C♯dim");
  assert.equal(chordName("A#:dim", "F:maj"), "B♭dim");
  // Other qualities keep the key's spelling.
  assert.equal(chordName("C#:maj", "C:maj"), "D♭");
  assert.equal(chordName("D#:maj7", "C:maj"), "E♭maj7");
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

test("a diminished fifth in the bass is spelled as a fifth", () => {
  assert.equal(chordName("F#:hdim7", "C:maj", "C", "second"), "F♯m7♭5/C"); // not /B♯
  assert.equal(chordName("B:dim7", "C:maj", "F", "second"), "Bdim7/F");
  assert.equal(chordName("C#:dim7", "C:maj", "G", "second"), "C♯dim7/G");
  assert.equal(Core.bassName("F#:hdim7", "C:maj", "C"), "C");
  // The diminished seventh would be a double flat (B𝄫 above C), so it moves to the next letter.
  assert.equal(chordName("C:dim7", "C:maj", "A", "third"), "Cdim7/A");
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
  assert.equal(alternativeName("D#:dim7", "C:dim7", "C:maj"), "E♭dim7"); // the third it is
  assert.equal(alternativeName("E:hdim7", "G:min6", "D:maj"), "Em7♭5"); // the sixth it is
  assert.equal(alternativeName("A:sus4(b7)", "A:7", "D:maj"), "A7sus4");
});

test("a diminished candidate on other notes is named as it would be if chosen", () => {
  const { alternativeName } = Core;
  assert.equal(alternativeName("C#:dim7", "C:maj", "C:maj"), "C♯dim7"); // not D♭dim7
  assert.equal(alternativeName("C#:dim", "C:maj", "C:maj"), "C♯dim"); // a triad too
  assert.equal(alternativeName("D#:hdim7", "C:min", "C:maj"), "D♯m7♭5"); // not the E♭ of Cm
  assert.equal(alternativeName("A#:dim7", "F:maj", "F:maj"), "B♭dim7"); // iv°7: no raised root
  assert.equal(alternativeName("C#:maj", "C:maj", "C:maj"), "D♭"); // other qualities as before
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

test("seventh figures keep the seventh's quality marker", () => {
  assert.equal(numeralText("IVmaj7", "root"), "IVmaj7");
  assert.equal(numeralText("IVmaj7", "first"), "IVmaj65");
  assert.equal(numeralText("ii7", "second"), "ii43");
  assert.equal(numeralText("iiø7", "root"), "iiø7");
  assert.equal(numeralText("viiø7", "first"), "viiø65");
  assert.equal(numeralText("vii°7", "root"), "vii°7");
  assert.equal(numeralText("vii°7", "third"), "vii°42");
  assert.equal(numeralText("viiø7/V", "first"), "viiø65/V");
  assert.equal(numeralText("vii°7/ii", "non_chord"), "vii°7/ii");
});

test("diminished and augmented triads take triad figures", () => {
  assert.equal(numeralText("vii°", "root"), "vii°");
  assert.equal(numeralText("vii°", "first"), "vii°6");
  assert.equal(numeralText("vii°", "second"), "vii°64");
  assert.equal(numeralText("III+", "first"), "III+6");
  assert.equal(numeralText("#i°", "root"), "♯i°");
  assert.equal(numeralText("vii°/ii", "first"), "vii°6/ii");
  // °7 is matched before °, so a diminished seventh keeps its seventh figures.
  assert.equal(numeralText("vii°7", "third"), "vii°42");
  assert.equal(Core.numeralParts("vii°", "root").suffix, "°");
  assert.equal(Core.numeralParts("vii°7", "root").suffix, "°7");
});

test("add6, add9, sus4, sus2 and 7sus4 numerals take no figures", () => {
  for (const inversion of ["root", "first", "second", "third", "non_chord", null]) {
    assert.equal(numeralText("ivadd6", inversion), "ivadd6");
    assert.equal(numeralText("IVadd9", inversion), "IVadd9");
    assert.equal(numeralText("Vadd9/V", inversion), "Vadd9/V");
    assert.equal(numeralText("Vsus4", inversion), "Vsus4");
    assert.equal(numeralText("Vsus2", inversion), "Vsus2");
    assert.equal(numeralText("V7sus4", inversion), "V7sus4");
  }
  const parts = Core.numeralParts("V7sus4", "root");
  assert.equal(parts.suffix, "7sus4");
  assert.equal(parts.quality, "7sus4");
  assert.deepEqual(parts.figures, []);
  assert.deepEqual(Core.numeralParts("V7", "first").figures, ["6", "5"]);
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
  assert.equal(numeralText("#ivø7", "root"), "♯ivø7");
  assert.equal(numeralText("bVIImaj7", "root"), "♭VIImaj7");
});

test("a secondary dominant's target chord is a fifth below it", () => {
  assert.equal(targetName("D:7", "V", "C:maj"), "G");
  assert.equal(targetName("E:maj", "vi", "C:maj"), "Am");
  assert.equal(targetName("G:7", "ii", "A#:maj"), "Cm");
  assert.equal(targetName("G:maj", "III", "A:min"), "C");
  assert.equal(targetName("A#:maj", "iv", "D#:min"), "E♭m");
});

test("a leading-tone chord's target is a semitone above it", () => {
  assert.equal(targetName("F#:hdim7", "V", "C:maj", true), "G");
  assert.equal(targetName("C#:dim", "ii", "C:maj", true), "Dm");
  assert.equal(targetName("C#:dim7", "ii", "C:maj", true), "Dm");
  assert.equal(targetName("D#:dim7", "V", "A:min", true), "E");
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

test("the beat at a time is the last one at or before it", () => {
  const beats = [0.023, 0.523, 1.023];
  assert.equal(Core.beatIndexAt(beats, 0), -1);
  assert.equal(Core.beatIndexAt(beats, 0.023), 0);
  assert.equal(Core.beatIndexAt(beats, 0.522), 0);
  assert.equal(Core.beatIndexAt(beats, 0.523), 1);
  assert.equal(Core.beatIndexAt(beats, 1.023), 2);
  assert.equal(Core.beatIndexAt(beats, 9), 2); // past the last beat, in its tail to the end
  assert.equal(Core.beatIndexAt([], 1), -1);
});

test("a time's beat position is linear inside each beat, and at the edge gaps' rate outside", () => {
  const beats = [0.5, 1.0, 2.0];
  assert.equal(Core.beatPosition(beats, 0.5), 0);
  assert.equal(Core.beatPosition(beats, 0.75), 0.5);
  assert.equal(Core.beatPosition(beats, 1.5), 1.5); // a beat twice as long, at the same width
  assert.equal(Core.beatPosition(beats, 2.5), 2.5); // past the last beat, at the last gap's rate
  assert.equal(Core.beatPosition(beats, 0.25), -0.5); // before the first, at the first gap's rate
  // One beat has no gap of its own, so it takes half a second; none at all is position 0.
  assert.equal(Core.beatPosition([0.5], 1.0), 1);
  assert.equal(Core.beatPosition([0.5], 0.25), -0.5);
  assert.equal(Core.beatPosition([], 3), 0);
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

// A one-segment timeline as `chordotomy analyze` writes it in schema 4 (no `edited`), with
// `fields` laid over the segment. As a 6 it has the DSP for its engine; `edited` is up to `fields`.
const SEGMENT = {
  start_beat: 0,
  end_beat: 2,
  start_time: 0.5,
  end_time: 1.5,
  chord: "C#:7",
  candidates: ["C#:7", "C#:maj", "F:min"],
  bass: "G#",
  inversion: "second",
  numeral: "V7",
  role: "diatonic",
  function: "dominant",
  target: null,
};
const DSP = { name: "dsp", version: "0.0.0" };
const withSegment = (fields, version = 4) => ({
  schema_version: version,
  generator: { name: "chordotomy", version: "0.0.0", ...(version >= 6 && { engine: DSP }) },
  source: { path: "song.mp3", duration: 1.5 },
  key: { label: "F#:maj", source: "estimated", candidates: ["F#:maj", "C#:maj", "A#:min"] },
  beats: [0.5, 1.0],
  segments: [{ ...SEGMENT, ...fields }],
});

test("schema versions 4 to 10 are accepted", () => {
  const ok = {
    schema_version: 10,
    generator: { name: "chordotomy", version: "0.0.0", engine: DSP },
    source: { path: "song.mp3", duration: 1, url: null },
    key: null,
    keys: [],
    beats: [],
    segments: [],
  };
  assert.equal(Core.timelineProblem(ok), null);
  const { keys, ...nine } = { ...ok, schema_version: 9 }; // the key regions came with schema 10
  assert.equal(Core.timelineProblem(nine), null);
  assert.equal(Core.timelineProblem({ ...ok, schema_version: 8 }), null);
  assert.equal(Core.timelineProblem({ ...ok, schema_version: 7 }), null);
  assert.equal(Core.timelineProblem({ ...ok, schema_version: 6 }), null);
  assert.equal(Core.timelineProblem({ ...ok, schema_version: 5 }), null);
  assert.equal(Core.timelineProblem({ ...ok, schema_version: 4 }), null);
  assert.match(Core.timelineProblem({ ...ok, schema_version: 3 }), /schema version 3.*analyze again/);
  assert.match(Core.timelineProblem({ ...ok, schema_version: 11 }), /versions 4 to 10.*newer chordotomy/);
  assert.match(Core.timelineProblem({ key: null }), /no schema_version/);
  assert.match(Core.timelineProblem([]), /no schema_version/);
  assert.match(Core.timelineProblem({ schema_version: 4 }), /no beats or segments/);
});

test("a 9 carries a source url that is null or a string", () => {
  const nine = withSegment({ edited: false }, 9);
  const withUrl = (source) => ({ ...nine, source });
  const source = { path: "song.mp3", duration: 1.5 };
  // Only the shape is checked here: the renderer, not the opener, decides what is linked.
  for (const url of [null, "https://www.youtube.com/watch?v=abc", "not a url"]) {
    assert.equal(Core.timelineProblem(withUrl({ ...source, url })), null);
  }
  for (const bad of [source, { ...source, url: 5 }, { ...source, url: ["https://x"] }]) {
    assert.match(Core.timelineProblem(withUrl(bad)), /source has a missing or invalid url/);
  }
  assert.equal(Core.timelineProblem({ ...withSegment({ edited: false }, 8), source }), null);
});

// The one-segment timeline as a 10: its source url, its unedited segment, and its key, F♯ major,
// as the one region over its two beats.
const region = (start_beat, end_beat, label = "F#:maj") => ({ start_beat, end_beat, label });
const ten = {
  ...withSegment({ edited: false }, 10),
  source: { path: "song.mp3", duration: 1.5, url: null },
  keys: [region(0, 2)],
};

test("a 10's key regions tile the beats and agree with its key", () => {
  const problem = (fields) => Core.timelineProblem({ ...ten, ...fields });
  assert.equal(problem({}), null);
  const { keys, ...missing } = ten;
  assert.match(Core.timelineProblem(missing), /no keys list/);
  assert.match(problem({ keys: region(0, 2) }), /no keys list/);
  // Empty exactly when there is no key.
  assert.match(problem({ keys: [] }), /a key but no key regions/);
  assert.match(problem({ key: null }), /key regions but no key/);
  assert.equal(problem({ key: null, keys: [] }), null);
  // Each region is an object holding what chordotomy writes.
  assert.match(problem({ keys: [null] }), /key region 1 isn't an object/);
  assert.match(problem({ keys: [region(0, "2")] }), /key region 1 has a missing or invalid end_beat/);
  assert.match(problem({ keys: [region(0, 2, "Gb:maj")] }), /key region 1 has a missing or invalid label/);
  // They tile the beats as the segments do.
  assert.match(problem({ keys: [region(0, 0), region(0, 2)] }), /key region 1 lies outside its beats/);
  assert.match(problem({ keys: [region(0, 3)] }), /key region 1 lies outside its beats/);
  assert.match(problem({ keys: [region(1, 2)] }), /key region 1 doesn't start where/); // a gap
  const overlap = [region(0, 2), region(1, 2, "C#:maj")];
  assert.match(problem({ keys: overlap }), /key region 2 doesn't start where/);
  assert.match(problem({ keys: [region(0, 1)] }), /key region 1 stops short of the last beat/);
  // No boundary inside a segment: playback reads a segment's key at its first beat.
  const inside = [region(0, 1), region(1, 2, "C#:maj")];
  assert.match(problem({ keys: inside }), /key region 2 starts inside a segment/);
  // A lone region is the key itself, so the key shown never disagrees with the one playing.
  assert.match(problem({ keys: [region(0, 2, "C#:maj")] }), /region is labelled C#:maj, but its key is F#:maj/);
});

test("a 10's given key is one region; an estimated key may change at a segment", () => {
  const first = { ...ten.segments[0], end_beat: 1, end_time: 1.0 };
  const second = { ...ten.segments[0], start_beat: 1, start_time: 1.0 };
  const two = { ...ten, segments: [first, second], keys: [region(0, 1), region(1, 2, "C#:maj")] };
  assert.equal(Core.timelineProblem(two), null);
  const given = { ...two, key: { ...two.key, source: "given" } };
  assert.match(Core.timelineProblem(given), /given key must be one region, not 2/);
  assert.equal(Core.timelineProblem({ ...given, keys: [region(0, 2)] }), null);
});

test("the key at a beat is its region's, and none outside them", () => {
  const keys = [region(0, 64, "E:maj"), region(64, 76, "F:maj")];
  assert.equal(Core.keyAt(keys, 0), "E:maj");
  assert.equal(Core.keyAt(keys, 63), "E:maj");
  assert.equal(Core.keyAt(keys, 64), "F:maj");
  assert.equal(Core.keyAt(keys, 75), "F:maj");
  assert.equal(Core.keyAt(keys, 76), null);
  assert.equal(Core.keyAt(keys, -1), null);
  assert.equal(Core.keyAt([], 0), null); // a timeline with no key
});

test("only what the browser parses as http(s) is a link", () => {
  for (const url of [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "HTTPS://Example.com/x",
    "http://localhost/x",
    "https://1.2.3.4/",
    "https://user:pw@example.com:8443/a?b=c#d",
    "https://bücher.example/",
    "https://[::1]:8080/x",
  ]) {
    assert.equal(Core.isHttpUrl(url), true, url);
  }
  for (const value of [
    "javascript:alert(1)",
    "file:///etc/passwd",
    "ftp://x/y",
    "youtube.com/watch?v=abc",
    "https://",
    "https://:80/a",
    "not a url",
    "",
    null,
    undefined,
    5,
    ["https://x"],
  ]) {
    assert.equal(Core.isHttpUrl(value), false, String(value));
  }
});

test("a 6 must name its engine, and an older file the chordotomy version that wrote it", () => {
  const timeline = (version, generator) => ({ ...withSegment({ edited: false }, version), generator });
  const engine = (value) =>
    Core.timelineProblem(timeline(6, { name: "chordotomy", version: "0.0.0", engine: value }));
  assert.equal(engine(DSP), null);
  assert.equal(engine({ name: "lv-chordia", version: "1.1.0" }), null);
  for (const value of [undefined, null, "dsp", [], { name: "dsp" }, { name: 5, version: "1" }]) {
    assert.match(engine(value), /generator has a missing or invalid engine/, JSON.stringify(value));
  }
  assert.match(Core.timelineProblem(timeline(6, undefined)), /invalid engine/);
  // Edit.upgrade records a 4 or a 5 as the DSP's at generator.version, so that must be there.
  for (const version of [4, 5]) {
    assert.equal(Core.timelineProblem(timeline(version, { name: "chordotomy", version: "0.1.0" })), null);
    assert.match(Core.timelineProblem(timeline(version, { name: "chordotomy" })), /no generator version/);
    assert.match(Core.timelineProblem(timeline(version, undefined)), /no generator version/);
  }
});

test("the engine reads as its name and version, the DSP's name in capitals", () => {
  const generator = (engine) => ({ generator: { name: "chordotomy", version: "0.0.0", engine } });
  assert.equal(Core.engineText(generator({ name: "lv-chordia", version: "1.1.0" })), "lv-chordia 1.1.0");
  assert.equal(Core.engineText(generator(DSP)), "DSP 0.0.0");
  assert.equal(Core.engineText({ generator: { name: "chordotomy", version: "0.0.0" } }), "");
});

test("chord and bass labels outside the schema are refused, not half-rendered", () => {
  const timeline = withSegment;
  assert.equal(Core.timelineProblem(timeline({})), null);
  const silence = { chord: "N", bass: null, inversion: null, numeral: null, role: null };
  assert.equal(Core.timelineProblem(timeline({ ...silence, function: null })), null);
  const chords = ["C:min7", "G:min6", "F#:hdim7", "C#:dim7", "G:sus4", "F:maj7", "C:aug"];
  for (const chord of [...chords, "B:dim", "C:sus2", "A:sus4(b7)", "C:maj(9)", "A:min(9)"]) {
    assert.equal(Core.timelineProblem(timeline({ chord })), null, chord);
  }
  assert.match(Core.timelineProblem(timeline({ chord: "C:maj6" })), /chord C:maj6/);
  // The parentheses are literal: unescaped, the pattern would take A:sus4b7 and refuse A:sus4(b7).
  assert.match(Core.timelineProblem(timeline({ chord: "A:sus4b7" })), /chord A:sus4b7/);
  assert.match(Core.timelineProblem(timeline({ chord: "C:min9" })), /chord C:min9/);
  assert.match(Core.timelineProblem(timeline({ chord: "C:add9" })), /chord C:add9/);
  assert.match(Core.timelineProblem(timeline({ chord: "E#:maj" })), /chord E#:maj/);
  assert.match(Core.timelineProblem(timeline({ chord: "B#:7" })), /chord B#:7/);
  assert.match(Core.timelineProblem(timeline({ chord: ["C:maj"] })), /chord C:maj/);
  assert.match(Core.timelineProblem(timeline({ bass: "Db" })), /bass Db/);
});

test("every segment field the viewer reads must be there and hold what chordotomy writes", () => {
  const problem = (fields, version) => Core.timelineProblem(withSegment(fields, version));
  const missing = (field, version = 4) => {
    const segment = withSegment({}, version);
    delete segment.segments[0][field];
    return Core.timelineProblem(segment);
  };
  const fields = Object.keys(SEGMENT).filter((field) => field !== "chord" && field !== "bass");
  for (const field of fields) {
    assert.match(missing(field), new RegExp(`segment 1 has a missing or invalid ${field}\\.`));
  }
  // `edited` came with schema 5: Edit.upgrade adds it to a 4.
  assert.equal(problem({}, 4), null);
  for (const version of [5, 6, 7]) {
    assert.equal(problem({ edited: true }, version), null);
    assert.match(problem({}, version), /segment 1 has a missing or invalid edited/);
    assert.match(problem({ edited: "false" }, version), /invalid edited/);
  }
  assert.match(problem({ start_beat: "0" }), /invalid start_beat/);
  assert.match(problem({ end_beat: 1.5 }), /invalid end_beat/);
  assert.match(problem({ start_time: "0.5" }), /invalid start_time/);
  assert.match(problem({ candidates: "C#:7" }), /invalid candidates/);
  assert.match(problem({ candidates: ["C#:7", "C:maj6"] }), /invalid candidates/);
  assert.equal(problem({ inversion: "non_chord" }), null);
  assert.match(problem({ inversion: "fourth" }), /invalid inversion/);
  assert.match(problem({ numeral: 5 }), /invalid numeral/);
  assert.match(problem({ target: ["V"] }), /invalid target/);
  for (const segment of [null, 7, "C:maj"]) {
    const timeline = { ...withSegment({}), segments: [segment] };
    assert.match(Core.timelineProblem(timeline), /segment 1 isn't an object/);
  }
  const second = withSegment({ end_beat: 1, end_time: 1.0 });
  second.segments.push({ ...SEGMENT, start_beat: 2, end_beat: 2 });
  assert.match(Core.timelineProblem(second), /segment 2 lies outside its beats/);
  assert.match(problem({ start_beat: -1 }), /outside its beats/);
  assert.match(problem({ end_beat: 3 }), /outside its beats/); // beats has 2: end_beat may be 2
  assert.match(problem({ end_beat: 1e9 }), /outside its beats/);
});

test("the beats, the source duration and the key must hold what chordotomy writes", () => {
  const timeline = withSegment({});
  assert.match(
    Core.timelineProblem({ ...timeline, beats: [0.5, "1.0"] }),
    /beat that isn't a time/,
  );
  const { source, ...unsourced } = timeline;
  assert.match(Core.timelineProblem(unsourced), /no source duration/);
  assert.match(Core.timelineProblem({ ...timeline, source: { duration: "1.5" } }), /no source/);
  const key = (fields) =>
    Core.timelineProblem({ ...timeline, key: { ...timeline.key, ...fields } });
  assert.equal(key({ source: "given" }), null);
  assert.equal(key({ candidates: [] }), null);
  assert.match(key({ source: "guessed" }), /key has a missing or invalid source or candidates/);
  assert.match(key({ candidates: undefined }), /key has a missing or invalid/);
  assert.match(key({ candidates: ["F#:maj", "Gb:maj"] }), /key has a missing or invalid/);
  assert.match(Core.timelineProblem({ ...timeline, key: 5 }), /key undefined/);
});

test("beats must ascend and segments must tile them with matching times", () => {
  const timeline = withSegment({ end_beat: 1, end_time: 1.0 });
  const second = { ...SEGMENT, start_beat: 1, end_beat: 2, start_time: 1.0, end_time: 1.5 };
  const two = { ...timeline, segments: [...timeline.segments, second] };
  assert.equal(Core.timelineProblem(two), null);
  assert.match(Core.timelineProblem({ ...two, beats: [1.0, 0.5] }), /beats aren't in ascending/);
  assert.match(Core.timelineProblem({ ...two, beats: [0.5, 0.5] }), /beats aren't in ascending/);
  const gap = { ...two, beats: [0.5, 1.0, 1.2], segments: [two.segments[0], { ...second, start_beat: 2, end_beat: 3, start_time: 1.2 }] };
  assert.match(Core.timelineProblem(gap), /segment 2 doesn't start where/);
  const late = { ...two, segments: [{ ...two.segments[0], start_beat: 1, end_beat: 2 }, second] };
  assert.match(Core.timelineProblem(late), /segment 1 doesn't start where/);
  assert.match(Core.timelineProblem({ ...two, beats: [0.5, 1.0, 1.2] }), /segment 2 stops short/);
  const off = (index, fields) => ({
    ...two,
    segments: two.segments.map((seg, at) => (at === index ? { ...seg, ...fields } : seg)),
  });
  assert.match(Core.timelineProblem(off(0, { start_time: 0.4 })), /segment 1 has times/);
  assert.match(Core.timelineProblem(off(0, { end_time: 0.9 })), /segment 1 has times/);
  assert.match(Core.timelineProblem(off(1, { end_time: 1.4 })), /segment 2 has times/);
});

test("an odd value anywhere gets a reason, never a throw", () => {
  const odd = [null, 0, -1, "", "x", true, [], [null], {}, { label: "C:maj" }];
  const timeline = ten;
  const fields = ["generator", "source", "key", "keys", "beats", "segments"];
  const places = [
    ...fields.map((field) => (value) => ({ ...timeline, [field]: value })),
    ...Object.keys(timeline.segments[0]).map((field) => (value) => ({
      ...timeline,
      segments: [{ ...timeline.segments[0], [field]: value }],
    })),
    ...Object.keys(timeline.keys[0]).map((field) => (value) => ({
      ...timeline,
      keys: [{ ...timeline.keys[0], [field]: value }],
    })),
  ];
  for (const place of places) {
    for (const value of odd) {
      const result = Core.timelineProblem(place(value));
      assert.ok(result === null || typeof result === "string", JSON.stringify(place(value)));
    }
  }
});

test("a key label outside the 24 keys chordotomy writes is refused", () => {
  const timeline = (label) => ({
    schema_version: 4,
    generator: { name: "chordotomy", version: "0.0.0" },
    source: { path: "song.mp3", duration: 1 },
    key: { label, source: "estimated", candidates: [] },
    beats: [],
    segments: [],
  });
  assert.equal(Core.timelineProblem(timeline("A#:min")), null);
  assert.equal(Core.timelineProblem({ ...timeline("C:maj"), key: null }), null);
  assert.match(Core.timelineProblem(timeline("Bb:maj")), /key Bb:maj/);
  assert.match(Core.timelineProblem(timeline("C:dorian")), /key C:dorian/);
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
  assert.deepEqual(Core.pitchClasses("G:min6"), [7, 10, 2, 4]);
  assert.deepEqual(Core.pitchClasses("A:sus4(b7)"), [9, 2, 4, 7]);
  assert.deepEqual(Core.pitchClasses("C:maj(9)"), [0, 4, 7, 2]);
  assert.deepEqual(Core.pitchClasses("F#:hdim7"), [6, 9, 0, 4]);
  assert.deepEqual(Core.pitchClasses("G:sus4"), [7, 0, 2]);
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

test("sameNotes tells respelled twins from different pitch sets", () => {
  assert.equal(Core.sameNotes("F#:hdim7", "A:min6"), true);
  assert.equal(Core.sameNotes("C:dim7", "D#:dim7"), true);
  assert.equal(Core.sameNotes("A:min", "A:min6"), false);
  assert.equal(Core.sameNotes("N", "A:min"), false);
});

test("the silent stand-in is a PCM WAV as long as the timeline", () => {
  const wav = Core.silentWav(2.5);
  const view = new DataView(wav.buffer);
  const text = (at) => String.fromCharCode(...wav.subarray(at, at + 4));
  assert.equal(text(0), "RIFF");
  assert.equal(view.getUint32(4, true), wav.length - 8);
  assert.equal(text(8), "WAVE");
  assert.equal(text(12), "fmt ");
  assert.equal(view.getUint16(20, true), 1); // PCM
  assert.equal(view.getUint16(22, true), 1); // mono
  const rate = view.getUint32(24, true);
  assert.equal(view.getUint32(28, true), rate * view.getUint16(32, true));
  assert.equal(view.getUint16(34, true), 8);
  assert.equal(text(36), "data");
  const length = view.getUint32(40, true);
  assert.equal(wav.length, 44 + length);
  assert.equal(length / rate, 2.5);
  assert.ok(wav.subarray(44).every((sample) => sample === 128));
  // A duration that isn't a whole number of samples rounds up, so the track never ends early,
  // and to an even count, since RIFF would pad an odd-sized chunk.
  assert.equal(new DataView(Core.silentWav(1 / 3).buffer).getUint32(40, true) % 2, 0);
  assert.ok(new DataView(Core.silentWav(1 / 3).buffer).getUint32(40, true) / rate >= 1 / 3);
});
