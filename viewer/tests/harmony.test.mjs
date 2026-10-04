// harmony.js against the golden vectors Python writes (tests/harmony_vectors.py). Python is the
// reference: a failure here means the port drifted, or the fixture needs regenerating.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import Harmony from "../harmony.js";

const vectors = JSON.parse(
  readFileSync(new URL("../../tests/harmony_vectors.json", import.meta.url), "utf8"),
);

test("analyze agrees with Python on every progression", () => {
  vectors.progressions.forEach((c, index) => {
    assert.deepEqual(Harmony.analyze(c.progression, c.key), c.expected, `${index}: ${c.name}`);
  });
});

test("inversion agrees with Python on every chord and bass", () => {
  vectors.inversions.forEach(([label, bass, expected], index) => {
    assert.equal(Harmony.inversion(label, bass), expected, `${index}: ${label} over ${bass}`);
  });
});

test("chordRuns and progression agree with Python", () => {
  vectors.runs.forEach((c, index) => {
    const runs = Harmony.chordRuns(c.segments);
    const name = `${index}: ${c.name}`;
    assert.deepEqual(runs.map((run) => run.length), c.expected.sizes, name);
    assert.deepEqual(Harmony.progression(runs), c.expected.progression, name);
  });
});

// The fixture enumerates every label Python writes, so its roots and qualities are Python's
// vocabulary: a quality added on one side only shows up here.
test("the vocabulary is Python's", () => {
  const chords = [
    ...vectors.progressions.flatMap((c) => c.progression.map(([label]) => label)),
    ...vectors.inversions.map(([label]) => label),
    ...vectors.runs.flatMap((c) => c.segments.map((segment) => segment.chord)),
  ].filter((label) => label !== "N");
  const roots = new Set(chords.map((label) => label.split(":")[0]));
  const qualities = new Set(chords.map((label) => label.split(":")[1]));
  assert.deepEqual([...roots].sort(), [...Harmony.ROOTS].sort(), "roots");
  assert.deepEqual([...qualities].sort(), Object.keys(Harmony.QUALITIES).sort(), "qualities");
  // That case lists QUALITIES in chords.py's order, which QUALITY_NAMES must keep.
  const onC = vectors.progressions.find((c) => c.name === "every quality on C");
  const order = onC.progression.map(([label]) => label.split(":")[1]);
  assert.deepEqual(Harmony.QUALITY_NAMES, order, "quality order");

  const keys = vectors.progressions.flatMap((c) => [
    c.key,
    c.expected.key?.label,
    ...(c.expected.key?.candidates ?? []),
    ...c.expected.keys.map((region) => region.label),
  ]);
  for (const key of keys.filter((key) => key != null)) {
    assert.ok(Harmony.KEYS.includes(key), `key ${key}`);
  }
  for (const [, bass] of vectors.inversions.filter(([, bass]) => bass !== null)) {
    assert.ok(Harmony.ROOTS.includes(bass), `bass ${bass}`);
  }
});
