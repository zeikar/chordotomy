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
  const ROLE_TEXT = { diatonic: "Diatonic", chromatic: "Chromatic" };
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

  function say(text) {
    $("status").textContent = text || "";
    $("status").hidden = !text;
  }

  function takeFiles(files) {
    say(null);
    const skipped = [];
    for (const file of files) {
      if (/\.json$/i.test(file.name) || file.type === "application/json") loadTimeline(file);
      else if (file.type.startsWith("audio/") || AUDIO_NAME.test(file.name)) loadAudio(file);
      else skipped.push(file.name);
    }
    if (skipped.length) say(`Skipped ${skipped.join(", ")}: not a recording or a .chords.json.`);
  }

  function showName(id, name) {
    $(id).textContent = name;
    $(id).title = name;
    $("files").hidden = false;
  }

  function loadAudio(file) {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioUrl = URL.createObjectURL(file);
    audio.src = audioUrl;
    audio.hidden = false;
    $("no-audio").hidden = true;
    showName("audio-name", file.name);
  }

  async function loadTimeline(file) {
    let data;
    try {
      data = JSON.parse(await file.text());
    } catch (error) {
      say(`Couldn't read ${file.name} as JSON: ${error.message}`);
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
    $("key-source").textContent = !key
      ? "The timeline has no chords."
      : key.source === "given"
        ? "Given with --key."
        : "Estimated from the chords.";
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
      const numeralText = segment.numeral ? Core.numeralText(segment.numeral, segment.inversion) : "";
      const label = [name, numeralText, Core.formatTime(segment.start_time)].filter(Boolean);
      button.setAttribute("aria-label", label.join(", "));
      button.title = label.slice(0, 2).join("  ");
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
    return ROLE_TEXT[segment.role] || "Not analyzed";
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
    $("now-role").textContent = isChord ? roleText(segment) : "No chord";
    $("now-function-row").hidden = !segment.function;
    $("now-function").textContent = segment.function || "";
    $("now-bass-row").hidden = !isChord;
    const bass = Core.bassName(segment.chord, keyLabel, segment.bass, segment.inversion);
    $("now-bass").textContent = bass ? `${bass}, ${INVERSION_TEXT[segment.inversion]}` : "None heard";
    const others = segment.candidates.slice(1).map((label) => Core.chordName(label, keyLabel));
    $("now-alt-row").hidden = others.length === 0;
    $("now-alt").textContent = others.join(", ");
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
    strip.scrollTo({ left: turnTarget, behavior: reducedMotion.matches ? "auto" : "smooth" });
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

  $("open").addEventListener("click", () => picker.click());
  picker.addEventListener("change", () => {
    takeFiles(picker.files);
    picker.value = ""; // so choosing the same file again still fires change
  });

  $("segments").addEventListener("click", (event) => {
    const button = event.target.closest(".segment");
    if (button) seek(Number(button.dataset.index));
  });

  document.addEventListener("keydown", (event) => {
    if (!timeline || event.altKey || event.ctrlKey || event.metaKey) return;
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
