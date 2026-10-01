// Correcting a chord timeline: setting a chord or the key, splitting, merging and removing
// segments, the re-analysis every edit ends in, the undo history, and the saved file. Pure
// functions on a timeline object: each returns a new timeline and leaves its input alone, sharing
// the segments it didn't change, so the history can keep whole snapshots cheaply and an unchanged
// segment is recognisable by identity. No DOM.
//
// A classic script, not an ES module, for the reason core.js gives; it loads after harmony.js. In
// the browser it defines the global `Edit` and reads the global `Harmony`; under Node it is a
// CommonJS module that requires harmony.js.
"use strict";

const Edit = ((Harmony) => {
  // Every chord label in the vocabulary. Edits come from the page's choices, and anything else
  // would reach names, numerals and the saved file as a label chordotomy doesn't write.
  const LABELS = new Set(
    Harmony.ROOTS.flatMap((root) => Harmony.QUALITY_NAMES.map((quality) => `${root}:${quality}`)),
  );

  // A schema-4, 5, 6 or 7 timeline as an 8. An 8 only adds a chord quality, so a 6 or 7 changes its
  // version alone, keeping its generator and segments. Only the DSP wrote files before 6, so it is
  // the engine, at the chordotomy version that wrote the file; `engine` follows that version, where
  // timeline.py writes it. A 4 also had no edits: `edited: false` goes last on every segment,
  // where timeline.py writes it. An 8 is returned as it is. The analyzer's fields stand until the
  // first edit.
  function upgrade(data) {
    const version = data.schema_version;
    if (version === 8) return data;
    const { generator } = data;
    const segments =
      version === 4
        ? data.segments.map((segment) => ({ ...segment, edited: false }))
        : data.segments;
    return {
      ...data,
      schema_version: 8,
      generator:
        version < 6
          ? { ...generator, engine: { name: "dsp", version: generator.version } }
          : generator,
      segments,
    };
  }

  // A span's times, read from the beats as timeline.py writes them rather than computed, so an
  // edit adds no rounding of its own. A span to the last beat runs to the end of the audio.
  function times(timeline, startBeat, endBeat) {
    const { beats } = timeline;
    return {
      start_time: beats[startBeat],
      end_time: endBeat === beats.length ? timeline.source.duration : beats[endBeat],
    };
  }

  // `count` segments from `index` replaced by `replacement`; the others are the same objects.
  function replace(timeline, index, count, replacement) {
    const { segments } = timeline;
    return {
      ...timeline,
      segments: [...segments.slice(0, index), ...replacement, ...segments.slice(index + count)],
    };
  }

  // The key and every segment's numeral, role, function and target, recomputed from the chords as
  // `chordotomy analyze` computes them: on chord runs, so equal neighbours (the analyzer writes
  // them when the bass changes, a split leaves them) are one chord without being merged. A given
  // key stays given; an estimated one is estimated again. A segment whose analysis is unchanged
  // stays the same object.
  function reanalyze(timeline) {
    const runs = Harmony.chordRuns(timeline.segments);
    const { key, analyses } = Harmony.analyze(Harmony.progression(runs), givenKey(timeline));
    const segments = runs.flatMap((run, index) =>
      run.map((segment) => withAnalysis(segment, analyses[index])),
    );
    return { ...timeline, key, segments };
  }

  // The key the user or --key fixed, or null when it is estimated or there is none.
  function givenKey(timeline) {
    return timeline.key?.source === "given" ? timeline.key.label : null;
  }

  // The fields already exist on a segment, so spreading over them keeps the schema's order.
  function withAnalysis(segment, analysis) {
    const same = Object.entries(analysis).every(([field, value]) => segment[field] === value);
    return same ? segment : { ...segment, ...analysis };
  }

  // The user's chord and bass for a segment (`N` has no bass). The candidates stay what the
  // analyzer heard, so its other readings remain on offer. Picking what the segment already has
  // is no edit: the analyzer's chord stays unedited, and there is no step to undo or save.
  function setChord(timeline, index, chord, bass) {
    const segment = timeline.segments[index];
    const newBass = chord === "N" ? null : bass;
    if (
      !segment ||
      !(chord === "N" || LABELS.has(chord)) ||
      !(newBass === null || Harmony.ROOTS.includes(newBass)) ||
      (chord === segment.chord && newBass === segment.bass)
    ) {
      return timeline;
    }
    const edited = {
      ...segment,
      chord,
      bass: newBass,
      inversion: Harmony.inversion(chord, newBass),
      edited: true,
    };
    return reanalyze(replace(timeline, index, 1, [edited]));
  }

  // Two segments from one, cut at a beat strictly inside it. Both halves keep everything the
  // segment had, its edited flag included: neither half's chord changed.
  function split(timeline, index, beat) {
    const segment = timeline.segments[index];
    if (
      !segment ||
      !Number.isInteger(beat) ||
      beat <= segment.start_beat ||
      beat >= segment.end_beat
    ) {
      return timeline;
    }
    const head = { ...segment, end_beat: beat, ...times(timeline, segment.start_beat, beat) };
    const tail = { ...segment, start_beat: beat, ...times(timeline, beat, segment.end_beat) };
    return reanalyze(replace(timeline, index, 1, [head, tail]));
  }

  // One segment from the one at `index` and its neighbour (index ± 1): the one at `index` keeps
  // its chord, bass and candidates over both spans. It counts as edited when either was, or when
  // the neighbour's chord or bass differed, since that span now holds what the user chose rather
  // than what the analyzer heard there.
  function merge(timeline, index, neighbour) {
    const { segments } = timeline;
    const survivor = segments[index];
    const other = segments[neighbour];
    if (!survivor || !other || Math.abs(neighbour - index) !== 1) return timeline;
    const first = Math.min(index, neighbour);
    const startBeat = segments[first].start_beat;
    const endBeat = segments[first + 1].end_beat;
    const merged = {
      ...survivor,
      start_beat: startBeat,
      end_beat: endBeat,
      ...times(timeline, startBeat, endBeat),
      edited:
        survivor.edited ||
        other.edited ||
        survivor.chord !== other.chord ||
        survivor.bass !== other.bass,
    };
    return reanalyze(replace(timeline, first, 2, [merged]));
  }

  // A segment gone, its span taken by the one before, or by the next for the first. A lone
  // segment stays: there is nothing to take its span, and setting it to N silences it.
  function remove(timeline, index) {
    return index === 0 ? merge(timeline, 1, 0) : merge(timeline, index - 1, index);
  }

  // The key fixed to `label`, as --key fixes it, or estimated again for null. reanalyze reads
  // the given label off the timeline and replaces the whole key object, candidates included.
  // Fixing the estimated key's own label is an edit (later chord edits no longer move it);
  // choosing what is already in force is not.
  function setKey(timeline, label) {
    if (label === givenKey(timeline) || (label !== null && !Harmony.KEYS.includes(label))) {
      return timeline;
    }
    return reanalyze({ ...timeline, key: label === null ? null : { label, source: "given" } });
  }

  // Undo keeps whole timelines rather than inverse edits: they are small, the snapshots share
  // their unchanged segments, and undoing to the opened timeline gives back that very object,
  // which is how the page tells there is nothing unsaved.
  function history(initial) {
    return { past: [], present: initial, future: [] };
  }

  // An edit that changed nothing (invalid arguments, or choosing what is already there, return
  // the timeline itself) leaves no step to undo, and keeps what there is to redo.
  function commit(h, next) {
    if (next === h.present) return h;
    return { past: [...h.past, h.present], present: next, future: [] };
  }

  function undo(h) {
    if (!h.past.length) return h;
    return { past: h.past.slice(0, -1), present: h.past.at(-1), future: [h.present, ...h.future] };
  }

  function redo(h) {
    if (!h.future.length) return h;
    return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1) };
  }

  // The file as `chordotomy analyze` writes it: two-space indent, ø and ° as themselves, a final
  // newline. A whole-number float loses its ".0" (5.0 is written 5), which parses the same.
  function serialize(timeline) {
    return JSON.stringify(timeline, null, 2) + "\n";
  }

  // <audio stem>.edited.chords.json, the name the skill looks for next to the recording, so saving
  // never replaces what the analyzer wrote. The stem comes from the timeline's source path: the
  // opened file's name can't tell a stem ending in .edited or .chords from the viewer's own
  // suffixes. Without a usable source path, song.chords.json → song.edited.chords.json, and an
  // opened .edited.chords.json keeps its name; a name from -o without .chords.json loses its .json.
  function saveName(timeline, fileName) {
    const base = typeof timeline.source?.path === "string" ? timeline.source.path.split(/[\\/]/).pop() : "";
    const dot = base.lastIndexOf(".");
    const audioStem = dot > 0 ? base.slice(0, dot) : base;
    const stem =
      audioStem ||
      fileName.replace(/(\.edited)?\.chords\.json$/i, "").replace(/\.json$/i, "");
    return stem + ".edited.chords.json";
  }

  return {
    commit,
    history,
    merge,
    reanalyze,
    redo,
    remove,
    saveName,
    serialize,
    setChord,
    setKey,
    split,
    undo,
    upgrade,
  };
})(typeof Harmony === "object" ? Harmony : require("./harmony.js"));

if (typeof module === "object") module.exports = Edit;
