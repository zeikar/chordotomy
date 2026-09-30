// The viewer's pure logic: spelling, chord names, numerals with figured bass, segment lookup, file
// validation, and what the chord sound plays when (voicings, strikes, the scheduling window). No
// DOM or audio, so Node's test runner covers it (viewer/tests/).
//
// A classic script, not an ES module: Chrome and Firefox refuse module scripts on file:// pages,
// and the viewer must also work opened straight from disk. In the browser it defines the global
// `Core`; under Node it is a CommonJS module.
"use strict";

const Core = (() => {
  const SCHEMA_VERSION = 3;
  const SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const CHORD_LABEL = /^[A-G]#?:(maj|min|7)$/;
  const LETTERS = "CDEFGAB";
  const NATURAL = [0, 2, 4, 5, 7, 9, 11];
  const GLYPH = { "-1": "♭", 0: "", 1: "♯" };
  const QUALITY_SUFFIX = { maj: "", min: "m", 7: "7" };
  // Seconds into a chord after which ← goes back to its start rather than to the chord before.
  const RESTART = 1;
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
  // this also spells V/x. Above a chord's root it gives each chord tone its member's letter (a
  // third two letters up, a seventh six), and any other note its interval's.
  const DEGREE = [0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6];
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

  // Spell `pc` by its interval above a spelled reference: a key's tonic or a chord's root.
  function spellAbove(pc, referencePc, referenceLetter) {
    return spell(pc, referenceLetter + DEGREE[mod(pc - referencePc, 12)]);
  }

  // Spell a pitch class as a degree of the key; without a key, as written (sharps).
  function spellInKey(pc, key) {
    if (!key) return spell(pc, LETTERS.indexOf(SHARPS[pc][0]));
    return spellAbove(pc, key.pc, key.letter);
  }

  function keyName(label) {
    const key = parseKey(label);
    if (!key) return null;
    return `${spell(key.pc, key.letter).name} ${key.mode === "min" ? "minor" : "major"}`;
  }

  function spellRoot(chord, key) {
    return spellInKey(SHARPS.indexOf(chord.split(":")[0]), key);
  }

  // Spell a note against a chord (not N) by its interval above the chord's spelled root, so the
  // bass and the other candidates agree with the chord: a chord tone as the member it is (F♯ under
  // D7, not G♭), any other note by its interval (Bm/A♯, not Bm/B♭).
  function spellAgainst(pc, chord, keyLabel) {
    const root = spellRoot(chord, parseKey(keyLabel));
    return spellAbove(pc, SHARPS.indexOf(chord.split(":")[0]), root.letter).name;
  }

  function bassName(chord, keyLabel, bass) {
    if (!bass || chord === "N") return null;
    return spellAgainst(SHARPS.indexOf(bass), chord, keyLabel);
  }

  // `C:maj` → C, `A:min` → Am, `G:7` → G7, `N` → N.C.; over a bass that isn't the root, a slash
  // chord (C/E).
  function chordName(chord, keyLabel, bass = null, inversion = null) {
    if (chord === "N") return "N.C.";
    const name = spellRoot(chord, parseKey(keyLabel)).name + QUALITY_SUFFIX[chord.split(":")[1]];
    if (!bass || !inversion || inversion === "root") return name;
    return `${name}/${bassName(chord, keyLabel, bass)}`;
  }

  // Another candidate for a segment, spelled against the segment's chord (G♯m beside E7/G♯, not
  // A♭m). Beside N there is no chord to agree with, so it is a degree of the key.
  function alternativeName(candidate, chord, keyLabel) {
    if (candidate === "N" || chord === "N") return chordName(candidate, keyLabel);
    const [root, quality] = candidate.split(":");
    return spellAgainst(SHARPS.indexOf(root), chord, keyLabel) + QUALITY_SUFFIX[quality];
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

  // Where ← (step -1) and → (step +1) go from time `t`. → is the next segment. ← is the start
  // of the current one, or the previous one when `t` is still within RESTART seconds of that
  // start, so pressing it again keeps going back, like a music player's previous-track button.
  function stepIndex(segments, t, step) {
    if (!segments.length) return -1;
    const index = Math.max(0, segmentIndexAt(segments, t));
    if (step > 0) return Math.min(segments.length - 1, index + 1);
    if (t - segments[index].start_time > RESTART) return index;
    return Math.max(0, index - 1);
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
    // Everything downstream (names, numerals, the chord sound) assumes the schema's vocabulary.
    for (const { chord, bass } of data.segments) {
      if (chord !== "N" && !CHORD_LABEL.test(chord)) {
        return `This timeline has a chord chordotomy doesn't write: chord ${chord}.`;
      }
      if (bass !== null && !SHARPS.includes(bass)) {
        return `This timeline has a note chordotomy doesn't write: bass ${bass}.`;
      }
    }
    return null;
  }

  // Hearing the chords. Voicings are MIDI note numbers: 60 is middle C.

  const INTERVALS = { maj: [0, 4, 7], min: [0, 3, 7], 7: [0, 4, 7, 10] };
  const MIDDLE_C = 60;
  // The lowest upper voice stays in G3–F♯4, one candidate per inversion, so a long progression
  // can't creep up or down the keyboard. The bass stays in C2–E3, always below it.
  const LOWEST_VOICE = 55;
  const BASS_RANGE = [36, 52];
  const FIRST_BASS = 43; // G2, the middle of the bass range
  // A strike already under way with less than this left would only be a blip.
  const SHORTEST = 0.08;

  function pitchClasses(chord) {
    if (chord === "N") return [];
    const [root, quality] = chord.split(":");
    return INTERVALS[quality].map((interval) => (SHARPS.indexOf(root) + interval) % 12);
  }

  function inversions(pcs) {
    const out = [];
    for (let low = LOWEST_VOICE; low < LOWEST_VOICE + 12; low++) {
      const first = pcs.indexOf(low % 12);
      if (first < 0) continue;
      const notes = [low];
      for (let k = 1; k < pcs.length; k++) {
        const pc = pcs[(first + k) % pcs.length];
        notes.push(notes[k - 1] + mod(pc - notes[k - 1], 12));
      }
      out.push(notes);
    }
    return out;
  }

  // How far the voices move: each note to the nearest note of the other chord, both ways, so a
  // triad and a seventh chord compare too.
  function motion(a, b) {
    const nearest = (note, chord) => Math.min(...chord.map((other) => Math.abs(note - other)));
    const total = (from, to) => from.reduce((sum, note) => sum + nearest(note, to), 0);
    return total(a, b) + total(b, a);
  }

  // The close-position inversion that moves least from `previous`; with none, the one nearest
  // middle C. Ties go to the one nearer the middle.
  function closestVoicing(pcs, previous) {
    const centre = (notes) => Math.abs(notes[0] - MIDDLE_C);
    const cost = (notes) => (previous ? motion(notes, previous) : 0) + centre(notes) / 100;
    return inversions(pcs).reduce((best, notes) => (cost(notes) < cost(best) ? notes : best));
  }

  // The octave of bass pitch class `pc` nearest the previous bass note (ties go lower), so a
  // stepwise bass line doesn't leap a seventh at an octave boundary.
  function closestBass(pc, previous) {
    let best = null;
    for (let note = BASS_RANGE[0]; note <= BASS_RANGE[1]; note++) {
      if (note % 12 !== pc) continue;
      if (best === null || Math.abs(note - previous) < Math.abs(best - previous)) best = note;
    }
    return best;
  }

  // One voicing per segment in timeline order, each led from the last chord heard (across any N),
  // so it doesn't depend on where playback starts. The bass is the segment's bass note, else the
  // root, so slash chords and inversions can be heard. N is null: silence.
  function voicings(segments) {
    let previous = null;
    let bass = FIRST_BASS;
    return segments.map((segment) => {
      if (segment.chord === "N") return null;
      const pcs = pitchClasses(segment.chord);
      previous = closestVoicing(pcs, previous);
      bass = closestBass(segment.bass ? SHARPS.indexOf(segment.bass) : pcs[0], bass);
      return { notes: previous, bass };
    });
  }

  // One strike per beat of every chord, so a change that misses the music's beat is easy to
  // hear. Each lasts until the next beat; a chord's last beat runs to the segment's end.
  function strikes(timeline) {
    const out = [];
    timeline.segments.forEach((segment, index) => {
      if (segment.chord === "N") return;
      for (let beat = segment.start_beat; beat < segment.end_beat; beat++) {
        const end = beat + 1 < segment.end_beat ? timeline.beats[beat + 1] : segment.end_time;
        out.push({ time: timeline.beats[beat], end, segment: index });
      }
    });
    return out;
  }

  // The first strike that hasn't ended by `t`: the one sounding at `t`, or else the next.
  function strikeIndexAt(list, t) {
    let lo = 0;
    let hi = list.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (list[mid].end <= t) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }

  // The strikes to schedule on one pass, from `index` on: those starting within `lookahead`
  // seconds of the recording's position `media`, as start and end offsets from now in audio-clock
  // seconds. Notes are heard `lag` seconds after they are scheduled (the audio output's latency),
  // so they go out that much early. A strike already under way starts at once with what's left.
  // Returns them with the index to continue from.
  function dueStrikes(list, index, { media, rate, lookahead, lag }) {
    const due = [];
    let next = index;
    if (!(rate > 0)) return { due, next };
    while (next < list.length && list[next].time < media + (lookahead + lag) * rate) {
      const strike = list[next++];
      const end = (strike.end - media) / rate - lag;
      if (end < SHORTEST) continue;
      const start = Math.max(0, (strike.time - media) / rate - lag);
      due.push({ segment: strike.segment, start, end });
    }
    return { due, next };
  }

  function formatTime(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  return {
    alternativeName,
    bassName,
    chordName,
    closestVoicing,
    dueStrikes,
    formatTime,
    keyName,
    numeralParts,
    numeralText,
    pitchClasses,
    segmentIndexAt,
    stepIndex,
    strikeIndexAt,
    strikes,
    targetName,
    timelineProblem,
    voicings,
  };
})();

if (typeof module === "object") module.exports = Core;
