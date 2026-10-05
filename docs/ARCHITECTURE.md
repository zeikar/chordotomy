# Architecture

Implemented so far: chords on the beat, from the lv-chordia model when the optional `model` extra is installed and from a DSP front end otherwise, key regions and Roman-numeral analysis, the bass note and inversions, explanations through the `explain-harmony` skill, a viewer that plays the recording with its chords, chord editing in that viewer, and an opt-in evaluation on real audio. The chord vocabulary is v6. This records the design decided before the first line of code (2026-09-29), the decisions since, and the reasons behind them.

## Pipeline

```text
audio ─→ beat tracking: onset strength ─────────────→ librosa's one-tempo DP (dsp engine)
           │            Beat This! beat activation ─→ librosa's one-tempo DP (model engine)
           │
           ├─→ CQT ─→ five ChordNets, averaged ─→ HMM ─→ frame labels ─→ beat majority ───────────────────┐
           │                                                             (model engine)                   │
           │            └─→ bass head, averaged per beat (model engine) ──────────────────────────────────┤
           │                                                                                              │
           ├─→ harmonic signal ─→ one tuning estimate ─┬─→ CQT, 36 bins per octave ─→ whitening           │
           │                                           │      ─→ treble and bass chroma, level, per beat  │
           │                                           │                    │                             │
           │                                           │                    ↓                             │
           │                                           │   template correlation + quality offsets         │
           │                                           │              + gated N + Viterbi (dsp engine)    │
           │                                           │                    │                             │
           │                                           └─→ CQT, 12 bins per octave ─→ bass note,          │
           │                                                                 segment cuts ─→ segments ←───┘
           │                                                                                  │
           │                                                                                  ↓
           │                                                   respell diminished and augmented twins
           │                                                                                  │
           │                                                                                  ↓
viewer ←── chord-timeline JSON ←───────────────────────────────── key regions + Roman numerals
```

- Chords are called per beat, not per frame, so a passing note doesn't become a chord change.
- Two engines recognize the chords. `--engine auto`, the default, takes the lv-chordia model when it is installed (the `model` extra) and the DSP front end otherwise; `--engine model` and `--engine dsp` pick one. The model is a pretrained ensemble whose frame labels are snapped to the beats. The DSP front end is a whitened chroma from librosa's CQT, then templates for eleven chord qualities, from triads to sevenths, a minor sixth, sus4 and the augmented and diminished triads. The vocabulary has two more, `sus2` and `sus4(b7)`, that only the model engine and the editor produce. The beat grid is each engine's own: librosa's one-tempo tracker follows librosa's onset strength on the DSP engine and Beat This!'s beat activation on the model engine, so the two can put a file's beats in different places. The cut rule, the twin respelling and the harmonic analysis are the same rules in both, while their results can differ: the per-beat bass is the low-register CQT's pick, after a salience test, on the DSP engine, and the DSP's plain pick or lv-chordia's bass head, whichever the head's test lets through, on the model engine, and the bass decides the cuts and a `min6` or `aug` spelling. See ["The model engine's beats come from Beat This!"](decisions.md#the-model-engines-beats-come-from-beat-this), ["A weak non-chord bass stays at root position"](decisions.md#a-weak-non-chord-bass-stays-at-root-position), ["A pretrained model as the recognizer"](decisions.md#a-pretrained-model-as-the-recognizer), ["Whitened chroma and an N gate on tonal evidence"](decisions.md#whitened-chroma-and-an-n-gate-on-tonal-evidence) and ["Chord vocabulary v6"](decisions.md#chord-vocabulary-v6).
- The bass note comes from a low-register CQT of the mix, and with the model engine also from lv-chordia's bass head. It settles slash chords and inversions (`F#7/A#`), which the chroma can't: it folds all octaves together and can't tell which note is lowest. A weak bass outside the chord is not trusted: the beat reads the chord's root, shown at root position, and the root is then not a measured note. A tie between per-beat basses goes to a tone of the chord. See ["Bass from DSP, not Demucs"](decisions.md#bass-from-dsp-not-demucs) and ["A weak non-chord bass stays at root position"](decisions.md#a-weak-non-chord-bass-stays-at-root-position).
- Analysis marks secondary dominants, secondary leading-tone chords and borrowed chords. The analyzer writes no prose: the explanations come from a Claude Code skill that reads the JSON. See ["Explanations from an agent skill"](decisions.md#explanations-from-an-agent-skill).
- A Python CLI (uv, Typer) writes the JSON. A static HTML viewer (`viewer/`) plays the audio, highlights the current chord, and corrects chords on the analyzer's beats, re-analyzing them in the browser. See ["Editing in the viewer"](viewer.md).

## Documents

- [recognition.md](recognition.md): how the audio becomes beats, chords and a bass, on the DSP engine and the model engine
- [harmony.md](harmony.md): the harmonic analysis, from the chord runs to the key, the key regions, numerals, roles and functions
- [timeline-json.md](timeline-json.md): the chord-timeline JSON, its fields and schema versions
- [viewer.md](viewer.md): editing in the viewer
- [evaluation.md](evaluation.md): scoring on real audio and on charted recordings, the current rows, and other chord recognizers
- [evaluation-history.md](evaluation-history.md): the rows of every earlier stage and the sweeps that set the constants
- [decisions.md](decisions.md): design decisions and their reasons
