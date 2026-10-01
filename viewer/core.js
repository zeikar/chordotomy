// The viewer's pure logic: spelling, chord names, numerals with figured bass, segment lookup, file
// validation, and what the chord sound plays when (voicings, strikes, the scheduling window). No
// DOM or audio, so Node's test runner covers it (viewer/tests/).
//
// A classic script, not an ES module: Chrome and Firefox refuse module scripts on file:// pages,
// and the viewer must also work opened straight from disk. In the browser it defines the global
// `Core` and reads the global `Harmony` that harmony.js, loaded first, defines; under Node it is
// a CommonJS module that requires harmony.js.
"use strict";

const Core = ((Harmony) => {
  // The viewer reads 4 to 7 and writes 7; an older file is upgraded in memory (see Edit.upgrade).
  const MIN_SCHEMA_VERSION = 4;
  const SCHEMA_VERSION = 7;
  // The chord vocabulary lives in harmony.js, beside the analysis ported from Python, so it has
  // no copy here. A new quality still takes an entry in QUALITY_SUFFIX and MEMBER_STEPS below,
  // and, if its numeral suffix is new, in NUMERAL_SUFFIX, numeralParts' pattern and app.js's
  // QUALITY_WORDS; it also takes an option in index.html's Quality select.
  const SHARPS = Harmony.ROOTS;
  const CHORD_LABEL = new RegExp(
    `^(${Harmony.ROOTS.join("|")}):(${Harmony.QUALITY_NAMES.join("|")})$`,
  );
  const LETTERS = "CDEFGAB";
  const NATURAL = [0, 2, 4, 5, 7, 9, 11];
  // The key's own scale by degree, which a numeral's accidentals are relative to: bIII in C
  // major, a plain III in C minor.
  const SCALE = { maj: NATURAL, min: [0, 2, 3, 5, 7, 8, 10] };
  const GLYPH = { "-1": "♭", 0: "", 1: "♯" };
  const QUALITY_SUFFIX = {
    maj: "",
    min: "m",
    7: "7",
    maj7: "maj7",
    min7: "m7",
    min6: "m6",
    hdim7: "m7♭5",
    dim7: "dim7",
    sus4: "sus4",
    aug: "aug",
    dim: "dim",
    sus2: "sus2",
  };
  // Each quality's chord tones in semitones above the root, in the order `inversion` counts them.
  const INTERVALS = Harmony.QUALITIES;
  // Each of those tones' letter steps above the root: a third two letters up, a seventh six.
  const MEMBER_STEPS = {
    maj: [0, 2, 4],
    min: [0, 2, 4],
    7: [0, 2, 4, 6],
    maj7: [0, 2, 4, 6],
    min7: [0, 2, 4, 6],
    min6: [0, 2, 4, 5],
    hdim7: [0, 2, 4, 6],
    dim7: [0, 2, 4, 6],
    sus4: [0, 3, 4],
    aug: [0, 2, 4],
    dim: [0, 2, 4],
    sus2: [0, 1, 4],
  };
  // Seconds into a chord after which ← goes back to its start rather than to the chord before.
  const RESTART = 1;
  // The length beatPosition gives the one beat of a single-beat grid, which has no gap to go by.
  const LONE_BEAT = 0.5;
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
  // this also spells V/x. Above a chord's root it spells a note that isn't a chord tone by its
  // interval; chord tones go by MEMBER_STEPS instead, since by interval alone a diminished fifth
  // would be an augmented fourth (B♯ over F♯m7♭5, not C).
  const DEGREE = [0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6];
  const FIGURES = {
    triad: { first: ["6"], second: ["6", "4"] },
    seventh: { first: ["6", "5"], second: ["4", "3"], third: ["4", "2"] },
  };
  // A numeral's suffix: the quality marker that stays beside the figures, and which figures it
  // takes. add6, sus4 and sus2 take none: their inversions are not stacks of thirds, so no figure
  // names them, and the chord name already shows the bass.
  const NUMERAL_SUFFIX = {
    "": { quality: "", figures: "triad" },
    7: { quality: "", figures: "seventh" },
    maj7: { quality: "maj", figures: "seventh" },
    "ø7": { quality: "ø", figures: "seventh" },
    "°7": { quality: "°", figures: "seventh" },
    "°": { quality: "°", figures: "triad" },
    "+": { quality: "+", figures: "triad" },
    add6: { quality: "add6", figures: null },
    sus4: { quality: "sus4", figures: null },
    sus2: { quality: "sus2", figures: null },
  };

  const mod = (n, m) => ((n % m) + m) % m;
  const isDiminished = (quality) => quality === "dim7" || quality === "hdim7" || quality === "dim";

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
    const [root, quality] = chord.split(":");
    const pc = SHARPS.indexOf(root);
    // A diminished chord or a half-diminished seventh leads up a semitone, so its numeral names the
    // raised degree below rather than the lowered one above (C#:dim7 in C is #i°7, not bii°7). The
    // name is spelled the same way, C♯dim7 rather than D♭dim7, so the two agree, except where that
    // would take a double sharp: then the enharmonic letter, as for any root (G:dim7 in F♯ is
    // Gdim7 under #i°7, not F𝄪dim7).
    if (key && isDiminished(quality)) {
      const offset = mod(pc - key.pc, 12);
      if (offset < SCALE[key.mode][DEGREE[offset]]) {
        return spell(pc, key.letter + DEGREE[offset] - 1);
      }
    }
    return spellInKey(pc, key);
  }

  // Spell a note against a chord (not N) from the chord's spelled root, so the bass and the other
  // candidates agree with the chord: a chord tone as the member it is (F♯ under D7, not G♭; C
  // under F♯m7♭5, not B♯), any other note by its interval (Bm/A♯, not Bm/B♭).
  function spellAgainst(pc, chord, keyLabel) {
    const [root, quality] = chord.split(":");
    const rootPc = SHARPS.indexOf(root);
    const letter = spellRoot(chord, parseKey(keyLabel)).letter;
    const member = INTERVALS[quality].indexOf(mod(pc - rootPc, 12));
    if (member >= 0) return spell(pc, letter + MEMBER_STEPS[quality][member]).name;
    return spellAbove(pc, rootPc, letter).name;
  }

  function bassName(chord, keyLabel, bass) {
    if (!bass || chord === "N") return null;
    return spellAgainst(SHARPS.indexOf(bass), chord, keyLabel);
  }

  // `C:maj` → C, `A:min` → Am, `G:7` → G7, `F#:hdim7` → F♯m7♭5, `N` → N.C.; over a bass that
  // isn't the root, a slash chord (C/E).
  function chordName(chord, keyLabel, bass = null, inversion = null) {
    if (chord === "N") return "N.C.";
    const name = spellRoot(chord, parseKey(keyLabel)).name + QUALITY_SUFFIX[chord.split(":")[1]];
    if (!bass || !inversion || inversion === "root") return name;
    return `${name}/${bassName(chord, keyLabel, bass)}`;
  }

  // Another candidate for a segment, spelled against the segment's chord (G♯m beside E7/G♯, not
  // A♭m). Beside N there is no chord to agree with, so it is a degree of the key. A diminished
  // candidate is spelled against the chord only when it is a twin on the same notes (E♭dim7
  // beside Cdim7); on other notes it is named as it would be if chosen, its root raised as its
  // numeral's is (C♯dim7 beside C, not D♭dim7).
  function alternativeName(candidate, chord, keyLabel) {
    if (candidate === "N" || chord === "N") return chordName(candidate, keyLabel);
    const [root, quality] = candidate.split(":");
    if (isDiminished(quality) && noteSet(candidate) !== noteSet(chord)) {
      return chordName(candidate, keyLabel);
    }
    return spellAgainst(SHARPS.indexOf(root), chord, keyLabel) + QUALITY_SUFFIX[quality];
  }

  // Two labels on the same notes (F#:hdim7 and A:min6) are respellings, not different sounds.
  function sameNotes(a, b) {
    return a !== "N" && b !== "N" && noteSet(a) === noteSet(b);
  }

  function noteSet(chord) {
    return pitchClasses(chord)
      .sort((a, b) => a - b)
      .join();
  }

  // Split a numeral into parts for display, with the figured bass its inversion calls for:
  // I + first → I6, V7 + first → V65, V7/V + first → V65/V (the figure goes before the slash).
  // A quality marker stays (IVmaj7 + first → IVmaj65, iiø7 + second → iiø43, vii° + first →
  // vii°6). A non-chord or unknown bass keeps the root-position figure. `suffix` is the numeral's
  // own, which tells vii° from vii°7 where the marker alone cannot.
  function numeralParts(numeral, inversion) {
    const [head, target = null] = numeral.split("/");
    const match = /^([b#]?)([IViv]+)(maj7|7|ø7|°7|°|\+|add6|sus4|sus2)?$/.exec(head);
    if (!match) {
      return { accidental: "", roman: numeral, quality: "", suffix: "", figures: [], target: null };
    }
    const [, accidental, roman, suffix = ""] = match;
    const { quality, figures: table } = NUMERAL_SUFFIX[suffix];
    let figures = [];
    if (table === "seventh") figures = FIGURES.seventh[inversion] || ["7"];
    else if (table === "triad") figures = FIGURES.triad[inversion] || [];
    return {
      accidental: accidental && GLYPH[accidental === "b" ? -1 : 1],
      roman,
      quality,
      suffix,
      figures,
      target,
    };
  }

  function numeralText(numeral, inversion) {
    const p = numeralParts(numeral, inversion);
    const head = p.accidental + p.roman + p.quality + p.figures.join("");
    return head + (p.target ? "/" + p.target : "");
  }

  // The chord a secondary dominant points at, a fifth below its root (V7/V in C → G, V/vi → Am),
  // or a secondary leading-tone chord's, a semitone above its root (viiø7/V in C → G).
  function targetName(chord, target, keyLabel, leadingTone = false) {
    const root = SHARPS.indexOf(chord.split(":")[0]);
    const minor = target === target.toLowerCase();
    const resolution = mod(root + (leadingTone ? 1 : -7), 12);
    return spellInKey(resolution, parseKey(keyLabel)).name + (minor ? "m" : "");
  }

  // Of `count` ascending times, `timeAt(i)` the i-th, the index of the last at or before `t`, or
  // -1 before the first.
  function lastAtOrBefore(count, timeAt, t) {
    let lo = 0;
    let hi = count - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (timeAt(mid) <= t) {
        found = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return found;
  }

  // Index of the segment sounding at time `t`, or -1 before the first one. Segments are
  // contiguous and sorted, so this is the last one starting at or before `t`.
  function segmentIndexAt(segments, t) {
    return lastAtOrBefore(segments.length, (i) => segments[i].start_time, t);
  }

  // Index of the beat under time `t`, the last at or before it, or -1 before the first one.
  function beatIndexAt(beats, t) {
    return lastAtOrBefore(beats.length, (i) => beats[i], t);
  }

  // The fractional beat index of time `t`: the beat it falls in plus how far through that beat it
  // is, so every beat spans one unit whatever its length. Before the first beat and after the
  // last, the nearest gap carries on (negative before the first). The strip is scaled per beat so
  // that a one-beat chord has room for its name, and on a grid whose tempo changes that holds only
  // if each beat, not each second, gets the same width.
  function beatPosition(beats, t) {
    if (beats.length === 0) return 0;
    if (beats.length === 1) return (t - beats[0]) / LONE_BEAT;
    const i = Math.min(Math.max(beatIndexAt(beats, t), 0), beats.length - 2);
    return i + (t - beats[i]) / (beats[i + 1] - beats[i]);
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

  const isLabel = (value) =>
    value === "N" || (typeof value === "string" && CHORD_LABEL.test(value));
  const isText = (value) => typeof value === "string";
  const nullOr = (check) => (value) => value === null || check(value);
  const INVERSION_NAMES = [...Harmony.INVERSIONS, "non_chord"];
  // What the segment fields the viewer reads may hold, chord and bass aside: timelineProblem names
  // those two in its message. `edited` came with schema 5; Edit.upgrade adds it to a 4.
  const SEGMENT_FIELDS = {
    start_beat: Number.isInteger,
    end_beat: Number.isInteger,
    start_time: Number.isFinite,
    end_time: Number.isFinite,
    candidates: (value) => Array.isArray(value) && value.every(isLabel),
    inversion: nullOr((value) => INVERSION_NAMES.includes(value)),
    numeral: nullOr(isText),
    role: nullOr(isText),
    function: nullOr(isText),
    target: nullOr(isText),
  };
  const SEGMENT_FIELDS_5 = { ...SEGMENT_FIELDS, edited: (value) => typeof value === "boolean" };

  // A reason the parsed JSON can't be shown, or null if it can. Whatever passes is safe to draw and
  // edit: every field the viewer reads is there and holds what chordotomy writes.
  function timelineProblem(data) {
    if (!data || typeof data !== "object" || !("schema_version" in data)) {
      return "This isn't a chordotomy timeline: it has no schema_version.";
    }
    const version = data.schema_version;
    if (!Number.isInteger(version) || version < MIN_SCHEMA_VERSION || version > SCHEMA_VERSION) {
      const fix =
        version < MIN_SCHEMA_VERSION
          ? "Run chordotomy analyze again to write a current one."
          : "It was written by a newer chordotomy than this viewer.";
      return `This timeline uses schema version ${version}; the viewer reads versions ${MIN_SCHEMA_VERSION} to ${SCHEMA_VERSION}. ${fix}`;
    }
    if (!Array.isArray(data.segments) || !Array.isArray(data.beats)) {
      return "This timeline has no beats or segments list.";
    }
    if (!data.beats.every(Number.isFinite)) return "This timeline has a beat that isn't a time.";
    // An edit to the last segment runs it to the end of the audio.
    if (!Number.isFinite(data.source?.duration)) return "This timeline has no source duration.";
    // Edit.upgrade records an older file as the DSP's at the chordotomy version that wrote it.
    const { generator } = data;
    if (version < 6 && !isText(generator?.version)) {
      return "This timeline has no generator version.";
    }
    const engine = generator?.engine;
    if (version >= 6 && !(engine && isText(engine.name) && isText(engine.version))) {
      return "This timeline's generator has a missing or invalid engine.";
    }
    // Everything downstream (names, numerals, the chord sound) assumes the schema's vocabulary.
    // The key is null when there is no chord to estimate it from.
    const { key } = data;
    if (key != null && !Harmony.KEYS.includes(key.label)) {
      return `This timeline has a key chordotomy doesn't write: key ${key.label}.`;
    }
    if (
      key != null &&
      !(
        (key.source === "estimated" || key.source === "given") &&
        Array.isArray(key.candidates) &&
        key.candidates.every((label) => Harmony.KEYS.includes(label))
      )
    ) {
      return "This timeline's key has a missing or invalid source or candidates.";
    }
    const { beats, segments } = data;
    if (beats.some((time, index) => index > 0 && time <= beats[index - 1])) {
      return "This timeline's beats aren't in ascending order.";
    }
    const fields = data.schema_version >= 5 ? SEGMENT_FIELDS_5 : SEGMENT_FIELDS;
    for (const [index, segment] of data.segments.entries()) {
      const where = `segment ${index + 1}`;
      if (!segment || typeof segment !== "object") {
        return `This timeline's ${where} isn't an object.`;
      }
      const { chord, bass } = segment;
      if (!isLabel(chord)) {
        return `This timeline has a chord chordotomy doesn't write: chord ${chord}.`;
      }
      if (bass !== null && !SHARPS.includes(bass)) {
        return `This timeline has a note chordotomy doesn't write: bass ${bass}.`;
      }
      const field = Object.keys(fields).find((name) => !fields[name](segment[name]));
      if (field) return `This timeline's ${where} has a missing or invalid ${field}.`;
      // Beats outside the list would be read as undefined times, and a huge span would hang the
      // chord sound, which strikes every beat of it.
      const { start_beat: start, end_beat: end } = segment;
      if (start < 0 || end <= start || end > data.beats.length) {
        return `This timeline's ${where} lies outside its beats.`;
      }
      // Beat lookup, split and merge rely on segments that tile the beats and carry their times.
      if (start !== (index ? segments[index - 1].end_beat : 0)) {
        return `This timeline's ${where} doesn't start where the one before it ends.`;
      }
      const last = index === segments.length - 1;
      if (last && end !== beats.length) return `This timeline's ${where} stops short of the last beat.`;
      if (segment.start_time !== beats[start] || segment.end_time !== (last ? data.source.duration : beats[end])) {
        return `This timeline's ${where} has times that don't match its beats.`;
      }
    }
    return null;
  }

  // The recognizer that produced the chords, as the header shows it ("lv-chordia 1.1.0",
  // "DSP 0.0.0"), or "" for a timeline that doesn't say.
  function engineText(data) {
    const engine = data.generator?.engine;
    if (!engine) return "";
    return `${engine.name === "dsp" ? "DSP" : engine.name} ${engine.version}`;
  }

  // Hearing the chords. Voicings are MIDI note numbers: 60 is middle C.

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
    beatIndexAt,
    beatPosition,
    chordName,
    closestVoicing,
    dueStrikes,
    engineText,
    formatTime,
    keyName,
    numeralParts,
    numeralText,
    pitchClasses,
    sameNotes,
    segmentIndexAt,
    stepIndex,
    strikeIndexAt,
    strikes,
    targetName,
    timelineProblem,
    voicings,
  };
})(typeof Harmony === "object" ? Harmony : require("./harmony.js"));

if (typeof module === "object") module.exports = Core;
