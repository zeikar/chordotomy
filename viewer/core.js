// The viewer's pure logic: spelling, chord names, numerals with figured bass, segment lookup and
// file validation. No DOM, so Node's test runner covers it (viewer/tests/).
//
// A classic script, not an ES module: Chrome and Firefox refuse module scripts on file:// pages,
// and the viewer must also work opened straight from disk. In the browser it defines the global
// `Core`; under Node it is a CommonJS module.
"use strict";

const Core = (() => {
  const SCHEMA_VERSION = 3;
  const SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const LETTERS = "CDEFGAB";
  const NATURAL = [0, 2, 4, 5, 7, 9, 11];
  const GLYPH = { "-1": "♭", 0: "", 1: "♯" };
  const QUALITY_SUFFIX = { maj: "", min: "m", 7: "7" };
  // Keys whose written sharp tonic is conventionally spelled flat. Every other key keeps its label.
  const FLAT_KEYS = {
    "C#:maj": "Db",
    "D#:maj": "Eb",
    "G#:maj": "Ab",
    "A#:maj": "Bb",
    "A#:min": "Bb",
    "D#:min": "Eb",
  };
  // Scale degree (0 = I … 6 = VII) of each root offset from the tonic, the table chordotomy's
  // numerals use in both modes: offset 10 is bVII (a B-flat in C), offset 6 is #IV (an F-sharp).
  // A secondary dominant's root, a fifth above its diatonic target, lands on the same degree, so
  // this also spells V/x and the candidates, which have no numeral of their own.
  const DEGREE = [0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6];
  // Letter steps from the root to the chord member that an inversion puts in the bass.
  const MEMBER_STEPS = { root: 0, first: 2, second: 4, third: 6 };
  const FIGURES = {
    triad: { first: ["6"], second: ["6", "4"] },
    seventh: { first: ["6", "5"], second: ["4", "3"], third: ["4", "2"] },
  };

  const mod = (n, m) => ((n % m) + m) % m;

  // Name pitch class `pc` on letter `letter` (0 = C … 6 = B). Chord symbols avoid double
  // accidentals, so a spelling that needs one moves to the neighbouring letter (E𝄫 → D, F𝄪 → G).
  function spell(pc, letter) {
    let l = mod(letter, 7);
    let acc = mod(pc - NATURAL[l] + 6, 12) - 6;
    if (acc > 1 || acc < -1) {
      l = mod(l + Math.sign(acc), 7);
      acc = mod(pc - NATURAL[l] + 6, 12) - 6;
    }
    return { letter: l, name: LETTERS[l] + GLYPH[acc] };
  }

  function parseKey(label) {
    if (!label) return null;
    const [root, mode] = label.split(":");
    const written = FLAT_KEYS[label] || root;
    return { pc: SHARPS.indexOf(root), letter: LETTERS.indexOf(written[0]), mode };
  }

  // Spell a pitch class as a degree of the key; without a key, as written (sharps).
  function spellInKey(pc, key) {
    if (!key) return spell(pc, LETTERS.indexOf(SHARPS[pc][0]));
    return spell(pc, key.letter + DEGREE[mod(pc - key.pc, 12)]);
  }

  function keyName(label) {
    const key = parseKey(label);
    if (!key) return null;
    return `${spell(key.pc, key.letter).name} ${key.mode === "min" ? "minor" : "major"}`;
  }

  function spellRoot(chord, key) {
    return spellInKey(SHARPS.indexOf(chord.split(":")[0]), key);
  }

  // The bass is spelled as the chord member its inversion names (F♯ under D7, not G♭); a
  // non-chord bass as a degree of the key.
  function bassName(chord, keyLabel, bass, inversion) {
    if (!bass || chord === "N") return null;
    const key = parseKey(keyLabel);
    const pc = SHARPS.indexOf(bass);
    const steps = MEMBER_STEPS[inversion];
    if (steps === undefined) return spellInKey(pc, key).name;
    return spell(pc, spellRoot(chord, key).letter + steps).name;
  }

  // `C:maj` → C, `A:min` → Am, `G:7` → G7, `N` → N.C.; over a bass that isn't the root, a slash
  // chord (C/E).
  function chordName(chord, keyLabel, bass = null, inversion = null) {
    if (chord === "N") return "N.C.";
    const name = spellRoot(chord, parseKey(keyLabel)).name + QUALITY_SUFFIX[chord.split(":")[1]];
    if (!bass || !inversion || inversion === "root") return name;
    return `${name}/${bassName(chord, keyLabel, bass, inversion)}`;
  }

  // Split a numeral into parts for display, with the figured bass its inversion calls for:
  // I + first → I6, V7 + first → V65, V7/V + first → V65/V (the figure goes before the slash).
  // A non-chord or unknown bass keeps the root-position figure.
  function numeralParts(numeral, inversion) {
    const [head, target = null] = numeral.split("/");
    const match = /^([b#]?)([IViv]+)(7?)$/.exec(head);
    if (!match) return { accidental: "", roman: numeral, figures: [], target: null };
    const [, accidental, roman, seventh] = match;
    const figures = seventh
      ? FIGURES.seventh[inversion] || ["7"]
      : FIGURES.triad[inversion] || [];
    return { accidental: accidental && GLYPH[accidental === "b" ? -1 : 1], roman, figures, target };
  }

  function numeralText(numeral, inversion) {
    const p = numeralParts(numeral, inversion);
    return p.accidental + p.roman + p.figures.join("") + (p.target ? "/" + p.target : "");
  }

  // The chord a secondary dominant points at, a fifth below its root: V7/V in C → G, V/vi → Am.
  function targetName(chord, target, keyLabel) {
    const root = SHARPS.indexOf(chord.split(":")[0]);
    const minor = target === target.toLowerCase();
    return spellInKey(mod(root - 7, 12), parseKey(keyLabel)).name + (minor ? "m" : "");
  }

  // Index of the segment sounding at time `t`, or -1 before the first one. Segments are
  // contiguous and sorted, so this is the last one starting at or before `t`.
  function segmentIndexAt(segments, t) {
    let lo = 0;
    let hi = segments.length - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (segments[mid].start_time <= t) {
        found = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return found;
  }

  // A reason the parsed JSON can't be shown, or null if it can.
  function timelineProblem(data) {
    if (!data || typeof data !== "object" || !("schema_version" in data)) {
      return "This isn't a chordotomy timeline: it has no schema_version.";
    }
    const version = data.schema_version;
    if (version !== SCHEMA_VERSION) {
      const fix =
        version < SCHEMA_VERSION
          ? "Run chordotomy analyze again to write a current one."
          : "It was written by a newer chordotomy than this viewer.";
      return `This timeline uses schema version ${version}; the viewer reads version ${SCHEMA_VERSION}. ${fix}`;
    }
    if (!Array.isArray(data.segments) || !Array.isArray(data.beats)) {
      return "This timeline has no beats or segments list.";
    }
    return null;
  }

  function formatTime(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  return {
    bassName,
    chordName,
    formatTime,
    keyName,
    numeralParts,
    numeralText,
    segmentIndexAt,
    targetName,
    timelineProblem,
  };
})();

if (typeof module === "object") module.exports = Core;
