// The viewer's DOM side: opening files, the timeline, the current-chord panel and playback.
// A classic script like core.js (see there for why); both are deferred, so core.js runs first.
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

  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const strip = $("strip");
  const picker = $("picker");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

  let timeline = null;
  let keyLabel = null;
  let pxPerSecond = 0;
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
  let hearChords = false;
  let context = null;
  let chordBus = null;
  let session = null; // the notes of one unbroken stretch of playback, faded out together
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

  function takeFiles(files) {
    clearMessages();
    const skipped = [];
    for (const file of files) {
      if (/\.json$/i.test(file.name) || file.type === "application/json") loadTimeline(file);
      else if (file.type.startsWith("audio/") || AUDIO_NAME.test(file.name)) loadAudio(file);
      else skipped.push(file.name);
    }
    if (skipped.length) say(`Skipped ${skipped.join(", ")}: not a recording or a .chords.json.`);
  }

  // A long name is cut before its extensions, which always show: they are where a recording and
  // its timeline differ (.mp3, .chords.json, .prototype.chords.json).
  function showName(id, name) {
    const extensions = /(\.[^.\s]+)+$/.exec(name);
    const cut = extensions ? extensions.index : name.length;
    const head = document.createElement("span");
    const tail = document.createElement("span");
    head.textContent = name.slice(0, cut);
    tail.textContent = name.slice(cut);
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
    showName("audio-name", file.name);
  }

  async function loadTimeline(file) {
    let data;
    try {
      data = JSON.parse(await file.text());
    } catch (error) {
      say(`Couldn't read ${file.name} as JSON (${error.message}).`);
      return;
    }
    const problem = Core.timelineProblem(data);
    if (problem) {
      say(`${file.name}: ${problem}`);
      return;
    }
    timeline = data;
    keyLabel = data.key ? data.key.label : null;
    showName("json-name", file.name);
    renderKey();
    renderTimeline();
    stopChords();
    chordStrikes = Core.strikes(data);
    chordVoicings = Core.voicings(data.segments);
    startChords();
    $("empty").hidden = true;
    $("viewer").hidden = false;
    current = null;
    update();
    checkDurations();
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

  function renderKey() {
    const key = timeline.key;
    $("key-name").textContent = key ? Core.keyName(key.label) : "None";
    if (key && key.source === "given") {
      const flag = document.createElement("code");
      flag.textContent = "--key";
      $("key-source").replaceChildren("Given with ", flag, ".");
    } else {
      $("key-source").textContent = key ? "Estimated from the chords." : "The timeline has no chords.";
    }
    const candidates = key ? key.candidates : [];
    $("key-candidates-label").textContent =
      key && key.source === "given" ? "The chords suggest" : "Ranked candidates";
    $("key-candidates-label").hidden = candidates.length === 0;
    $("key-candidates").replaceChildren(
      ...candidates.map((label) => {
        const item = document.createElement("li");
        item.textContent = Core.keyName(label);
        return item;
      }),
    );
  }

  function medianGap(beats) {
    const gaps = beats.slice(1).map((beat, i) => beat - beats[i]);
    gaps.sort((a, b) => a - b);
    return gaps.length ? gaps[gaps.length >> 1] : 0.5;
  }

  function place(element, start, end) {
    element.style.left = `${start * pxPerSecond}px`;
    if (end !== undefined) element.style.width = `${(end - start) * pxPerSecond}px`;
  }

  function renderNumeral(element, segment) {
    element.replaceChildren();
    if (!segment.numeral) return;
    const parts = Core.numeralParts(segment.numeral, segment.inversion);
    element.append(parts.accidental + parts.roman);
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

  // Figures read one by one ("V 6 5 of V"), not as a number.
  function spokenNumeral(segment) {
    const parts = Core.numeralParts(segment.numeral, segment.inversion);
    const head = [parts.accidental + parts.roman, ...parts.figures].join(" ");
    return parts.target ? `${head} of ${parts.target}` : head;
  }

  function renderTimeline() {
    const { beats, segments } = timeline;
    // Scale by the beat, not the second, so a one-beat chord has room for its name at any tempo.
    pxPerSecond = PX_PER_BEAT / medianGap(beats);
    const last = segments[segments.length - 1];
    const duration = (timeline.source && timeline.source.duration) || (last ? last.end_time : 0);
    $("track").style.width = `${duration * pxPerSecond}px`;

    buttons = segments.map((segment, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "segment";
      button.tabIndex = -1;
      button.dataset.index = index;
      button.dataset.role = segment.role || "none";
      place(button, segment.start_time, segment.end_time);
      const name = Core.chordName(segment.chord, keyLabel, segment.bass, segment.inversion);
      const chord = document.createElement("span");
      chord.className = "segment-chord";
      chord.textContent = name;
      const numeral = document.createElement("span");
      numeral.className = "segment-numeral";
      renderNumeral(numeral, segment);
      button.append(chord, numeral);
      button.title = segment.numeral
        ? `${name}  ${Core.numeralText(segment.numeral, segment.inversion)}`
        : name;
      const spoken = segment.numeral ? spokenNumeral(segment) : "";
      const label = [name, spoken, Core.formatTime(segment.start_time)].filter(Boolean);
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
    strip.scrollLeft = 0;
  }

  function roleText(segment) {
    if (segment.role === "secondary_dominant" && segment.target) {
      const target = Core.targetName(segment.chord, segment.target, keyLabel);
      return `Secondary dominant of ${segment.target} (${target})`;
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
    renderNumeral($("now-numeral"), segment);
    // Every row always shows, so the panel doesn't jump on chord changes.
    $("now-role").textContent = isChord ? roleText(segment) : "No chord";
    const bass = Core.bassName(segment.chord, keyLabel, segment.bass);
    $("now-bass").textContent = bass ? `${bass}, ${INVERSION_TEXT[segment.inversion]}` : "None heard";
    $("now-alt").textContent = segment.candidates
      .slice(1)
      .map((label) => Core.alternativeName(label, segment.chord, keyLabel))
      .join(", ");
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

  function currentIndex() {
    // The head before the first beat is shorter than a beat, so it shows the first chord rather
    // than nothing.
    return Math.max(0, Core.segmentIndexAt(timeline.segments, now()));
  }

  function update() {
    if (!timeline) return;
    const x = now() * pxPerSecond;
    $("playhead").style.transform = `translateX(${x}px)`;
    const index = currentIndex();
    if (index !== current) show(index);
    follow(x);
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

  function seek(index) {
    const segment = timeline.segments[index];
    if (!segment) return;
    if (audioUrl) audio.currentTime = segment.start_time + SEEK_NUDGE;
    else idleTime = segment.start_time;
    update();
  }

  function togglePlay() {
    if (!audioUrl) return;
    if (audio.paused) {
      audio.play().catch((error) => say(`Couldn't play the recording: ${error.message}`));
    } else {
      audio.pause();
    }
  }

  // Squared, so the slider sounds even. Measured on a mastered track, the default (70) sits about
  // 8 dB under the recording, and the top reaches its level for listening to the chords alone
  // with peaks still short of clipping.
  function chordGain() {
    return 1.4 * (Number($("chord-volume").value) / 100) ** 2;
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

  function startChords() {
    if (ticker || !hearChords || !timeline || !audioUrl || audio.paused) return;
    ensureContext();
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
    if (!session) return;
    const old = session;
    old.gain.setTargetAtTime(0, context.currentTime, 0.01);
    setTimeout(() => old.disconnect(), 1000);
    session = null;
  }

  function scheduleChords() {
    if (context.state !== "running") return;
    const media = audio.currentTime;
    const now = context.currentTime;
    const rate = audio.playbackRate;
    while (
      nextStrike < chordStrikes.length &&
      chordStrikes[nextStrike].time < media + LOOKAHEAD * rate
    ) {
      const strike = chordStrikes[nextStrike++];
      if (strike.end <= media) continue; // already over: late is better skipped than stacked
      const start = now + Math.max(0, strike.time - media) / rate;
      strikeChord(chordVoicings[strike.segment], start, now + (strike.end - media) / rate);
    }
  }

  // A soft, clearly pitched voice per note: a triangle and a slightly detuned sine, a quick attack,
  // a decay toward a lower sustain, and a fade just before the next beat so each strike is heard.
  function strikeChord(voicing, start, end) {
    const release = Math.max(start + ATTACK, end - 0.05);
    const notes = [[voicing.bass, 0.1], ...voicing.notes.map((note) => [note, 0.07])];
    for (const [note, level] of notes) {
      const envelope = new GainNode(context, { gain: 0 });
      envelope.gain.setValueAtTime(0, start);
      envelope.gain.linearRampToValueAtTime(level, start + ATTACK);
      envelope.gain.setTargetAtTime(level * 0.4, start + ATTACK, 0.3);
      envelope.gain.setTargetAtTime(0, release, RELEASE);
      envelope.connect(session);
      const frequency = 440 * 2 ** ((note - 69) / 12);
      for (const [type, detune] of [
        ["triangle", -4],
        ["sine", 4],
      ]) {
        const oscillator = new OscillatorNode(context, { type, frequency, detune });
        oscillator.connect(envelope);
        oscillator.start(start);
        oscillator.stop(release + RELEASE * 8);
      }
    }
  }

  function setHearChords(on) {
    hearChords = on;
    $("hear-chords").setAttribute("aria-pressed", String(on));
    if (on) {
      ensureContext();
      startChords();
    } else {
      stopChords();
    }
  }

  function toggleMute() {
    audio.muted = !audio.muted;
  }

  for (const button of document.querySelectorAll(".open-files")) {
    button.addEventListener("click", () => picker.click());
  }
  $("dismiss").addEventListener("click", clearMessages);
  picker.addEventListener("change", () => {
    takeFiles(picker.files);
    picker.value = ""; // so choosing the same file again still fires change
  });

  $("segments").addEventListener("click", (event) => {
    const button = event.target.closest(".segment");
    if (button) seek(Number(button.dataset.index));
  });

  $("hear-chords").addEventListener("click", () => setHearChords(!hearChords));
  $("mute-recording").addEventListener("click", toggleMute);
  $("chord-volume").addEventListener("input", () => {
    if (chordBus) chordBus.gain.setTargetAtTime(chordGain(), context.currentTime, 0.02);
  });
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
    if (!timeline || event.altKey || event.ctrlKey || event.metaKey) return;
    // Letter shortcuts work from any control; none of them takes letters.
    const letter = event.key.toLowerCase();
    if ((letter === "h" || letter === "m") && audioUrl) {
      if (!event.repeat) {
        if (letter === "h") setHearChords(!hearChords);
        else toggleMute();
      }
      return;
    }
    // Other controls keep their own keys. On a chord button Space plays rather than seeks. The
    // audio element toggles on Space by itself (preventDefault doesn't stop it), but its arrows
    // step chords here like everywhere else.
    if (event.target.closest("button:not(.segment), input, a")) return;
    if (event.key === " " && event.target !== audio) {
      event.preventDefault();
      togglePlay();
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const step = event.key === "ArrowRight" ? 1 : -1;
      const index = Math.min(buttons.length - 1, Math.max(0, currentIndex() + step));
      seek(index);
      if (strip.contains(document.activeElement)) buttons[index].focus({ preventScroll: true });
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
