// The harmonic analysis, ported so the viewer can re-analyze a corrected timeline: key estimation,
// numerals, roles and targets (src/chordotomy/harmony.py), the bass's position in a chord
// (chords.inversion), and the run grouping the analysis reads (timeline.chord_runs and
// timeline.progression). Tables and functions keep Python's names. Python is the reference and
// tests/harmony_vectors.json pins this port to it (viewer/tests/harmony.test.mjs), so a rule
// change starts in Python and ends with regenerating that file.
//
// The chord vocabulary (ROOTS, QUALITY_TONES) lives here too, and core.js reads it from here. A
// new quality starts in Python (chords.py's QUALITIES and harmony.py's NUMERAL_SUFFIX, plus
// LOWERCASE for a minor or diminished third) and ends with regenerating the fixture. Here it
// takes the same entries, in QUALITY_TONES, NUMERAL_SUFFIX and LOWERCASE; core.js lists the
// display tables of its own that need one.
//
// A classic script, not an ES module, for the reason core.js gives; it loads before core.js. In
// the browser it defines the global `Harmony`; under Node it is a CommonJS module.
"use strict";

const Harmony = (() => {
  const ROOTS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  // Each quality's chord tones in semitones above the root, in the order `inversion` counts them,
  // listed in chords.py's order.
  const QUALITY_TONES = [
    ["maj", [0, 4, 7]],
    ["min", [0, 3, 7]],
    ["7", [0, 4, 7, 10]],
    ["maj7", [0, 4, 7, 11]],
    ["min7", [0, 3, 7, 10]],
    ["min6", [0, 3, 7, 9]],
    ["hdim7", [0, 3, 6, 10]],
    ["dim7", [0, 3, 6, 9]],
    ["sus4", [0, 5, 7]],
  ];
  // Wherever order matters, read QUALITY_NAMES: Object.keys(QUALITIES) lists "7" first, as JS
  // enumerates integer-like keys before the others.
  const QUALITY_NAMES = QUALITY_TONES.map(([name]) => name);
  const QUALITIES = Object.fromEntries(QUALITY_TONES);
  const INVERSIONS = ["root", "first", "second", "third"];
  // In Python's order, which is the estimator's final tie-break.
  const KEYS = ROOTS.flatMap((root) => ["maj", "min"].map((mode) => `${root}:${mode}`));
  const SCALE = { maj: new Set([0, 2, 4, 5, 7, 9, 11]), min: new Set([0, 2, 3, 5, 7, 8, 10]) };
  // The tonic outweighs IV and V, which outweigh the other degrees (1; a chord that is not
  // diatonic weighs 0), so time spent on I, IV and V decides between keys that share most of
  // their triads.
  const DEGREE_WEIGHT = { 0: 3, 5: 2, 7: 2 };
  // Accidentals are relative to the key's own scale, so minor spells its natural-minor degrees
  // plain.
  const NUMERALS = {
    maj: ["I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII"],
    min: ["I", "bII", "II", "III", "#III", "IV", "#IV", "V", "VI", "#VI", "VII", "#VII"],
  };
  // Case shows the third: lowercase for a minor or diminished one; sus4 has none and stays upper.
  const LOWERCASE = new Set(["min", "min7", "min6", "hdim7", "dim7"]);
  // min6 is `add6` because `iv6` is the first-inversion figure. ø and ° are the characters
  // themselves: core.js turns only the b and # accidentals into glyphs, so an ASCII stand-in
  // would reach the reader as a letter.
  const NUMERAL_SUFFIX = {
    maj: "",
    min: "",
    7: "7",
    maj7: "maj7",
    min7: "7",
    min6: "add6",
    hdim7: "ø7",
    dim7: "°7",
    sus4: "sus4",
  };
  // Tonic substitutes on III / VI; VII is the subtonic dominant in minor.
  const FUNCTIONS = {
    I: "tonic",
    II: "predominant",
    III: "tonic",
    IV: "predominant",
    V: "dominant",
    VI: "tonic",
    VII: "dominant",
  };
  // Triads a secondary dominant or leading-tone chord can tonicize, by root offset: the tonic and
  // the diminished degrees are excluded, and minor's degree 5 is written V, as its harmonic-minor
  // dominant.
  const TARGETS = {
    maj: { 2: "ii", 4: "iii", 5: "IV", 7: "V", 9: "vi" },
    min: { 3: "III", 5: "iv", 7: "V", 8: "VI", 10: "VII" },
  };
  const PARALLEL = { maj: "min", min: "maj" };
  const CANDIDATES = 3;

  const mod = (n, m) => ((n % m) + m) % m;

  function isDiatonic(offset, quality, mode) {
    // The raised leading tone is admitted in two harmonic-minor chords only, the dominant (V, V7)
    // and the diminished seventh on the leading tone (#vii°7), so it does not make F-G#-C
    // diatonic.
    if (
      mode === "min" &&
      ((offset === 7 && (quality === "maj" || quality === "7")) ||
        (offset === 11 && quality === "dim7"))
    ) {
      return true;
    }
    return QUALITIES[quality].every((interval) => SCALE[mode].has((offset + interval) % 12));
  }

  function resolves(following, root, tonic, mode) {
    if (following == null || following === "N") return false;
    const [followingRoot, quality] = following.split(":");
    const offset = mod(ROOTS.indexOf(followingRoot) - ROOTS.indexOf(tonic), 12);
    return followingRoot === root && isDiatonic(offset, quality, mode);
  }

  // A tonic seventh chord (Cmaj7, Am7) settles a key as its triad does, so the tie-breaks compare
  // it to the key label as that triad.
  function tonicTriad(label) {
    const [root, quality] = label.split(":");
    const triad = { maj7: "maj", min7: "min" }[quality] || quality;
    return `${root}:${triad}`;
  }

  // Rank all 24 keys for a list of [chord label, beats]; empty if there is no chord.
  function estimateKey(progression) {
    const beats = {};
    const tonicBeats = {};
    for (const [label, n] of progression) {
      if (label === "N") continue;
      beats[label] = (beats[label] || 0) + n;
      const triad = tonicTriad(label);
      tonicBeats[triad] = (tonicBeats[triad] || 0) + n;
    }
    if (!Object.keys(beats).length) return [];
    const first = tonicTriad(progression.find(([label]) => label !== "N")[0]);

    const rank = (key) => {
      const [tonic, mode] = key.split(":");
      const tonicIndex = ROOTS.indexOf(tonic);
      let score = 0;
      for (const [label, n] of Object.entries(beats)) {
        const [root, quality] = label.split(":");
        const offset = mod(ROOTS.indexOf(root) - tonicIndex, 12);
        if (isDiatonic(offset, quality, mode)) score += n * (DEGREE_WEIGHT[offset] ?? 1);
      }
      return [score, tonicBeats[key] || 0, first === key ? 1 : 0];
    };
    const ranks = KEYS.map(rank);
    const compare = (a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
    // Highest rank first, and equal ranks keep KEYS order, as Python's stable
    // sorted(reverse=True) does: KEYS order is the final tie-break.
    return KEYS.map((_, index) => index)
      .sort((a, b) => compare(ranks[b], ranks[a]) || a - b)
      .map((index) => KEYS[index]);
  }

  function numeral(offset, quality, mode) {
    let text = NUMERALS[mode][offset];
    // A diminished or half-diminished seventh leads up a semitone, so its root is the raised
    // degree below, never the flattened one above: C#:dim7 in C major is #i°7, pointing at ii,
    // not bii°7. The degree below a flat one is always plain.
    if ((quality === "dim7" || quality === "hdim7") && text.startsWith("b")) {
      text = "#" + NUMERALS[mode][offset - 1];
    }
    if (LOWERCASE.has(quality)) text = text.toLowerCase();
    return text + NUMERAL_SUFFIX[quality];
  }

  // Classify one chord against a key: numeral, role, function and target. `following` is the
  // label of the next run ("N" included), null or undefined for the last one.
  function analyzeChord(label, key, following = null) {
    if (label === "N") return { numeral: null, role: null, function: null, target: null };
    const [tonic, mode] = key.split(":");
    const [root, quality] = label.split(":");
    const offset = mod(ROOTS.indexOf(root) - ROOTS.indexOf(tonic), 12);
    const text = numeral(offset, quality, mode);
    if (isDiatonic(offset, quality, mode)) {
      // The degree names the function; only minor's #VII carries an accidental to strip.
      const harmonicFunction = FUNCTIONS[NUMERALS[mode][offset].replace(/^[#b]+/, "")];
      return { numeral: text, role: "diatonic", function: harmonicFunction, target: null };
    }
    let targetOffset = mod(offset - 7, 12);
    const secondary = (quality === "maj" || quality === "7") && targetOffset in TARGETS[mode];
    const borrowed = isDiatonic(offset, quality, PARALLEL[mode]);
    if (secondary) {
      const target = TARGETS[mode][targetOffset];
      const resolution = ROOTS[(ROOTS.indexOf(tonic) + targetOffset) % 12];
      // Only the major triads on the tonic and subdominant of a minor key are also borrowed, and
      // for those the very next chord being diatonic on the target's root is the one thing that
      // tells V/VII from a borrowed IV. Outside this overlap and the leading-tone chords below,
      // `following` is ignored, so a label depends on the chord and key alone.
      if (!borrowed || resolves(following, resolution, tonic, mode)) {
        return {
          numeral: (quality === "7" ? "V7" : "V") + "/" + target,
          role: "secondary_dominant",
          function: null,
          target,
        };
      }
    }
    if (quality === "dim7" || quality === "hdim7") {
      // The fifth relation of a dominant identifies it on its own; a leading-tone chord only by
      // where it goes, so it takes the same resolution test as the overlap above, always.
      targetOffset = (offset + 1) % 12;
      const resolution = ROOTS[(ROOTS.indexOf(tonic) + targetOffset) % 12];
      if (targetOffset in TARGETS[mode] && resolves(following, resolution, tonic, mode)) {
        const target = TARGETS[mode][targetOffset];
        return {
          numeral: "vii" + NUMERAL_SUFFIX[quality] + "/" + target,
          role: "secondary_dominant",
          function: null,
          target,
        };
      }
    }
    if (borrowed) return { numeral: text, role: "borrowed", function: null, target: null };
    return { numeral: text, role: "chromatic", function: null, target: null };
  }

  // Analyze a list of [chord label, beats] into a key object and one analysis per entry. `key`,
  // if given, is a label from KEYS; null or undefined estimates it. The key object is null only
  // when there is no chord to estimate from and no key was given.
  function analyze(progression, key = null) {
    const ranked = estimateKey(progression);
    if (key == null && !ranked.length) {
      // Every entry is N here, and an N is analyzed without looking at the key.
      return { key: null, analyses: progression.map(() => analyzeChord("N", "C:maj")) };
    }
    const label = key ?? ranked[0];
    // The candidates stay the estimator's ranking even when the key is given, so a wrong
    // override can be compared against what the chords suggest.
    const keyObject = {
      label,
      source: key == null ? "estimated" : "given",
      candidates: ranked.slice(0, CANDIDATES),
    };
    const analyses = progression.map(([chord], index) =>
      analyzeChord(chord, label, index + 1 < progression.length ? progression[index + 1][0] : null),
    );
    return { key: keyObject, analyses };
  }

  // Position of the bass note within a chord label: root/first/second/third or non_chord; null
  // for N or no bass.
  function inversion(label, bass) {
    if (label === "N" || bass == null) return null;
    const [root, quality] = label.split(":");
    const offset = mod(ROOTS.indexOf(bass) - ROOTS.indexOf(root), 12);
    const member = QUALITIES[quality].indexOf(offset);
    return member >= 0 ? INVERSIONS[member] : "non_chord";
  }

  // Group consecutive segments with one chord into runs. Harmony runs on chord runs, not
  // segments: the key weights and the secondary-dominant look-ahead are defined on chords, and a
  // bass change does not end a chord.
  function chordRuns(segments) {
    const runs = [];
    for (const segment of segments) {
      const run = runs[runs.length - 1];
      if (run && run[0].chord === segment.chord) run.push(segment);
      else runs.push([segment]);
    }
    return runs;
  }

  // Each run's chord and its length in beats, the input of `analyze`.
  function progression(runs) {
    return runs.map((run) => [run[0].chord, run[run.length - 1].end_beat - run[0].start_beat]);
  }

  return {
    CANDIDATES,
    DEGREE_WEIGHT,
    FUNCTIONS,
    INVERSIONS,
    KEYS,
    LOWERCASE,
    NUMERALS,
    NUMERAL_SUFFIX,
    PARALLEL,
    QUALITIES,
    QUALITY_NAMES,
    ROOTS,
    SCALE,
    TARGETS,
    analyze,
    analyzeChord,
    chordRuns,
    estimateKey,
    inversion,
    isDiatonic,
    numeral,
    progression,
    resolves,
    tonicTriad,
  };
})();

if (typeof module === "object") module.exports = Harmony;
