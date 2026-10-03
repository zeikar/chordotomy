// The viewer's DOM side: opening files, the timeline, the current-chord panel, editing and
// playback. A classic script like core.js (see there for why). The scripts are deferred, so they
// run in document order: harmony.js, core.js, edit.js, then this one.
"use strict";

(() => {
  const PX_PER_BEAT = 76;
  const RULER_STEP = 5; // seconds between time labels
  // Reading currentTime back can land a hair before the value just set, which would light up the
  // previous segment.
  const SEEK_NUDGE = 0.001;
  const AUDIO_NAME = /\.(mp3|wav|flac|m4a|aac|ogg|oga|opus|webm)$/i;
  // Hearing the chords: every TICK_MS, notes due in the next LOOKAHEAD seconds are scheduled on
  // the AudioContext clock, mapped from the recording's currentTime. Timers are too coarse to
  // start notes on time themselves; the audio clock isn't.
  const TICK_MS = 50;
  const LOOKAHEAD = 0.15;
  const ATTACK = 0.012;
  const RELEASE = 0.02; // time constant of the fade just before the next beat
  const INVERSION_TEXT = {
    root: "root position",
    first: "first inversion",
    second: "second inversion",
    third: "third inversion",
    non_chord: "not a chord tone",
  };
  // Screen readers would say "degree" for °, "o with stroke" for ø, and read ivadd6 as one word.
  // Keyed by the numeral's suffix, not its marker: vii° and vii°7 share the °.
  const QUALITY_WORDS = {
    maj7: "major seventh",
    "ø7": "half-diminished seventh",
    "°7": "diminished seventh",
    "°": "diminished",
    "+": "augmented",
    add6: "add 6",
    sus4: "sus 4",
    sus2: "sus 2",
    "7sus4": "seven sus 4",
  };

  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const strip = $("strip");
  const picker = $("picker");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

  // Every edit is a step in `history` (see Edit.history), and `timeline` is its present, set only
  // by refreshView. `saved` is the timeline as last opened or saved, and `timelineName` the name
  // of the opened file, which the saved file's name comes from.
  let history = null;
  let saved = null;
  let timeline = null;
  let timelineName = null;
  // Counts the batches of files taken; one still reading its timeline gives way to a later one.
  let latestBatch = 0;
  // While a select of the picker has focus or the pointer is pressed on it, the index of the
  // segment that was current when that began; null otherwise. Playback moving on then neither
  // rewrites the picker nor moves its edits to the next chord.
  let pinned = null;
  let keyLabel = null;
  let xAt = null; // a time's x on the strip, set by renderTimeline
  let buttons = [];
  let current = null;
  let tabStop = null;
  let audioUrl = null;
  let idleTime = 0; // the position when there is no recording to play
  let looping = false;
  let turnTarget = 0;
  let turnUntil = 0;
  let chordStrikes = [];
  let chordVoicings = [];
  let playChords = false;
  let context = null;
  let chordBus = null;
  let session = null; // the notes of one unbroken stretch of playback, faded out together
  let audition = null; // a chord sounded once while paused
  let ticker = null;
  let nextStrike = 0;

  // Messages add up while one batch of files loads, so a skipped file isn't hidden by an error.
  function say(text) {
    const line = document.createElement("p");
    line.textContent = text;
    $("messages").append(line);
    $("status").hidden = false;
  }

  function clearMessages() {
    $("messages").replaceChildren();
    $("status").hidden = true;
  }

  // A batch of dropped or picked files opens whole or not at all, so the recording and the
  // timeline shown are always a pair the user chose together. Its timeline is read and checked
  // before anything changes, and unsaved edits go only when the user says so. A recording on its
  // own replaces just the recording, which loses no edit.
  async function takeFiles(list) {
    // Copied before the first await: the picker empties its live list right after this call.
    const files = [...list];
    clearMessages();
    let recording = null;
    let timelineFile = null;
    const unknown = [];
    const extra = [];
    for (const file of files) {
      if (/\.json$/i.test(file.name) || file.type === "application/json") {
        if (timelineFile) extra.push(file.name);
        else timelineFile = file;
      } else if (file.type.startsWith("audio/") || AUDIO_NAME.test(file.name)) {
        if (recording) extra.push(file.name);
        else recording = file;
      } else {
        unknown.push(file.name);
      }
    }
    if (unknown.length) say(`Skipped ${unknown.join(", ")}: not a recording or a .chords.json.`);
    if (extra.length) {
      say(`Skipped ${extra.join(", ")}: one recording and one timeline open at a time.`);
    }
    // Only a batch with something to open takes over from one still being read.
    if (!recording && !timelineFile) return;
    const batch = ++latestBatch;
    let opened = null;
    if (timelineFile) {
      const read = await readTimeline(timelineFile);
      if (batch !== latestBatch) return;
      if (read.problem) {
        say(read.problem);
        return;
      }
      opened = read.timeline;
      const names = [recording, timelineFile].filter(Boolean).map((file) => file.name);
      if (dirty() && !confirm(`Discard unsaved edits and open ${names.join(" and ")}?`)) {
        say(`Didn't open ${names.join(" and ")}: kept the unsaved edits.`);
        return;
      }
    }
    if (recording) loadAudio(recording);
    if (opened) installTimeline(opened, timelineFile.name);
  }

  // The timeline in `file`, checked and upgraded to schema 9, or the reason it can't be shown.
  async function readTimeline(file) {
    let data;
    try {
      data = JSON.parse(await file.text());
    } catch (error) {
      return { problem: `Couldn't read ${file.name} as JSON (${error.message}).` };
    }
    // A file the checks didn't foresee can make them throw; that too opens nothing.
    try {
      const problem = Core.timelineProblem(data);
      if (problem) return { problem: `${file.name}: ${problem}` };
      // Opening doesn't re-analyze: the analyzer's fields stand until the first edit.
      return { timeline: Edit.upgrade(data) };
    } catch (error) {
      return { problem: `${file.name}: This timeline can't be shown (${error.message}).` };
    }
  }

  // A long name is cut before its extensions, which always show: they are where a recording and
  // its timeline differ (.mp3, .chords.json, .prototype.chords.json). A `note` after the name
  // always shows too.
  function showName(id, name, note = "") {
    const extensions = /(\.[^.\s]+)+$/.exec(name);
    const cut = extensions ? extensions.index : name.length;
    const head = document.createElement("span");
    const tail = document.createElement("span");
    head.textContent = name.slice(0, cut);
    tail.textContent = name.slice(cut) + (note && ` · ${note}`);
    $(id).replaceChildren(head, tail);
    $(id).title = name;
    $("files").hidden = false;
  }

  function loadAudio(file) {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioUrl = URL.createObjectURL(file);
    audio.src = audioUrl;
    audio.hidden = false;
    $("no-audio").hidden = true;
    $("listen").hidden = false;
    for (const hint of document.querySelectorAll(".needs-recording")) hint.hidden = false;
    showName("audio-name", file.name);
  }

  // A timeline from readTimeline, shown with a fresh history and nothing unsaved.
  function installTimeline(opened, name) {
    // A new timeline ends a pick in progress: the picker's pinned segment belongs to the old one.
    if ($("editor").contains(document.activeElement)) document.activeElement.blur();
    history = Edit.history(opened);
    saved = opened;
    timelineName = name;
    showName("json-name", name, Core.engineText(opened));
    $("empty").hidden = true;
    $("viewer").hidden = false;
    strip.scrollLeft = 0;
    refreshView();
    checkDurations();
  }

  // Edits since the timeline was opened or last saved. Undoing back to that point gives back the
  // very object `saved` holds (see Edit.history), so that is clean again.
  function dirty() {
    return history !== null && history.present !== saved;
  }

  // Saving downloads a new file named after the recording (Edit.saveName): the page never writes
  // to the file it opened, so what the analyzer wrote stays as it was. The object URL is revoked
  // a tick later, once the download has started.
  function save() {
    const name = Edit.saveName(history.present, timelineName);
    const blob = new Blob([Edit.serialize(history.present)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url));
    saved = history.present;
    refreshEditor();
    $("announce").textContent = `Saved ${name}`;
  }

  // Draw everything that comes from the timeline again, from history.present: after opening a
  // file, an edit, or a step through the history. The strip keeps its scroll position, a focused
  // chord keeps the focus, and the chord sound picks up from where the recording is.
  function refreshView(announcement = "") {
    timeline = history.present;
    keyLabel = timeline.key ? timeline.key.label : null;
    chordStrikes = Core.strikes(timeline);
    chordVoicings = Core.voicings(timeline.segments);
    // Mid-play, the strike under way starts again at once with what is left of it, so an edit to
    // the chord sounding now is heard right away. Paused, a chord still sounding from a click or
    // an edit is the old timeline's, so it stops; commitEdit and stepHistory sound the new one.
    stopChords();
    if (audition) fadeOut(audition);
    audition = null;
    startChords();
    renderKey();
    const focused = strip.contains(document.activeElement);
    renderTimeline();
    // The pin lasts only while a picker select has focus. A touch that scrolls the page from a
    // select pins it without focusing it, and an edit can move the segments under a stale pin.
    if (!document.activeElement.closest(".pick")) pinned = null;
    current = null;
    update();
    if (focused && buttons[current]) buttons[current].focus({ preventScroll: true });
    $("announce").textContent = announcement;
  }

  // The one way an edit enters the history. Undo and redo step through it without this, so they
  // never add a step or clear what there is to redo. Paused with the chords on, the chord now in
  // place sounds once, as a click on it would.
  function commitEdit(next, announcement) {
    if (next === history.present) return;
    history = Edit.commit(history, next);
    refreshView(announcement);
    auditionChord(current);
  }

  // Undo (Edit.undo) or redo (Edit.redo), announced as `verb` with the chord now under the
  // playhead. With nothing to step to, nothing changes. Paused with the chords on, that chord
  // sounds once, as after an edit.
  function stepHistory(move, verb) {
    const next = move(history);
    if (next === history) return;
    history = next;
    refreshView();
    const segment = timeline.segments[current];
    $("announce").textContent = segment ? `${verb}: ${nameOf(segment)}` : verb;
    auditionChord(current);
  }

  // A segment's chord as the strip names it, in the key in force.
  function nameOf(segment) {
    return Core.chordName(segment.chord, keyLabel, segment.bass, segment.inversion);
  }

  // The beat under the playhead at time `t`, when it lies strictly inside the chord there: the
  // one place a split can go. Null on a chord's first beat, before the first beat, and in a
  // one-beat chord.
  function splitPoint(t = now()) {
    const index = currentIndex(t);
    const segment = timeline.segments[index];
    const beat = Core.beatIndexAt(timeline.beats, t);
    if (!segment || beat <= segment.start_beat || beat >= segment.end_beat) return null;
    return { index, beat };
  }

  function splitAt(t) {
    const point = splitPoint(t);
    if (!point) return;
    const name = nameOf(timeline.segments[point.index]);
    const next = Edit.split(timeline, point.index, point.beat);
    commitEdit(next, `Split ${name} at beat ${point.beat + 1}`);
  }

  // The chord at `index` merged with the one before (`step` -1) or after (1); the chord at `index`
  // keeps its chord and bass over both spans.
  function mergeWith(index, step) {
    const survivor = timeline.segments[index];
    const other = timeline.segments[index + step];
    if (!survivor || !other) return;
    const next = Edit.merge(timeline, index, index + step);
    commitEdit(next, `Merged ${nameOf(survivor)} with ${nameOf(other)}`);
  }

  function deleteAt(index) {
    const segment = timeline.segments[index];
    if (segment) commitEdit(Edit.remove(timeline, index), `Deleted ${nameOf(segment)}`);
  }

  // The key select: a label fixes the key, "" (Estimated) estimates it again.
  function setKey(label) {
    const next = Edit.setKey(timeline, label || null);
    const name = next.key ? Core.keyName(next.key.label) : "none";
    commitEdit(next, label ? `Key set to ${name}` : `Key estimated: ${name}`);
  }

  // A segment's chord and bass, as the picker or a candidate sets them.
  function setChord(index, chord, bass) {
    const next = Edit.setChord(timeline, index, chord, bass);
    if (next === timeline) return; // a timeline with no segments: nothing to set
    const segment = next.segments[index];
    const key = next.key ? next.key.label : null;
    const name = Core.chordName(segment.chord, key, segment.bass, segment.inversion);
    commitEdit(next, `Chord set to ${name}`);
  }

  // The bass the Bass select reads for a chord on `root`: Root follows the chord's root, so a
  // root or quality change carries it along; None is no bass; a note stays as it is.
  function pickedBass(root) {
    const value = $("edit-bass").value;
    if (value === "root") return root;
    return value === "none" ? null : value;
  }

  // A pick applies at once, to the chord the picker shows (see `pinned`). Over silence the picker
  // reads a root, No chord and Root, so a root or bass picked there also makes the chord major:
  // entering a chord into silence is one pick.
  function applyPicker(event) {
    const quality = $("edit-quality");
    if (event.currentTarget !== quality && quality.value === "N") quality.value = "maj";
    const root = $("edit-root").value;
    const chord = quality.value === "N" ? "N" : `${root}:${quality.value}`;
    setChord(pinned ?? current, chord, pickedBass(root));
  }

  // Files are paired by the user, so a length mismatch is the one hint that they don't belong
  // together.
  function checkDurations() {
    const expected = timeline && timeline.source && timeline.source.duration;
    if (typeof expected !== "number" || !Number.isFinite(audio.duration)) return;
    if (Math.abs(audio.duration - expected) > 1) {
      say(
        `The recording is ${Core.formatTime(audio.duration)} long, but the chord timeline covers ` +
          `${Core.formatTime(expected)}. Check that the two files belong together.`,
      );
    }
  }

  // The key, given (by --key or the select) or estimated. `candidates` is the estimator's ranking
  // either way, so its first is what choosing Estimated gives; it is empty with no chord.
  function renderKey() {
    const key = timeline.key;
    const candidates = key ? key.candidates : [];
    const given = key?.source === "given";
    $("key-name").textContent = key ? Core.keyName(key.label) : "None";
    const select = $("key-select");
    const estimate = candidates.length ? Core.keyName(candidates[0]) : "no chords";
    select.options[0].textContent = `Estimated (${estimate})`;
    select.value = given ? key.label : "";
    // Given, the candidates' heading says so; the line above them is for the other cases.
    $("key-source").hidden = given && candidates.length > 0;
    $("key-source").textContent = candidates.length
      ? "Estimated from the chords."
      : "The timeline has no chords.";
    $("key-candidates-label").textContent = given
      ? "Given; the chords suggest:"
      : "Ranked candidates";
    $("key-candidates-label").hidden = candidates.length === 0;
    $("key-candidates").replaceChildren(
      ...candidates.map((label) => {
        const item = document.createElement("li");
        item.textContent = Core.keyName(label);
        return item;
      }),
    );
  }

  function place(element, start, end) {
    const left = xAt(start);
    element.style.left = `${left}px`;
    if (end !== undefined) element.style.width = `${xAt(end) - left}px`;
  }

  function renderNumeral(element, segment) {
    element.replaceChildren();
    if (!segment.numeral) return;
    const parts = Core.numeralParts(segment.numeral, segment.inversion);
    element.append(parts.accidental + parts.roman + parts.quality);
    if (parts.figures.length) {
      const figures = document.createElement("span");
      figures.className = "figures";
      for (const figure of parts.figures) {
        const digit = document.createElement("span");
        digit.textContent = figure;
        figures.append(digit);
      }
      element.append(figures);
    }
    if (parts.target) element.append(`/${parts.target}`);
  }

  // Figures read one by one ("V 6 5 of V"), not as a number, and quality markers as words
  // ("ii half-diminished seventh 4 3"), which already say seventh, so a root-position 7 is dropped.
  function spokenNumeral(segment) {
    const parts = Core.numeralParts(segment.numeral, segment.inversion);
    const words = QUALITY_WORDS[parts.suffix];
    const figures = words ? parts.figures.filter((figure) => figure !== "7") : parts.figures;
    const head = [parts.accidental + parts.roman, words, ...figures].filter(Boolean).join(" ");
    return parts.target ? `${head} of ${parts.target}` : head;
  }

  function renderTimeline() {
    const { beats, segments } = timeline;
    // Every beat gets PX_PER_BEAT, not every second, so a one-beat chord has room for its name at
    // any tempo, and through a tempo change too: the ruler's seconds spread or bunch instead.
    const origin = Core.beatPosition(beats, 0);
    xAt = (t) => PX_PER_BEAT * (Core.beatPosition(beats, t) - origin);
    const last = segments[segments.length - 1];
    const duration = (timeline.source && timeline.source.duration) || (last ? last.end_time : 0);
    $("track").style.width = `${xAt(duration)}px`;

    buttons = segments.map((segment, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "segment";
      button.tabIndex = -1;
      button.dataset.index = index;
      button.dataset.role = segment.role || "none";
      if (segment.edited) button.dataset.edited = "";
      place(button, segment.start_time, segment.end_time);
      const name = Core.chordName(segment.chord, keyLabel, segment.bass, segment.inversion);
      const chord = document.createElement("span");
      chord.className = "segment-chord";
      // A slash chord too long for its cell breaks before the slash, and only there. The longest
      // heads (D♯m7♭5, B♭maj7) also take smaller type in a one-beat cell (style.css).
      const [head, bass] = name.split("/");
      chord.append(head);
      if (bass) {
        const slash = document.createElement("span");
        slash.textContent = `/${bass}`;
        chord.append(document.createElement("wbr"), slash);
      }
      chord.classList.toggle("long", head.length > 5);
      const numeral = document.createElement("span");
      numeral.className = "segment-numeral";
      renderNumeral(numeral, segment);
      // A numeral with a quality marker (♭VIImaj7, viiø7/VII) takes smaller type in a one-beat cell;
      // a one-character suffix (V+, vii°, V7) keeps the normal size.
      if (segment.numeral) {
        const parts = Core.numeralParts(segment.numeral, segment.inversion);
        numeral.classList.toggle("long", parts.suffix.length > 1);
      }
      button.append(chord, numeral);
      button.title = segment.numeral
        ? `${name}  ${Core.numeralText(segment.numeral, segment.inversion)}`
        : name;
      const spoken = segment.numeral ? spokenNumeral(segment) : "";
      const label = [
        name,
        spoken,
        Core.formatTime(segment.start_time),
        segment.edited && "edited",
      ].filter(Boolean);
      button.setAttribute("aria-label", label.join(", "));
      return button;
    });
    $("segments").replaceChildren(...buttons);
    tabStop = null;

    const marks = beats.map((beat) => {
      const tick = document.createElement("i");
      place(tick, beat);
      return tick;
    });
    for (let second = 0; second <= duration; second += RULER_STEP) {
      const time = document.createElement("span");
      time.textContent = Core.formatTime(second);
      place(time, second);
      marks.push(time);
    }
    $("ruler").replaceChildren(...marks);
  }

  function roleText(segment) {
    if (segment.role === "secondary_dominant" && segment.target) {
      // The role covers viiø7/x, vii°7/x and vii°/x too, which lead up to their target rather than
      // down.
      const quality = segment.chord.split(":")[1];
      const leadingTone = quality === "dim7" || quality === "hdim7" || quality === "dim";
      const target = Core.targetName(segment.chord, segment.target, keyLabel, leadingTone);
      const kind = leadingTone ? "Leading-tone chord" : "Secondary dominant";
      return `${kind} of ${segment.target} (${target})`;
    }
    if (segment.role === "borrowed") {
      return `Borrowed from the parallel ${keyLabel.endsWith(":maj") ? "minor" : "major"}`;
    }
    // Every diatonic chord has a function, and only diatonic chords do.
    if (segment.function) return `Diatonic, ${segment.function} function`;
    return "Chromatic";
  }

  function renderNow(segment) {
    const isChord = segment.chord !== "N";
    document.querySelector(".now").dataset.role = segment.role || "none";
    $("now-chord").textContent = Core.chordName(
      segment.chord,
      keyLabel,
      segment.bass,
      segment.inversion,
    );
    fitBigChord();
    renderNumeral($("now-numeral"), segment);
    // Every row always shows, so the panel doesn't jump on chord changes.
    $("now-role").textContent = isChord ? roleText(segment) : "No chord";
    const bass = Core.bassName(segment.chord, keyLabel, segment.bass);
    $("now-bass").textContent = bass ? `${bass}, ${INVERSION_TEXT[segment.inversion]}` : "None heard";
    $("now-edited").hidden = !segment.edited;
    $("now-alt-label").textContent = segment.edited ? "Analyzer heard" : "Also heard as";
    renderCandidates(segment);
    renderPicker(pinned === null ? segment : timeline.segments[pinned]);
  }

  // The picker shows the segment. Over silence it still holds a root, the key's tonic, so a
  // quality picked there makes a chord on it.
  function renderPicker(segment) {
    const isChord = segment.chord !== "N";
    const [root, quality] = isChord
      ? segment.chord.split(":")
      : [keyLabel ? keyLabel.split(":")[0] : "C", "N"];
    $("edit-root").value = root;
    $("edit-quality").value = quality;
    // The root's own note is what Root reads, so it is not offered twice. Arrowing through the
    // notes (a pick per step on Windows and Linux) then passes it instead of snapping back to
    // Root, and reaches every note after it and None. A root moved onto a fixed bass note makes
    // that bass Root from then on.
    const bass = $("edit-bass");
    for (const option of bass.options) option.disabled = option.value === root;
    bass.value =
      !isChord || segment.bass === root ? "root" : segment.bass === null ? "none" : segment.bass;
  }

  // The analyzer's other readings, each a button that makes it the chord. Once the chord is the
  // user's, everything it heard is on offer, its first reading included, bar the chord itself.
  function renderCandidates(segment) {
    const list = $("now-alt");
    const labels = segment.edited
      ? segment.candidates.filter((label) => label !== segment.chord)
      : segment.candidates.slice(1);
    // A focused candidate keeps the focus at its place in the list, when a keyboard click or
    // playback moving on draws the list again.
    const focused = [...list.querySelectorAll(".candidate")].indexOf(document.activeElement);
    list.replaceChildren(
      ...labels.map((label) => {
        const item = document.createElement("span");
        const button = document.createElement("button");
        const name = Core.alternativeName(label, segment.chord, keyLabel);
        const sameNotes = Core.sameNotes(label, segment.chord);
        const action = `Set chord to ${name}${sameNotes ? ", same notes" : ""}`;
        button.type = "button";
        button.className = "button candidate";
        button.textContent = name;
        button.setAttribute("aria-label", action);
        button.title = action;
        button.addEventListener("click", (event) => {
          releaseFocus(event);
          setChord(current, label, label === "N" ? null : pickedBass(label.split(":")[0]));
        });
        item.append(button);
        if (sameNotes) {
          // The button's name already says it.
          const note = document.createElement("span");
          note.setAttribute("aria-hidden", "true");
          note.textContent = " (same notes)";
          item.append(note);
        }
        return item;
      }),
    );
    const choices = list.querySelectorAll(".candidate");
    if (focused >= 0 && choices.length) {
      choices[Math.min(focused, choices.length - 1)].focus({ preventScroll: true });
    }
  }

  // A long name (D♯m7♭5/C♯) is wider than the chord column at full size; it shrinks to fit rather
  // than lose its bass. Text width is proportional to the font size, so one measurement sets it.
  // The line keeps its height, so the rows below don't move when such a name comes up.
  function fitBigChord() {
    const element = $("now-chord");
    element.style.fontSize = "";
    element.style.lineHeight = "";
    const overflow = element.scrollWidth / element.clientWidth;
    if (!(overflow > 1)) return;
    const size = parseFloat(getComputedStyle(element).fontSize);
    element.style.lineHeight = `${size}px`;
    element.style.fontSize = `${Math.floor(size / overflow)}px`;
  }

  function show(index) {
    if (current !== null && buttons[current]) buttons[current].classList.remove("current");
    current = index;
    const button = buttons[index];
    if (!button) return;
    button.classList.add("current");
    // One tab stop for the whole timeline, on the current chord.
    if (tabStop) tabStop.tabIndex = -1;
    button.tabIndex = 0;
    tabStop = button;
    renderNow(timeline.segments[index]);
  }

  function now() {
    return audioUrl ? audio.currentTime : idleTime;
  }

  function currentIndex(t = now()) {
    // The head before the first beat is shorter than a beat, so it shows the first chord rather
    // than nothing.
    return Math.max(0, Core.segmentIndexAt(timeline.segments, t));
  }

  function update() {
    if (!timeline) return;
    const x = xAt(now());
    $("playhead").style.transform = `translateX(${x}px)`;
    const index = currentIndex();
    if (index !== current) show(index);
    follow(x);
    refreshEditor();
  }

  // What the edit buttons can do from here. Split depends on the beat under the playhead, not just
  // the chord, so this runs on every update, not only when the chord changes.
  function refreshEditor() {
    const { segments } = timeline;
    const segment = segments[current];
    const splittable = splitPoint() !== null;
    let splitTitle = "Split this chord at the beat under the playhead";
    if (!splittable && segment && segment.end_beat - segment.start_beat === 1) {
      splitTitle = "This chord is one beat long; there is nowhere inside it to split";
    } else if (!splittable) {
      splitTitle = "Step to a beat inside this chord to split it there (Shift+← or Shift+→)";
    }
    setButton("split", splittable, splitTitle);
    setButton("merge-before", segments[current - 1] !== undefined);
    setButton("merge-after", segments[current + 1] !== undefined);
    const lone = segments.length < 2;
    setButton(
      "delete",
      !lone,
      lone
        ? "The only chord can't be deleted; set it to No chord instead"
        : `Delete this chord; the chord ${current === 0 ? "after" : "before"} takes its beats`,
    );
    setButton("undo", history.past.length > 0);
    setButton("redo", history.future.length > 0);
    // Save takes its unsaved look from this text being shown (style.css).
    const unsaved = dirty();
    if ($("unsaved").hidden === unsaved) $("unsaved").hidden = !unsaved;
  }

  // aria-disabled rather than disabled, so a button stays focusable: a keyboard click that rules
  // out its own next use (Split after a split, Undo at the oldest step) keeps the focus there,
  // and the title saying why can still be reached. Each action does nothing where it doesn't
  // apply. This runs every frame, so only a change touches the DOM and the accessibility tree.
  function setButton(id, enabled, title) {
    const button = $(id);
    const disabled = String(!enabled);
    if (button.getAttribute("aria-disabled") !== disabled) {
      button.setAttribute("aria-disabled", disabled);
    }
    if (title !== undefined && button.title !== title) button.title = title;
  }

  // Turn the page when the playhead leaves the view, instead of scrolling every frame: the chords
  // ahead stay still long enough to read.
  function follow(x) {
    const width = strip.clientWidth;
    const left = performance.now() < turnUntil ? turnTarget : strip.scrollLeft;
    if (x >= left && x <= left + width * 0.85) return;
    turnTarget = Math.max(0, x - width * 0.15);
    turnUntil = performance.now() + 600;
    // A long seek jumps: smooth-scrolling through minutes of chords is only a blur.
    const jump = reducedMotion.matches || Math.abs(turnTarget - strip.scrollLeft) > width;
    strip.scrollTo({ left: turnTarget, behavior: jump ? "auto" : "smooth" });
  }

  function frame() {
    update();
    looping = !audio.paused;
    if (looping) requestAnimationFrame(frame);
  }

  function seekTime(t) {
    if (audioUrl) audio.currentTime = t + SEEK_NUDGE;
    else idleTime = t;
    update();
  }

  function seek(index) {
    const segment = timeline.segments[index];
    if (!segment) return;
    seekTime(segment.start_time);
    auditionChord(index);
  }

  // Shift+← and Shift+→: to the beat before or after the one under the playhead, so a split point
  // can be reached without a mouse, and with no recording open.
  function stepBeat(step) {
    const { beats } = timeline;
    const beat = Core.beatIndexAt(beats, now()) + step;
    if (beat >= 0 && beat < beats.length) seekTime(beats[beat]);
  }

  function togglePlay() {
    if (!audioUrl) return;
    if (audio.paused) {
      audio.play().catch((error) => say(`Couldn't play the recording: ${error.message}`));
    } else {
      audio.pause();
    }
  }

  // Squared, so the slider sounds even. Measured on a mastered track, the default (80) sits about
  // 9 dB under the recording; at the top, a seventh chord with every wave in phase stays short of
  // clipping.
  function chordGain() {
    return (Number($("chord-volume").value) / 100) ** 2;
  }

  // First called from the toggle, a user gesture, so the autoplay policy lets the context run.
  function ensureContext() {
    if (!context) {
      context = new AudioContext();
      chordBus = new GainNode(context, { gain: chordGain() });
      // Takes the edge off the triangle waves, so the chords sit under the recording.
      const lowpass = new BiquadFilterNode(context, { type: "lowpass", frequency: 1800 });
      chordBus.connect(lowpass).connect(context.destination);
    }
    if (context.state === "suspended") {
      context.resume().catch((error) => say(`Couldn't start the chord sound: ${error.message}`));
    }
  }

  // The recording's clock is moving: not paused, not mid-seek, not stalled waiting for data.
  function clockRunning() {
    return !audio.paused && !audio.seeking && audio.readyState >= audio.HAVE_FUTURE_DATA;
  }

  function startChords() {
    if (ticker || !playChords || !timeline || !audioUrl || !clockRunning()) return;
    ensureContext();
    if (audition) fadeOut(audition);
    audition = null;
    session = new GainNode(context);
    session.connect(chordBus);
    // Mid-beat, the chord sounding now starts at once rather than waiting for the next beat.
    nextStrike = Core.strikeIndexAt(chordStrikes, audio.currentTime);
    ticker = setInterval(scheduleChords, TICK_MS);
    scheduleChords();
  }

  // On pause, seek, stall, rate change or the toggle: fade out everything sounding or queued. The
  // next start finds its place afresh, so a long seek can't release a burst of stale notes.
  function stopChords() {
    clearInterval(ticker);
    ticker = null;
    if (session) fadeOut(session);
    session = null;
  }

  // Fade rather than cut, so stopping never clicks; unhook once the fade is long over.
  function fadeOut(node) {
    node.gain.setTargetAtTime(0, context.currentTime, 0.01);
    setTimeout(() => node.disconnect(), 1000);
  }

  // Paused, a chord you click or step to sounds once, so it can be checked on its own. This has
  // its own gain, since the seek's own events stop the playback session right after.
  function auditionChord(index) {
    const voicing = chordVoicings[index];
    if (!playChords || !voicing || !audioUrl || !audio.paused) return;
    ensureContext();
    if (audition) fadeOut(audition);
    audition = new GainNode(context);
    audition.connect(chordBus);
    const segment = timeline.segments[index];
    const now = context.currentTime;
    strikeChord(voicing, now, now + Math.min(segment.end_time - segment.start_time, 1.5), audition);
  }

  function scheduleChords() {
    // pause() and seeks stop the clock at once but send their events later: skip that gap.
    if (context.state !== "running" || !clockRunning()) return;
    const now = context.currentTime;
    const { due, next } = Core.dueStrikes(chordStrikes, nextStrike, {
      media: audio.currentTime,
      rate: audio.playbackRate,
      lookahead: LOOKAHEAD,
      // A note scheduled now is heard this much later, while the recording's currentTime already
      // allows for its own output delay. outputLatency is missing in some browsers.
      lag: (context.baseLatency || 0) + (context.outputLatency || 0),
    });
    nextStrike = next;
    for (const strike of due) {
      strikeChord(chordVoicings[strike.segment], now + strike.start, now + strike.end, session);
    }
  }

  // A soft, clearly pitched voice per note: a triangle and a slightly detuned sine, a quick attack,
  // a decay toward a lower sustain, and a fade just before the next beat so each strike is heard.
  function strikeChord(voicing, start, end, destination) {
    const release = Math.max(start + ATTACK, end - 0.05);
    const notes = [[voicing.bass, 0.1], ...voicing.notes.map((note) => [note, 0.07])];
    for (const [note, level] of notes) {
      const envelope = new GainNode(context, { gain: 0 });
      envelope.gain.setValueAtTime(0, start);
      envelope.gain.linearRampToValueAtTime(level, start + ATTACK);
      envelope.gain.setTargetAtTime(level * 0.4, start + ATTACK, 0.3);
      envelope.gain.setTargetAtTime(0, release, RELEASE);
      envelope.connect(destination);
      const frequency = 440 * 2 ** ((note - 69) / 12);
      const oscillators = [
        ["triangle", -4],
        ["sine", 4],
      ].map(([type, detune]) => {
        const oscillator = new OscillatorNode(context, { type, frequency, detune });
        oscillator.connect(envelope);
        oscillator.start(start);
        oscillator.stop(release + RELEASE * 8);
        return oscillator;
      });
      // Both stop together; unhooking the envelope then keeps a long song from piling up nodes.
      oscillators[0].onended = () => envelope.disconnect();
    }
  }

  function setPlayChords(on) {
    playChords = on;
    $("play-chords").setAttribute("aria-pressed", String(on));
    if (on) {
      ensureContext();
      startChords();
      // Paused, turning it on sounds the current chord, so it's never on and silent.
      if (timeline) auditionChord(currentIndex());
    } else {
      stopChords();
      if (audition) fadeOut(audition);
      audition = null;
      // Idle, the context would keep the audio device busy. Suspend once the fade is done.
      setTimeout(() => {
        if (!playChords) context.suspend();
      }, 200);
    }
  }

  // After a mouse click, focus leaves the button, so Space goes back to playing and pausing.
  // A keyboard click (detail 0) keeps it there.
  function releaseFocus(event) {
    if (event.detail > 0) event.currentTarget.blur();
  }

  function toggleMute() {
    audio.muted = !audio.muted;
  }

  for (const button of document.querySelectorAll(".open-files")) {
    button.addEventListener("click", (event) => {
      releaseFocus(event);
      picker.click();
    });
  }
  $("dismiss").addEventListener("click", clearMessages);
  // The column narrows with the window, and the accidentals' font can arrive after the first fit.
  addEventListener("resize", fitBigChord);
  document.fonts.addEventListener("loadingdone", fitBigChord);
  picker.addEventListener("change", () => {
    takeFiles(picker.files);
    picker.value = ""; // so choosing the same file again still fires change
  });

  $("segments").addEventListener("click", (event) => {
    const button = event.target.closest(".segment");
    if (button) seek(Number(button.dataset.index));
  });

  // A pick takes a moment (a menu is open, or the arrows step through it), and playback may move
  // on meanwhile: the picker stays on the chord it showed when the press or the focus began, and
  // lets go when the select loses focus. Picked with the mouse, a select lets go of focus as the
  // buttons do, so Space goes back to playing and pausing; picked from the keyboard, it keeps it.
  let pointerPick = false;
  const pin = () => {
    if (pinned === null) pinned = current;
  };
  for (const id of ["edit-root", "edit-quality", "edit-bass"]) {
    const select = $(id);
    select.addEventListener("pointerdown", () => {
      pointerPick = true;
      pin();
    });
    select.addEventListener("focus", pin);
    select.addEventListener("blur", () => {
      pinned = null;
      show(current);
    });
    // A touch that scrolls the page from the select pins it but never focuses it, so no blur
    // lets go.
    select.addEventListener("pointercancel", () => {
      if (document.activeElement === select) return;
      pinned = null;
      show(current);
    });
    select.addEventListener("keydown", () => (pointerPick = false));
    select.addEventListener("change", (event) => {
      applyPicker(event);
      if (pointerPick) select.blur();
    });
  }

  // The key select lists the 24 keys after Estimated, in the analyzer's order, named as the page
  // names keys. It lets go of focus after a mouse pick as the picker's selects do.
  const keySelect = $("key-select");
  keySelect.append(...Harmony.KEYS.map((label) => new Option(Core.keyName(label), label)));
  keySelect.addEventListener("pointerdown", () => (pointerPick = true));
  keySelect.addEventListener("keydown", () => (pointerPick = false));
  keySelect.addEventListener("change", () => {
    setKey(keySelect.value);
    if (pointerPick) keySelect.blur();
  });

  // An edit button acts on the moment its press began: during playback the click comes a moment
  // later, maybe on the next beat or chord. A click with no press of its own (from assistive
  // technology) acts on the moment of the click.
  let pressedAt = null;
  const actions = {
    split: splitAt,
    "merge-before": (t) => mergeWith(currentIndex(t), -1),
    "merge-after": (t) => mergeWith(currentIndex(t), 1),
    delete: (t) => deleteAt(currentIndex(t)),
    undo: () => stepHistory(Edit.undo, "Undo"),
    redo: () => stepHistory(Edit.redo, "Redo"),
  };
  for (const [id, action] of Object.entries(actions)) {
    const button = $(id);
    const press = () => (pressedAt = now());
    button.addEventListener("pointerdown", press);
    button.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") press();
    });
    button.addEventListener("click", (event) => {
      const t = pressedAt ?? now();
      pressedAt = null;
      releaseFocus(event);
      action(t);
    });
  }
  // A press that ends without a click on its button (released off it, or a touch that turned
  // into a scroll) ends here, after any button's own click handler has run.
  document.addEventListener("click", () => (pressedAt = null));
  document.addEventListener("pointercancel", () => (pressedAt = null));

  // Saving is allowed with nothing unsaved too: it writes an opened schema-4 to 8 file as a 9.
  $("save").addEventListener("click", (event) => {
    releaseFocus(event);
    save();
  });
  // Closing or reloading the page would lose the unsaved edits, so the browser asks first.
  addEventListener("beforeunload", (event) => {
    if (!dirty()) return;
    event.preventDefault();
    event.returnValue = true; // what Chrome before 119 asks on instead of preventDefault
  });

  $("play-chords").addEventListener("click", (event) => {
    releaseFocus(event);
    setPlayChords(!playChords);
  });
  $("mute-recording").addEventListener("click", (event) => {
    releaseFocus(event);
    toggleMute();
  });
  $("chord-volume").addEventListener("input", () => {
    if (chordBus) chordBus.gain.setTargetAtTime(chordGain(), context.currentTime, 0.02);
  });
  // Dragged with the mouse, the slider lets go of focus too; from the keyboard it keeps it.
  $("chord-volume").addEventListener("pointerup", (event) => event.currentTarget.blur());
  // The native controls can mute too, so the button follows the element rather than a flag.
  audio.addEventListener("volumechange", () => {
    $("mute-recording").setAttribute("aria-pressed", String(audio.muted));
  });

  // The chords follow the recording's clock: they start when it runs and stop whenever it stops
  // or jumps. A seek is seeking (stop) then seeked (start from the new place).
  audio.addEventListener("playing", startChords);
  audio.addEventListener("seeked", startChords);
  for (const type of ["pause", "seeking", "waiting", "ended", "emptied"]) {
    audio.addEventListener(type, stopChords);
  }
  audio.addEventListener("ratechange", () => {
    stopChords();
    startChords();
  });

  document.addEventListener("keydown", (event) => {
    if (!timeline || event.altKey) return;
    const target = event.target;
    // A select (or a text field) keeps every key: letters pick by name, Space opens it, arrows
    // step through it, and an undo there would pull the chord it picks for out from under it.
    // A select has no use for Backspace, but a WebKit that still goes back a page on it would
    // leave the edits behind, and a keyboard pick keeps the focus on the select.
    if (target.closest("select")) {
      if (event.key === "Backspace") event.preventDefault();
      return;
    }
    if (target.closest("input[type=text]")) return;
    // Letter shortcuts work from every other control; none of them takes letters. The physical
    // key is the fallback, so they also work with a non-Latin layout on (Korean input sends "ㅊ"
    // for C).
    const letter = /^[a-z]$/i.test(event.key)
      ? event.key.toLowerCase()
      : { KeyC: "c", KeyM: "m", KeyS: "s", KeyY: "y", KeyZ: "z" }[event.code];
    if (event.ctrlKey || event.metaKey) {
      // Ctrl+Z or ⌘Z undoes and adds Shift to redo; Ctrl+Y redoes too, as on Windows (⌘Y is the
      // browser's history on a Mac). Every other combination is the browser's.
      const redo = (letter === "z" && event.shiftKey) || (letter === "y" && !event.metaKey);
      if (letter !== "z" && !redo) return;
      event.preventDefault();
      // Held down, an edit key acts once, as C and M do: a held Delete would take several chords.
      if (event.repeat) return;
      if (redo) stepHistory(Edit.redo, "Redo");
      else stepHistory(Edit.undo, "Undo");
      return;
    }
    if (letter === "s") {
      event.preventDefault();
      if (!event.repeat) splitAt(now());
      return;
    }
    // Backspace too, as a Mac keyboard has no Delete key; preventDefault keeps it from going back
    // a page in browsers that still do that.
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      if (!event.repeat) deleteAt(current);
      return;
    }
    if ((letter === "c" || letter === "m") && audioUrl) {
      event.preventDefault();
      if (event.repeat) return;
      // The button that changed doesn't have focus, so say what happened for screen readers.
      if (letter === "c") {
        setPlayChords(!playChords);
        $("announce").textContent = playChords ? "Chords on" : "Chords off";
      } else {
        toggleMute();
        $("announce").textContent = audio.muted ? "Recording muted" : "Recording on";
      }
      return;
    }
    if (event.key === " ") {
      // Buttons and links keep Space (on a chord button it plays rather than seeks). The audio
      // element toggles on Space by itself, as preventDefault doesn't stop it.
      if (target === audio || target.closest("button:not(.segment), a")) return;
      event.preventDefault();
      togglePlay();
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      // The volume slider's and the player's own arrows (on the player, both would seek).
      if (target === audio || target.closest("input")) return;
      event.preventDefault();
      const step = event.key === "ArrowRight" ? 1 : -1;
      if (event.shiftKey) {
        stepBeat(step);
      } else {
        const index = Core.stepIndex(timeline.segments, now(), step);
        if (index < 0) return;
        seek(index);
      }
      if (strip.contains(document.activeElement) && buttons[current]) {
        buttons[current].focus({ preventScroll: true });
      }
    }
  });

  audio.addEventListener("play", () => {
    if (!looping) {
      looping = true;
      requestAnimationFrame(frame);
    }
  });
  for (const type of ["seeking", "seeked", "pause", "ended"]) audio.addEventListener(type, update);
  audio.addEventListener("loadedmetadata", () => {
    update();
    checkDurations();
  });
  audio.addEventListener("error", () => {
    say(`This browser can't play ${$("audio-name").textContent}.`);
  });

  // Drops anywhere on the page. The counter is there because dragleave also fires when the
  // pointer moves between child elements.
  const dropzone = $("dropzone");
  let dragDepth = 0;
  const carriesFiles = (event) => event.dataTransfer && event.dataTransfer.types.includes("Files");
  addEventListener("dragenter", (event) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    dropzone.hidden = false;
  });
  addEventListener("dragover", (event) => {
    if (carriesFiles(event)) event.preventDefault();
  });
  addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) dropzone.hidden = true;
  });
  addEventListener("drop", (event) => {
    event.preventDefault();
    dragDepth = 0;
    dropzone.hidden = true;
    if (event.dataTransfer) takeFiles(event.dataTransfer.files);
  });
})();
