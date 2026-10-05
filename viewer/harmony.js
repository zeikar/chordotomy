// The harmonic analysis, ported so the viewer can re-analyze a corrected timeline: key estimation,
// key regions, numerals, roles and targets (src/chordotomy/harmony.py), the bass's position in a
// chord (chords.inversion), and the run grouping the analysis reads (timeline.chord_runs and
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
    ["aug", [0, 4, 8]],
    ["dim", [0, 3, 6]],
    ["sus2", [0, 2, 7]],
    ["sus4(b7)", [0, 5, 7, 10]],
    ["maj(9)", [0, 4, 7, 2]],
    ["min(9)", [0, 3, 7, 2]],
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
  // What a key change costs, in the unit of the weights (beats × degree weight): a stretch becomes
  // a region of its own only when it reads more than that much better in another key. Real songs
  // put the working range at 26–35: an A-major song ending D–E–F#sus4–F# (26 better in F# major)
  // holds from 26, and a song ending G, E for seven seconds, F loses that E at 36 and the F at 38.
  // Synthesized ones bound it too: a ii–V7/ii vamp and Fm–Bb inside a C-major verse (36 better in D
  // minor) split at 16 and hold from 18; a 20-beat half-step ending, F–C–Bb–C ×2, F (48 in F, 0 in
  // the song's E major), is kept through 44 and lost at 48, where it gains only what the change
  // costs; and a C-major verse with an A-minor chorus, Am–Dm–E7 ×5, stays one region at 30 only
  // with the relative rule below.
  const KEY_CHANGE_PENALTY = 30;
  // Relative keys share a scale, so only the degree weights tell them apart, and a switch between
  // them follows where the time goes inside a section rather than a modulation: a real song split
  // into C-sharp minor and E major over chords both keys share. So no region switches straight to
  // its relative. A third key can still bridge them: at a penalty of 15 to 19 the A-minor chorus
  // above goes C, D minor, C, as D minor reads it 40 better than C, and the estimator names that
  // region A minor.
  const RELATIVE = Object.fromEntries(
    ROOTS.map((root, i) => [`${root}:maj`, `${ROOTS[(i + 9) % 12]}:min`]),
  );
  for (const [major, minor] of Object.entries(RELATIVE)) RELATIVE[minor] = major;
  // Accidentals are relative to the key's own scale, so minor spells its natural-minor degrees
  // plain.
  const NUMERALS = {
    maj: ["I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII"],
    min: ["I", "bII", "II", "III", "#III", "IV", "#IV", "V", "VI", "#VI", "VII", "#VII"],
  };
  // Case shows the third: lowercase for a minor or diminished one; sus4, sus2 and sus4(b7) have
  // none and stay upper.
  const LOWERCASE = new Set(["min", "min7", "min6", "hdim7", "dim7", "dim", "min(9)"]);
  // min6 is `add6` because `iv6` is the first-inversion figure; the added ninths are `add9` for
  // the same reason, as `I9` would read as a ninth chord. ø and ° are the characters
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
    aug: "+",
    dim: "°",
    sus2: "sus2",
    "sus4(b7)": "7sus4",
    "maj(9)": "add9",
    "min(9)": "add9",
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
  // Each tetrad's triad, below its seventh (or min6's sixth, or an added ninth), for the
  // borrowed-seventh rule. The sus4(b7) entry keeps the table complete for every tetrad; for this quality the parallel-mode
  // test already covers every borrowed case, so it changes no classification.
  const TRIAD = {
    7: "maj",
    maj7: "maj",
    min7: "min",
    min6: "min",
    hdim7: "dim",
    dim7: "dim",
    "sus4(b7)": "sus4",
    "maj(9)": "maj",
    "min(9)": "min",
  };
  // The chords a secondary dominant can be: a major triad, alone or with a seventh or an added
  // ninth.
  const DOMINANTS = new Set(["maj", "7", "maj(9)"]);
  const CANDIDATES = 3;

  const mod = (n, m) => ((n % m) + m) % m;

  function isDiatonic(offset, quality, mode) {
    // The raised leading tone is admitted in five harmonic-minor chords and nowhere else: the
    // dominant (V, V7), the diminished triad and seventh on the leading tone (#vii°, #vii°7) and
    // the augmented mediant (III+). So it does not make F-G#-C or E-G#-C diatonic.
    if (
      mode === "min" &&
      ((offset === 7 && (quality === "maj" || quality === "7")) ||
        (offset === 11 && (quality === "dim" || quality === "dim7")) ||
        (offset === 3 && quality === "aug"))
    ) {
      return true;
    }
    return QUALITIES[quality].every((interval) => SCALE[mode].has((offset + interval) % 12));
  }

  // A chord of the parallel mode, or a tetrad on one of its triads whose fourth tone lies in
  // either mode: a seventh the borrowed triad takes from home is still borrowed color. So in major
  // bVIImaj7, ii°7 (the notes of the borrowed vii°7), iadd6 and vadd6 are borrowed. In minor the
  // rule would also cover I7 and IV7, but the secondary dominant claims them first. A triad of the
  // home mode with a foreign seventh stays chromatic (IV7 in major, VIImaj7 and iadd6 in minor), as
  // do sevenths outside both scales (bIII7, bVI7, Vmaj7). This only widens what borrowed covers;
  // the precedence stays diatonic, secondary dominant, leading-tone chord, borrowed, chromatic.
  function isBorrowed(offset, quality, mode) {
    const parallel = PARALLEL[mode];
    if (isDiatonic(offset, quality, parallel)) return true;
    if (!(quality in TRIAD)) return false;
    const fourth = (offset + QUALITIES[quality][3]) % 12;
    return (
      isDiatonic(offset, TRIAD[quality], parallel) &&
      (SCALE[mode].has(fourth) || SCALE[parallel].has(fourth))
    );
  }

  function resolves(following, root, tonic, mode) {
    if (following == null || following === "N") return false;
    const [followingRoot, quality] = following.split(":");
    const offset = mod(ROOTS.indexOf(followingRoot) - ROOTS.indexOf(tonic), 12);
    return followingRoot === root && isDiatonic(offset, quality, mode);
  }

  // A tonic seventh chord (Cmaj7, Am7) or added ninth (Cadd9) settles a key as its triad does, so
  // the tie-breaks compare it to the key label as that triad.
  function tonicTriad(label) {
    const [root, quality] = label.split(":");
    const triad =
      { maj7: "maj", min7: "min", "maj(9)": "maj", "min(9)": "min" }[quality] || quality;
    return `${root}:${triad}`;
  }

  // One beat's weight, shared by the estimator and the key regions.
  function weight(label, key) {
    if (label === "N") return 0;
    const [tonic, mode] = key.split(":");
    const [root, quality] = label.split(":");
    const offset = mod(ROOTS.indexOf(root) - ROOTS.indexOf(tonic), 12);
    return isDiatonic(offset, quality, mode) ? (DEGREE_WEIGHT[offset] ?? 1) : 0;
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
      let score = 0;
      for (const [label, n] of Object.entries(beats)) score += n * weight(label, key);
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

  // A Viterbi path over the 24 keys, one per run, scoring the runs' weights in their keys less
  // `penalty` per change. A path's score is the pair [that sum, minus its changes], so of two paths
  // that sum the same the one with fewer changes wins: a change that gains only the penalty never
  // splits, wherever it sits and whichever key comes first in KEYS. The path decides only where
  // the regions lie: each is named by the estimator over its own runs, so a single region is named
  // as the whole song is.
  function regionKeys(progression, penalty) {
    // Pairs compare as Python's tuples do, and max keeps the first of equal ones, as Python's does.
    const compare = (a, b) => a[0] - b[0] || a[1] - b[1];
    const max = (keys, scores) =>
      keys.reduce((top, key) => (compare(scores[key], scores[top]) > 0 ? key : top));
    const [label, n] = progression[0];
    let best = Object.fromEntries(KEYS.map((key) => [key, [n * weight(label, key), 0]]));
    const back = [];
    for (const [label, n] of progression.slice(1)) {
      const pointers = {};
      const scores = {};
      for (const current of KEYS) {
        // max keeps the first of equal scores, so a tie goes to the earliest in KEYS.
        const others = KEYS.filter((other) => other !== current && other !== RELATIVE[current]);
        const source = max(others, best);
        const stay = best[current];
        const change = [best[source][0] - penalty, best[source][1] - 1];
        // Switching on a tie puts each change as late as it can go, so a run that weighs the same
        // in both keys (an N, a pivot chord) stays with the key before it.
        const switches = compare(change, stay) >= 0;
        pointers[current] = switches ? source : current;
        const [total, minusChanges] = switches ? change : stay;
        scores[current] = [total + n * weight(label, current), minusChanges];
      }
      back.push(pointers);
      best = scores;
    }
    // Of paths with equal sums and equal changes, the one ending in the earliest key in KEYS.
    const path = [max(KEYS, best)];
    for (const pointers of back.reverse()) path.push(pointers[path[path.length - 1]]);
    path.reverse();
    const runKeys = [];
    for (let start = 0, end; start < path.length; start = end) {
      end = start + 1;
      while (end < path.length && path[end] === path[start]) end += 1;
      const ranked = estimateKey(progression.slice(start, end));
      // A stretch of only N is a stepping stone to the relative key (C, N, then A minor). With a
      // positive penalty it is never the first, as a leading N keeps the first chord's key at no
      // cost, and it stays with the key before it, as any N at a change does.
      const key = ranked.length ? ranked[0] : runKeys[runKeys.length - 1];
      runKeys.push(...Array(end - start).fill(key));
    }
    return runKeys;
  }

  // Neighbours named alike are one region.
  function regions(progression, runKeys) {
    const regions = [];
    let beat = 0;
    progression.forEach(([, n], index) => {
      const region = regions[regions.length - 1];
      if (region && region.label === runKeys[index]) region.end_beat += n;
      else regions.push({ start_beat: beat, end_beat: beat + n, label: runKeys[index] });
      beat += n;
    });
    return regions;
  }

  function numeral(offset, quality, mode) {
    let text = NUMERALS[mode][offset];
    // A diminished chord or a half-diminished seventh leads up a semitone, so its root is the
    // raised degree below, never the flattened one above: C#:dim7 in C major is #i°7, pointing at
    // ii, not bii°7. The degree below a flat one is always plain.
    if ((quality === "dim7" || quality === "hdim7" || quality === "dim") && text.startsWith("b")) {
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
    // An augmented triad never counts: it is symmetric, so its root is the bass's or
    // resolve_twins's spelling, not a fifth relation that identifies it. sus2 never counts either,
    // as sus4 does not, nor does a sus4(b7): no third, so no leading tone. An added ninth keeps the
    // triad's leading tone, so a maj(9) counts as its triad does; a maj7 does not, its major
    // seventh no dominant's.
    const secondary = DOMINANTS.has(quality) && targetOffset in TARGETS[mode];
    const borrowed = isBorrowed(offset, quality, mode);
    if (secondary) {
      const target = TARGETS[mode][targetOffset];
      const resolution = ROOTS[(ROOTS.indexOf(tonic) + targetOffset) % 12];
      // Only the major triads on the tonic and subdominant of a minor key, alone or with an added
      // ninth, are also chords of the parallel mode, and for those the very next chord being diatonic on the target's root is
      // the one thing that tells V/VII from a borrowed IV. The borrowed-seventh rule does not
      // widen this overlap, so I7 and IV7 in minor stay V7/iv and V7/VII wherever they go.
      // Outside this overlap and the leading-tone chords below, `following` is ignored, so a
      // label depends on the chord and key alone.
      const parallel = isDiatonic(offset, quality, PARALLEL[mode]);
      if (!parallel || resolves(following, resolution, tonic, mode)) {
        return {
          numeral: "V" + NUMERAL_SUFFIX[quality] + "/" + target,
          role: "secondary_dominant",
          function: null,
          target,
        };
      }
    }
    if (quality === "dim7" || quality === "hdim7" || quality === "dim") {
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

  // Analyze a list of [chord label, beats] into a key object, key regions and one analysis per
  // entry. The key object is the whole song's. `key`, if given, is a label from KEYS; it is then
  // the one region and every entry is analyzed in it. Null or undefined estimates it, the regions
  // come from `regionKeys`, and each entry is analyzed in its region's key. The key object is null,
  // and the regions empty, only when there is no chord to estimate from and no key was given.
  function analyze(progression, key = null) {
    const ranked = estimateKey(progression);
    if (key == null && !ranked.length) {
      // Every entry is N here, and an N is analyzed without looking at the key.
      return { key: null, keys: [], analyses: progression.map(() => analyzeChord("N", "C:maj")) };
    }
    const label = key ?? ranked[0];
    // The candidates stay the estimator's ranking even when the key is given, so a wrong
    // override can be compared against what the chords suggest.
    const keyObject = {
      label,
      source: key == null ? "estimated" : "given",
      candidates: ranked.slice(0, CANDIDATES),
    };
    const runKeys =
      key == null ? regionKeys(progression, KEY_CHANGE_PENALTY) : progression.map(() => key);
    // The look-ahead reads the next run whatever its region.
    const analyses = progression.map(([chord], index) =>
      analyzeChord(
        chord,
        runKeys[index],
        index + 1 < progression.length ? progression[index + 1][0] : null,
      ),
    );
    return { key: keyObject, keys: regions(progression, runKeys), analyses };
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
