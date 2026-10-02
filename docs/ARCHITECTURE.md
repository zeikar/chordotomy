# Architecture

Implemented so far: chords on the beat, from the lv-chordia model when the optional `model` extra is installed and from a DSP front end otherwise, key estimation and Roman-numeral analysis, the bass note and inversions, explanations through the `explain-harmony` skill, a viewer that plays the recording with its chords, chord editing in that viewer, and an opt-in evaluation on real audio. The chord vocabulary is v6. This records the design decided before the first line of code (2026-09-29), the decisions since, and the reasons behind them.

## Pipeline

```text
audio ─→ beat tracking
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
viewer ←── chord-timeline JSON ←────────────────────────────── key estimation + Roman numerals
```

- Chords are called per beat, not per frame, so a passing note doesn't become a chord change.
- Two engines recognize the chords. `--engine auto`, the default, takes the lv-chordia model when it is installed (the `model` extra) and the DSP front end otherwise; `--engine model` and `--engine dsp` pick one. The model is a pretrained ensemble whose frame labels are snapped to the beats. The DSP front end is a whitened chroma from librosa's CQT, then templates for eleven chord qualities, from triads to sevenths, a minor sixth, sus4 and the augmented and diminished triads. The vocabulary has two more, `sus2` and `sus4(b7)`, that only the model engine and the editor produce. The beat grid, the cut rule, the twin respelling and the harmonic analysis are the same rules in both, while their results can differ: the per-beat bass is the low-register CQT's pick, after a salience test, on the DSP engine, and the DSP's plain pick or lv-chordia's bass head, whichever the head's test lets through, on the model engine, and the bass decides the cuts and a `min6` or `aug` spelling. See "A weak non-chord bass stays at root position", "A pretrained model as the recognizer", "Whitened chroma and an N gate on tonal evidence" and "Chord vocabulary v6" under Design decisions.
- The bass note comes from a low-register CQT of the mix, and with the model engine also from lv-chordia's bass head. It settles slash chords and inversions (`F#7/A#`), which the chroma can't: it folds all octaves together and can't tell which note is lowest. A weak bass outside the chord is not trusted: the beat reads the chord's root, shown at root position, and the root is then not a measured note. A tie between per-beat basses goes to a tone of the chord. See "Bass from DSP, not Demucs" and "A weak non-chord bass stays at root position" under Design decisions.
- Analysis marks secondary dominants, secondary leading-tone chords and borrowed chords. The analyzer writes no prose: the explanations come from a Claude Code skill that reads the JSON. See "Explanations from an agent skill" under Design decisions.
- A Python CLI (uv, Typer) writes the JSON. A static HTML viewer (`viewer/`) plays the audio, highlights the current chord, and corrects chords on the analyzer's beats, re-analyzing them in the browser. See "Editing in the viewer".

### Stages implemented

Audio is decoded to mono at 22050 Hz. The harmonic part is taken with HPSS, so drums don't leak into the chroma.

Beats come from `librosa.beat.beat_track` with `trim=False`, because the default trim dropped the last real beats of a synthesized clip. The tracker keeps one tempo per file. It bends its beats to follow a drifting performance, but it does not follow a tempo change (see "Tempo changes are not followed" under Evaluation). The tracker places no beats in leading or trailing silence. So the grid is extended in both directions: the head at the first gap and the tail at the last, the grid's local period at each edge. On a constant grid both are the median gap within a frame; when only one beat is found, the step is the period of the tracker's tempo. Without that, the final chord's last beat would swallow a silent tail, and leading silence would have no beats to label `N`. A tail beat is added only if at least half a period remains, to avoid a sliver interval. Beat tracking runs first, so a file with no beats fails before any chroma work. The tracker can also lock at half tempo; the octave check below doubles such a grid when the chord changes fall between its beats.

Beats need not be evenly spaced. The decoder takes each beat's own length (see the smoothing paragraph below). `beats` in the JSON carries times, not a period, so a grid whose period changes is still schema 8. The viewer draws every beat at one width. The bass cut below counts beats, not seconds (`BASS_HOLD`).

The chord CQT starts at C1 and spans 252 bins, seven octaves at 36 bins per octave (a third of a semitone), the resolution of Mauch & Dixon. Its tuning is one `estimate_tuning` value on the harmonic signal, shared with the bass CQT below.

Each frame is then whitened along the frequency axis. A bin becomes its excess over the Hamming-weighted running mean of its octave (37 bins, k-18 to k+18), in running standard deviations; a bin at or below the mean is 0. So a chord's own tones cannot dominate their background, and a broadband, loud mix stops looking flat. The window edges repeat the edge value, and digital silence (sigma 0) whitens to 0. No max-normalisation follows, because the correlation below is scale-free.

Two pitch windows fold the whitened bins to twelve pitch classes: each class takes the bin on its pitch and one either side, which absorbs what the tuning estimate leaves. Both windows are raised cosines. The treble window fades in from E2 to C3 (MIDI 40 to 48) and out from C6 to C7 (MIDI 84 to 96). It starts above the bass line and the kick, which would flatten the chroma, and ends below the hi-hat and sibilance octaves. The bass window is flat up to B2 (MIDI 47) and fades out by B3 (MIDI 59). Each beat takes the median of its frames, for both chromas.

The `N` gate below reads four values per beat, each relative to the track or the beat itself:

- The level is the median RMS of the harmonic signal per beat, in dB relative to the 95th-percentile beat. A high percentile rather than the maximum, so one loud hit cannot push a quiet intro under the gate.
- The onset is the beat's peak onset strength, in units of the track's median frame. Where that median is 0, as on a mostly silent clip, any flux counts as struck. The envelope is librosa's `onset_strength` with its default mean over mel bands, not the tracker's median over bands: at -50 dB only a few bands rise, so their median is 0 where the mean still shows the strike.
- The flatness is the median spectral flatness of the harmonic signal over the beat's frames: near 0 for tones, 1 for digital silence.
- The harmonic share is the share of the beat's energy that is in the harmonic signal: the lower of the share summed over the beat and its median per frame, and 0 on a beat with no energy. A beat counts as harmonic only where both say so. The sum is set by the beat's loudest frames, so a drum hit outweighs the cymbal sustain HPSS keeps as harmonic (the median Tiny AAM drum stem decodes 81 % `N` with the summed share, 53 % with the median one). The median is set by most of the beat's frames, so a beat that is mostly silence reads 0 though its first frames carry the last chord or a cut's click.

There are 156 chord labels, 12 roots × 13 qualities: `maj`, `min`, `7`, `maj7`, `min7`, `min6`, `hdim7`, `dim7`, `sus4`, `aug`, `dim`, `sus2` and `sus4(b7)` (see "Chord vocabulary v4", "Chord vocabulary v5" and "Chord vocabulary v6" under Design decisions). The decoder never chooses `sus2` or `sus4(b7)`, as the offsets below say. A chord's template is the sum, over its tones, of each tone's first four partials: the fundamental, the octave, the twelfth and the double octave, 0, +12, +19 and +24 semitones folded to pitch classes. Partial k weighs `PARTIAL_DECAY`^(k-1), with `PARTIAL_DECAY` = 0.8. A chord's score is the Pearson correlation of the treble chroma with its template, in [-1, 1], plus `BASS_WEIGHT` = 0.3 times the correlation of the bass chroma with the chord's bass profile, plus its quality's offset. The bass profile is on the chord tones alone, without partials: 1.0 on the root and `BASS_TONE` = 0.7 on the chord's other tones. Both sides of each correlation are centred and unit-normed over the twelve classes, so a flat or silent chroma has no shape and scores 0 against every chord.

The offsets (`QUALITY_OFFSET`) are 0 for `maj`, `min` and `7`, -0.1 for `maj7`, `min7`, `min6`, `hdim7`, `dim7` and `dim`, -0.25 for `sus4` and `aug`, and minus infinity for `sus2` and `sus4(b7)`. So the other tetrads, the diminished triad, `sus4` and `aug` have to beat the triads by evidence, and `sus2` and `sus4(b7)` are never called: a label at minus infinity has likelihood 0 in `smooth` and ranks last among a segment's candidates. "Chord vocabulary v4", "Chord vocabulary v5" and "Chord vocabulary v6" say why; "Tuning the v4 constants", "Tuning the v5 offsets" and "Tuning the v6 offset" under Evaluation say how the values were found. `aug` and `dim` are called at a stated price: against never calling them, they give up at most 0.24 pp on any Tiny AAM or GuitarSet column.

Some labels share a pitch set. `G:min6` and `E:hdim7` are both G–Bb–D–E, and a `dim7`'s four tones are the roots of four `dim7` labels on the same notes. Their templates are the same, so only the bass profile, which favours the root, tells these twins apart. Without bass evidence they tie exactly, and the decoder keeps the label that comes first: qualities in the order above, then roots from C. So `G:min6` wins over `E:hdim7`, `C:dim7` over `D#:dim7`, `F#:dim7` and `A:dim7`, and `C:aug` over `E:aug` and `G#:aug`, the three roots of one augmented triad: the earliest root. That choice says nothing about the music; the respelling step at the end of this section revisits it. Two relations are not twins to the decoder. The diminished triad is a subset of the `dim7` and `hdim7` on its tones (`B:dim` is inside `B:dim7` and `B:hdim7`), not the same set, so it has a template of its own, and its offset equals theirs. And `C:sus2` is `G:sus4`'s pitch set, but the DSP never calls `sus2`, so it decodes `G:sus4` for a played Csus2 and the bass shows the inversion. The model engine does call `sus2`. A `sus4(b7)` has no twin: A–D–E–G is no other label's set, though it contains `A:sus4`, `D:sus4`, `D:sus2` and `G:sus2` and shares three tones with `A:7`, `A:min7` and `E:min7`.

`N` is not a template. Its score is the constant `N_SCORE` = 0.3, which a chord has to beat. And a beat with no tonal content of its own can only be `N`, because whitening is scale-free and would turn residual ringing or a drum's noise into a chord. That is the gate, `no_chord`. A beat is noise-like when its flatness is over `N_FLATNESS` = 0.02, quiet when its level is more than `N_GATE_DB` = 40 dB below the loud beats, struck when its onset is over `ONSET_FRACTION` = 0.5, and a sliver when its harmonic share is under `N_HARMONIC_SHARE` = 0.3. A beat is forced to `N` when it is a sliver and either noise-like or quiet, or when it is noise-like, quiet and not struck. Digital silence meets both conditions. So a tonal beat with harmonic energy of its own is a chord however quiet: a held chord has no onset on most of its beats, and its harmonic evidence is what says it is a chord. A loud tonal beat is never forced either, even when its harmonic share is a sliver, as on a percussive strum. A quiet beat that looks tonal but whose harmonic part is a sliver is forced, because HPSS spreads a neighbouring chord's tones into the first and last beats of a drum break. "Whitened chroma and an N gate on tonal evidence" under Design decisions gives the measured reasons. The model engine does not apply the gate.

Smoothing is a Viterbi decode over these scores. Likelihoods are `exp((score - best) / TEMPERATURE)` with `TEMPERATURE` = 0.03, so a gap of g on one beat is worth g / 0.03 nats against the transition cost. A forced beat's chord likelihoods are 0. From beat i to beat i + 1, a state stays put with probability p_i = exp(-Δt_i / `CHORD_SECONDS`), where Δt_i is beat i's own length and `CHORD_SECONDS` = 2.8, and the rest is spread evenly over the other 156 states. So the cost of a switch grows with the label count: it is ln(156 p_i / (1 - p_i)) nats against staying, about 6.7 after a beat of 0.5 s, and leaving a chord for one beat and coming back costs about 13.4 at that tempo. With v3's 37 states each switch cost ln 3, about 1.1 nats, less at the same p; that is why the decode constants were retuned with the vocabulary. v5's 144 other states instead of v4's 108 add ln(144 / 108), 0.29 nats, to each switch. The twelve `sus2` states count among them although the DSP never chooses one: one vocabulary serves both engines, and the v5 offsets were tuned with this transition. v6's 156 other states instead of v5's 144 add ln(156 / 144), 0.08 nats, to each switch, and the twelve `sus4(b7)` states, never chosen either, are among them; the v6 offset was swept with this transition. The expected chord length is in seconds, not beats, and each beat pays for its own length. So a tracker locked at half or double tempo does not halve or double it, and neither does a beat that runs long or short. The decode is librosa's Viterbi, step for step in librosa's arithmetic, with one transition matrix per beat instead of one per track, so on a constant grid its path is librosa's to the beat (`test_smooth_matches_librosa_on_a_constant_grid`). The temperature is low enough that a real change lasting two beats survives, and the self-loop is strong enough that a single beat where a chord flickers to its sibling does not.

The octave check reads the grid against the chord changes. When the tracker locks at half tempo and the chords change on the beats it skips, its grid merges the chords on either side of each change. So `beat_features` first builds the doubled grid, a beat inserted at every midpoint and the edges extended at half the edge gaps, and decodes it with the DSP's own `match` and `smooth`, with no beat gated. It does so in either engine, since both share the grid. When at least `OCTAVE_MIN_CHANGES` = 24 chord changes are decoded and at least `OCTAVE_INSERTED_SHARE` = 0.80 of them start on inserted beats, the doubled grid is kept for the whole track; otherwise the tracker's grid is. A half-tempo grid in phase with the changes is left. Each chord is one beat on it, and the decoder keeps a one-beat change to a distinct chord, so it costs granularity, not chords. The check has two limits. Under a half lock, one-beat chords at the true tempo change on inserted and tracker beats alike, a share of 0.50, so that lock is not caught. And a grid at double tempo is never halved: it loses no chord, since the self-loop is in seconds, while halving could merge real two-beat chords.

Consecutive beats with the same state become one chord run. A run is also cut where the per-beat bass changes to a value that holds for two beats (see the bass paragraphs below). Each resulting segment carries three candidate labels, computed over its own beats: the smoothed chord first, then the labels with the highest mean score over the segment. Scores are not written out, per the confidence rule below. Consecutive segments may therefore share a chord.

The cut rule governs a bass move under a held chord only, because a chord change already cuts. So a one-beat slash chord that comes with a chord change (C → G/B → Am) is its own segment. A one-beat bass move under an unchanged chord is almost always a passing or walking tone, and cutting on it would fragment the timeline without changing the harmony. An alternating bass under a held chord (C–E–C–E, C–G–C–G) is a root-position accompaniment pattern, not a series of inversions: no value holds two beats, so it stays one segment. A segment's bass is the value held inside it. A move shorter than two beats is excluded from that choice, so three C beats and one loud E beat read C. A segment with no held value takes the most frequent per-beat value, silence included, ties to a tone of the segment's chord, then a note, then the earliest. So `[D#, C]` under `C:maj` reads `C`, where taking the earliest beat wrote `C/D#`, a passing note on beat 1 of a two-beat chord as a slash, and `[E, C]` still reads `E`, both being chord tones. The vote is `null` when most beats are silent. The first held value cuts at its own start when at least two beats precede it in the run (`C–E–C–E–G–G` is two segments, the first by that vote); with fewer, it absorbs them. A bass-register silence held for two or more beats under one chord (a bass player resting while the chord is voiced above the register) also cuts: the middle segment has bass `null`, and the chord on either side keeps its own bass. `N` runs are never cut and have no bass.

The bass note is by definition the lowest sounding note, so it is read from a CQT that keeps octaves apart. Folding it into a chroma would lose that: a chord played alone ties its tones on an argmax, and any low chord tone louder than the bass would win. The CQT is taken from the same harmonic signal as the chroma. It starts at C1 (32.7 Hz) and spans 84 bins, seven octaves at 12 bins per octave, the same span as the chord CQT. Bin k is k semitones above C1. The lowest 36 bins (C1–B3, 32.7–246.9 Hz) are the bass register. The bins above it are context for the peak test and give the silence floor the file's level.

Twelve bins per octave rather than the chroma's 36, because the CQT window at C1 is then 0.53 s instead of 1.59 s, so beats stay separable. The cost is that a note leaks into its neighbouring semitone bins at 0.50 to 0.60 of its peak. The pick rule below is built around that. The magnitude is reduced to the median over each beat, on the same grid as the chroma.

For tuning, both CQTs take the same `estimate_tuning` value, measured at 36 bins per octave on the harmonic signal. The bass CQT divides it by three for its 12-bin grid. So the bass bins line up with the chord chroma's, and on a recording detuned by half a semitone the chroma's root and the bass note fall on the same side.

A beat column is zeroed when its register maximum is below 1 % (`SILENCE_FLOOR`) of the loudest bin of the whole matrix, the file's loudest note anywhere. A file with nothing in the register never sets its own reference this way: what survives there is leakage under real notes above, which the peak test rejects. The column is zeroed rather than lifted by an additive floor, because a flat column would make C1 the lowest peak.

On each column the bass is the lowest local maximum inside the register that is at least half the register's maximum. Its pitch class is the bin mod 12. Local maxima are tested over the whole 84-bin profile, so a note just above the register (C4 leaks into B3 at half its height) is a slope, not a peak. Leakage is never a local maximum, and a bass note's harmonics all lie above it. Taking the lowest peak rather than the loudest is the definition of a bass; the price is that a fundamental weaker than half the loudest register bin is not picked. A zero column, or one with no qualifying peak, has no bass.

On the DSP engine a pick outside the beat's chord has one more test (`beat_basses`): it must be at least `NONCHORD_SALIENCE` = 1.0 of the register's maximum, that is the register's loudest note, else the beat reads the chord's root. A pick that is a tone of the chord is written as heard, whatever its height. The root is a fallback, not a measured note. On a locally analyzed recording with a chart the test rejects the weaker, lower notes the pick took under a louder root, at 0.53 to 0.74 of the loudest; the held slashes it keeps sit at 1.0, so a held `D/E` is the bound: above 1.0 even the loudest pick fails and no non-chord slash is written. "Bass reliability" under Evaluation has the sweep.

The bass also feeds the chord choice, through the bass chroma and its weight in the score. The treble chroma starts at E2, so the bass line no longer flattens it. The bass chroma is not a root vote: a chord's bass profile is 1.0 on its root and 0.7 on its other tones. A bass pedal now argues for every chord that contains it, most for the chord rooted on it. A loud pedal outside the chord still pulls the label toward chords that contain it. A bass on the third or fifth still supports its chord, so the treble decides between a first inversion and the chord rooted on the bass (`A:min/C` against `C:maj`, `G:maj/B` against `B:min`). A root bass breaks the ties the treble cannot, like `G:min6` against `E:hdim7`. The bass note that goes into the segments is, on the DSP engine, the CQT pick above after that test, not this chroma.

The bass chroma is zeroed on beats where the plain pick, before the salience test, finds no note. The correlation is scale-free, so otherwise the leakage under a chord voiced above the register would vote at full strength; it pulled a bass-less `C:maj` toward `C:maj7`.

Last, a diminished or augmented chord is respelled by where it leads (`resolve_twins`). This works on chord runs, consecutive segments with the same chord, and the next chord is the following run's. A `dim7` run becomes the twin whose root is a semitone below the next chord's root whenever one exists, whatever its bass. A `dim7` is symmetric, so the bass profile roots it on its lowest tone, and that tone is its inversion, not its root: a `C#:dim7` played over E decodes as `E:dim7`, and before `D:min` it is respelled `C#:dim7` in first inversion. A `dim7` run followed by a `dim7` on the same notes is one chord over a moved bass, and takes the following run's label. A `min6` run becomes its `hdim7` twin when that twin leads into the next chord, so a bass-less `A:min6` before `G:maj` is `F#:hdim7`. It stays `min6` if any of its segments has a heard bass on the `min6`'s root, the evidence for that reading; a root that `beat_basses` or `beat_bass` wrote as the fallback was not heard, so it does not count (`segment` carries this as an internal `bass_heard` flag that is not in the JSON). An `hdim7` is never respelled. An `aug` run becomes the `aug` a fifth above the next chord's root whenever its pitch set has one, the dominant resolution (`V+` to `I`), which is the one strong convention for an augmented triad: a bass-less `D#:aug` before `C:maj` is `G:aug`, and a `C:aug` before `A:min` is `E:aug`. Like a `min6`, it stays if any of its segments has a heard bass on the decoded root, the evidence for that reading, since label order says nothing (`C:aug` over C before `A:min` stays). A `dim` triad has no twin and keeps its label. `sus2`, `sus4` and `sus4(b7)` are never respelled: a suspension resolves on its own root, so the next chord's root is no evidence as it is for a leading-tone chord, and sus chords are voiced over their root. The DSP decodes `G:sus4` alone, and a `sus2` or `sus4(b7)` from the model stays as it is. A run with no twin that leads, and a run before `N` or at the end, keeps the recognizer's label. The runs are taken from the last back, so each one leads into the next chord as that chord will be written. A respelled segment's candidates lead with the new label, then the recognizer's, and its `inversion` follows the new label.

#### The model engine

With `--engine model`, or `--engine auto` when lv-chordia is installed, the per-beat chord states and scores come from lv-chordia, the ensemble of Jiang, Chen, Li & Xia (ISMIR 2019), instead of the templates and the Viterbi decode above. Everything else is the DSP path described above: the beats, the cut rule, `segment` and its candidates, `resolve_twins`, and the harmonic analysis below. `auto` looks for the package with `importlib.util.find_spec`, which imports neither lv_chordia nor torch. `--engine model` without the extra is a usage error that names `uv sync --extra model`. An extra that is installed but cannot run, because an import fails or a checkpoint is missing or damaged, is an error that names the reinstall and `--engine dsp`. It never falls back to the DSP on its own, which would hand the user the other engine's chords without asking.

The nets read the decoded mono signal, not its harmonic part, through the package's own front end, `CQTV2`, run on the signal `load_audio` already decoded rather than on the file: a hybrid CQT from F#0, 288 bins at 36 per octave, on the DSP's hop of 512 samples at 22050 Hz. So its frame k is frame k of the DSP's chord CQT.

They run over windows of at most `CHUNK_SECONDS` = 60 s. The track is cut into equal windows, and each runs with `OVERLAP_SECONDS` = 5 s of context on both sides, clipped to the track, whose outputs are dropped. The windows bound the nets' memory, which grows with the length they see. They also keep the nets' InstanceNorm and BiLSTM to at most 70 s, closer to the 23 s segments the nets were trained on than a whole song. "Model engine" under Evaluation has the memory, and the scores with and without the windows.

Each of the five nets has six heads, each a softmax per frame: the root and triad (or none), the bass, and the seventh, ninth, eleventh and thirteenth. Each head is averaged over the five nets, as the package's `chord_recognition` averages them. The decoder is the package's `XHMMDecoder` on its `submission` dictionary: 25 qualities on 12 roots, and `N`. Its `get_chord_tag_obs` scores every dictionary name on every frame by the log of the product of the probabilities its heads give it, not normalized over the names. The HMM is a Viterbi decode over those names that charges a fixed cost for every change. It runs without beats, as `chord_recognition` runs it, so a chord can change on any frame, and gives one name per frame.

`QUALITY` in `model.py` maps the dictionary's qualities to v6's, with the slash dropped, and the decoder's flat roots (`Eb`, `Ab`, `Bb`) become sharps:

| lv-chordia | v6 | loses |
| --- | --- | --- |
| `maj`, `min`, `7`, `maj7`, `min7`, `hdim7`, `dim7`, `sus4`, `aug`, `dim`, `sus2`, `sus4(b7)` | the same | nothing |
| `9` | `7` | the ninth |
| `11` | `7` | the ninth and eleventh |
| `13` | `7` | the ninth, eleventh and thirteenth |
| `maj9` | `maj7` | the ninth |
| `min9` | `min7` | the ninth |
| `maj/3`, `maj/5`, `maj/b7`, `maj/2`, `min/b3`, `min/5`, `min/b7`, `min/2` | `maj`, `min` | the bass, which comes from the bass head instead (below) |

On the two evaluation datasets the model emitted no `9`, `11`, `13`, `sus2`, `aug` or `sus4(b7)` at all. It emitted `dim` on 0.03 % of Tiny AAM's duration and 0.69 % of GuitarSet's, and a slash chord on 2.5 % of Tiny AAM's and 1.9 % of GuitarSet's. Until v5 it mapped `aug`, `dim` and `sus2` to `maj`, `dim7` and the `sus4` a fifth up, and until v6 `sus4(b7)` to `sus4`; "Chord vocabulary v5" and "Chord vocabulary v6" say why that ended. `11` stays `7`, since Harte's 11 includes the third. No quality maps to `min6`, so the model engine never calls one.

Each beat takes the label that covers most of its frames, ties to the lowest label index as in the DSP's decoder (`beat_states`). The scores are folded onto v6's 157 labels (`fold`, `beat_scores`): a label's score on a frame is the log of the summed probability of the names that map to it, a log-sum-exp of `get_chord_tag_obs`'s log-scores, and its score on a beat is the mean over the beat's frames. A label no name maps to, every `min6`, scores -inf. The states come from the HMM and the scores from the probabilities before it, as the DSP's states come from its Viterbi and its scores from the correlation, and `segment` ranks a segment's candidates by these scores as it does the DSP's.

The bass head is averaged over each beat's frames as the scores are, giving 13 values per beat: index 0 for no bass and one per pitch class. `beat_bass` gives `segment` one bass per beat. Per chord beat the candidates are, in order, the DSP's plain `pick_bass` (absent when the bass register is silent) and then the head's note (the argmax of the twelve notes, absent when "no bass" is the largest of the thirteen). The first candidate that is a tone of the chord is the bass, never gated. Otherwise the first non-chord candidate whose posterior in the head is at least `BASS_SUPPORT` = 0.7 is. Otherwise the beat reads the chord's root, a fallback written as root position and not a measured note. `null` is written only when there was no candidate: for `N`, or when the head hears no bass and the register is silent. So `null` means something else here than on the DSP engine, where it means no note in the bass register, and the model can write a note from the head where the DSP's register is silent. The cut rule and the vote read these values as they read the DSP's, but the two engines' bass values differ, and so can their cuts.

The DSP's `N` gate and `N_SCORE` are not applied. The gate exists because whitening is scale-free; the model's `N` is its own, a dictionary name the HMM decodes like any other. A bass outside the model's chord is kept only when it is a tone of the chord or the head supports it; what the DSP pick alone cost there is in "Bass reliability" under Evaluation.

### Harmonic analysis

The analysis is a pure function of the chord runs and an optional key. A chord run is consecutive segments with the same chord, with their beats summed, so a bass change under a chord changes neither the key weights nor the look-ahead below. It takes no audio (see "Key from chords, not audio" under Design decisions). It lives in `harmony.py`.

A chord is diatonic when every chord tone lies in the key's scale: major, or natural minor. Minor admits five harmonic-minor cases on top, all with the raised leading tone: `maj` and `7` on the dominant degree (V and V7), `dim` and `dim7` on the leading tone (`#vii°` and `#vii°7`), and `aug` on the mediant (`III+`, C–E–G♯ in A minor). The raised leading tone is admitted nowhere else, so `F:min` in A minor is chromatic, not diatonic. The resulting sets are:

- major: `I ii iii IV V vi vii°`; `Imaj7 ii7 iii7 IVmaj7 V7 vi7 viiø7`; `iiadd6`; `Isus4 IIsus4 IIIsus4 Vsus4 VIsus4`; `Isus2 IIsus2 IVsus2 Vsus2 VIsus2`; `II7sus4 III7sus4 V7sus4 VI7sus4`
- minor: `i ii° III III+ iv v V VI VII #vii°`; `i7 IIImaj7 iv7 v7 V7 VImaj7 VII7 iiø7 #vii°7`; `ivadd6`; `Isus4 IIIsus4 IVsus4 Vsus4 VIIsus4`; `Isus2 IIIsus2 IVsus2 VIsus2 VIIsus2`; `I7sus4 IV7sus4 V7sus4 VII7sus4`

`VII7` is there because `G:7` in A minor is G–B–D–F, all natural minor. `C:7` in C major is not diatonic, since Bb is outside the scale.

The key is one global key per file. Each of the 24 keys scores the sum over chords of beats times a weight. A non-diatonic chord weighs 0. A diatonic chord weighs 3 on the tonic, 2 on the subdominant or dominant degree, and 1 on any other degree. The diatonic test takes the full label, seventh included, not its triad. Reduced to triads, `C – Am – D7 – G7` would be G major, where D and G are V and I; with its sevenths it is C major, because the F of `G:7` is outside G major. A seventh detected where there is none can take its chord out of the key, which costs that one chord's vote and no more. Beats are used rather than seconds because they are the musical duration and the segments carry them. Relative keys share six triads, so the choice between them comes down to where the time goes: `Am–F–C–G` with equal beats is C major, and the same loop with `Am` twice as long is A minor. Ties break on beats spent on the key's own tonic chord, then on whether the first chord is that chord, where the tonic chord is the tonic triad or its `maj7` or `min7` (`Am7 – Cmaj7` with equal beats is A minor, as `Am – C` is), then on the fixed key order. A timeline of only `N` has no key. The top 3 keys are written out.

`--key` replaces the estimated key. The estimator still runs, so `key.candidates` keeps showing what the chords suggest, and you can see how far an override is from it.

A numeral is `<accidental><roman><suffix>`, followed by `/<target>` for a secondary chord. The roman is the root's offset from the tonic, spelled with accidentals relative to the key's own scale (major scale, or natural minor). Case shows the third: uppercase for a major third or none, lowercase for a minor one. The suffix comes from the quality:

| quality | case | suffix | in C major |
| --- | --- | --- | --- |
| `maj` | upper | | `F:maj` is `IV` |
| `min` | lower | | `F:min` is `iv` |
| `7` | upper | `7` | `G:7` is `V7` |
| `maj7` | upper | `maj7` | `F:maj7` is `IVmaj7` |
| `min7` | lower | `7` | `D:min7` is `ii7` |
| `min6` | lower | `add6` | `F:min6` is `ivadd6` |
| `hdim7` | lower | `ø7` | `D:hdim7` is `iiø7` |
| `dim7` | lower | `°7` | `B:dim7` is `vii°7` |
| `sus4` | upper | `sus4` | `G:sus4` is `Vsus4` |
| `aug` | upper | `+` | `G:aug` is `V+` |
| `dim` | lower | `°` | `B:dim` is `vii°` |
| `sus2` | upper | `sus2` | `G:sus2` is `Vsus2` |
| `sus4(b7)` | upper | `7sus4` | `G:sus4(b7)` is `V7sus4` |

`min6` is `add6` because `iv6` would read as the first-inversion figure. `ø` and `°` are the characters U+00F8 and U+00B0, not ASCII stand-ins; the accidentals stay ASCII `b` and `#`, and `+` is the ASCII plus. `dim` has no 7 in its suffix, which tells `vii°` from `vii°7`. Accidentals describe the root only, so `E:7` in A minor is `V7`, never with a raised leading tone.

The three diminished qualities have one exception. A `dim`, `dim7` or `hdim7` root on a degree spelled flat is spelled as the raised degree below, because a diminished chord leads up a semitone. `C#:dim7` in C major is `#i°7`, pointing at `ii`, never `bii°7`; likewise `#ii°7`, `#v°7` and `#vi°7` in major and `#i°7` in minor, and `C#:dim` is `#i°`. Every other chord keeps the plain spelling, so `C#:maj` in C major is `bII`. The viewer spells the chord name the same way, C♯dim7 rather than D♭dim7, except where that would need a double sharp, where it takes the enharmonic letter (`G:dim7` in F# major is Gdim7 under `#i°7`).

The diminished triad is diatonic as `vii°` in major and as `ii°` and `#vii°` in minor. Their seventh chords are `viiø7` in major, and `iiø7` and `#vii°7` in minor. A diminished triad that is diatonic only in the parallel mode is borrowed: `D:dim` in C major is a borrowed `ii°`.

Each chord gets one role. The first match wins:

1. `diatonic`, by the test above in the key's own mode.
2. `secondary_dominant`, for a `maj` or `7` chord whose root a perfect fifth below is a tonicizable diatonic triad. Major targets are `ii iii IV V vi`; minor targets are `III iv V VI VII`. Never the tonic, never a diminished degree. The numeral is `V/<target>` or `V7/<target>`, and `target` names the tonicized numeral. The rule is the pitch relationship, so a `V7/V` that resolves elsewhere is still labeled. Only `maj` and `7` count: a `maj7` has no tritone, and a `sus4` or a `sus4(b7)` no leading tone.
3. `secondary_dominant` as well, for a secondary leading-tone chord: a `dim`, `dim7` or `hdim7` whose root is a semitone below one of the same targets, when the next chord is diatonic in the key and has the target's root. The numeral is `vii°/<target>`, `vii°7/<target>` or `viiø7/<target>`, and `target` is set: in C major, `C#:dim` before `D:min` is `vii°/ii`, `C#:dim7` before `D:min7` is `vii°7/ii`, and `F#:hdim7` before `G:maj` is `viiø7/V`. A dominant is known by its fifth relation alone, a leading-tone chord only by where it goes, so this rule always looks ahead: `F#:hdim7` before `F:maj` is a chromatic `#ivø7`.
4. `borrowed`, when the chord is diatonic in the parallel mode (same tonic, other mode). The seventh counts, and `TRIAD` also maps `sus4(b7)` to its `sus4`, so in major `C:sus4(b7)`, `F:sus4(b7)` and `A#:sus4(b7)` are borrowed `I7sus4`, `IV7sus4` and `bVII7sus4`: chords of the parallel mode, to which the seventh adds no case. So `A#:7` (Bb7) is a borrowed `bVII7` in C major, while `D#:7` and `G#:7` (Eb7, Ab7) are not borrowed, because Db and Gb are outside C minor. An added sixth counts the same way, and so does the parallel minor's `#vii°7`: `F:min6` (F–Ab–C–D) is a borrowed `ivadd6` in C major, and `B:dim7` a borrowed `vii°7`. A tetrad is also borrowed when its triad is diatonic in the parallel mode and its seventh (a `min6`'s sixth) lies in either mode's scale, so a seventh the borrowed triad takes from the home mode is still borrowed colour. In major that makes `A#:maj7` a borrowed `bVIImaj7`, `D:dim7` a borrowed `ii°7` (the notes of the borrowed `vii°7`), and `C:min6` and `G:min6` borrowed `iadd6` and `vadd6`. In A minor the rule would also cover `A:7` and `D:7`, but rule 2 claims them first, so they are `V7/iv` and `V7/VII` wherever they go. A triad of the home mode with a foreign seventh stays chromatic (`F:7` in C major is `IV7`; `G:maj7` and `A:min6` in A minor are `VIImaj7` and `iadd6`), as do sevenths outside both scales (`D#:7` is `bIII7`, `G#:7` is `bVI7`, `G:maj7` in C major would be `Vmaj7`). The precedence does not change.
5. `chromatic`, everything else, with the plain numeral.

Two chords need a look-ahead to tell rule 2 from rule 4, both in minor keys: the major triads on the tonic and the subdominant. The dominant sevenths `A:7` and `D:7` also meet both tests, but they are always secondary dominants, because the overlap asks whether the chord itself belongs to the parallel mode, and neither is a chord of A major, whose scale has G♯ and C♯ where they have G and C. `A:maj` in A minor is either `V/iv` or a borrowed `I`, and `D:maj` is either `V/VII` or a borrowed `IV`. Here the label looks one chord ahead. The chord is a secondary dominant only when the immediately following chord is diatonic in the key and has the target's root: `D:min` after `A:maj` (`D:7` and `D:maj` are not diatonic in A minor), `G:maj` or `G:7` after `D:maj`. Any other chord, a non-diatonic chord on that root, an `N`, or the end of the track makes it borrowed. Silence is not a resolution, however long. A leading-tone chord (rule 3) takes the same test, always. Every other label depends on the chord and key alone.

An `aug` is never a secondary dominant, and its `V+` is chromatic. The chord is symmetric, so its root is the bass's or `resolve_twins`'s choice, not a fifth relation that identifies it: `C+`, `E+` and `G#+` are one chord, and by the fifth relation they would be `V+/IV`, `V+/vi` or `bVI+` in C major by tie-break alone. The common pop augmented chord, `I+` passing to `IV` or `vi`, sits on the tonic. So the tonic's `V+` keeps the plain numeral `V+` with the role `chromatic`; the numeral already names the augmented dominant. `sus2` is never one either, as `sus4` is not, and neither is `sus4(b7)`: with no third it has no leading tone.

The function is set for diatonic chords only, by the degree, whatever the quality: `I`, `III`, `VI` are `tonic`; `II`, `IV` are `predominant`; `V`, `VII` are `dominant`. So `viiø7`, `vii°`, `#vii°7` and `#vii°` are dominant, `III+` is tonic, and `Vsus4`, `Vsus2`, `V7sus4` and `iiadd6` take their degree's function. `iii` and `vi` are tonic substitutes, and `VII` in minor is the subtonic dominant. Other roles have no function.

The viewer re-analyzes edited chords with a JavaScript port of this analysis, `viewer/harmony.js`, pinned to the Python by golden vectors that `uv run python tests/harmony_vectors.py` writes to `tests/harmony_vectors.json`: pytest fails when the file no longer matches the Python, and `node --test viewer/tests/` replays every case through the port (see "Re-analysis in the browser, Python as the reference" under Design decisions).

## The chord-timeline JSON

This is the project's public seam. It carries beat positions, not just seconds, so another tool, or a notation stage someone else builds, can consume it. `chordotomy analyze` writes it as schema version 8.

| field | type | meaning |
| --- | --- | --- |
| `schema_version` | int, `8` | schema version of this file |
| `generator.name` | `"chordotomy"` | |
| `generator.version` | str | the chordotomy version that wrote the file |
| `generator.engine.name` | `"dsp"` or `"lv-chordia"` | the recognizer that produced `chord` and `candidates`: chordotomy's DSP front end, or the lv-chordia model |
| `generator.engine.version` | str | chordotomy's version for `dsp`, the lv-chordia package version otherwise |
| `source.path` | str | the audio path as given on the command line |
| `source.duration` | float, seconds, 3 decimals | |
| `beats` | list of float seconds, 3 decimals, ascending | beat index = list position |
| `key` | object or `null` | the key the numerals are relative to; `null` only when the timeline has no chord and no `--key` was given |
| `key.label` | str | `<root>:maj` or `<root>:min`, sharps only, e.g. `C:maj`, `A:min` |
| `key.source` | `"estimated"` or `"given"` | `given` when `--key` was passed or the user chose the key in the viewer |
| `key.candidates` | list of up to 3 str | the estimator's ranking, best first, no scores; `candidates[0] == label` when `source` is `estimated`; `[]` when the timeline has no chord |
| `segments[].start_beat` | int | inclusive |
| `segments[].end_beat` | int | exclusive; may equal `len(beats)`, meaning the segment runs to the end of the audio |
| `segments[].start_time` | float | `beats[start_beat]` |
| `segments[].end_time` | float | `beats[end_beat]`, or `source.duration` when `end_beat == len(beats)` |
| `segments[].chord` | str | Harte label or `N`; always the root-position label; consecutive segments may repeat it when the bass changes under one chord |
| `segments[].candidates` | list of 3 str | best first by the recognizer's own scores over the segment, which aren't written; `candidates[0] == chord` when `edited` is false, and the analyzer's ranking for the span the segment came from when it is true; when a diminished or augmented chord was respelled by where it leads, `candidates[1]` is the recognizer's label for the same notes |
| `segments[].bass` | str or `null` | the segment's held bass, sharps only (`C` to `B`): the per-beat bass (on the DSP engine the lowest note sounding in the bass register; on the model engine the bass lv-chordia's bass head hears) that holds for at least 2 beats under the chord; when no value holds that long (a one-beat chord, a bass moving every beat), the most frequent per-beat value, silence included, ties to a tone of the segment's chord, then a note, then the earliest; a bass move shorter than 2 beats under an unchanged chord (a passing tone, an alternating C–E or C–G accompaniment) is not reported; a per-beat bass outside the chord that is judged unreliable (on the DSP, under `NONCHORD_SALIENCE` of the register's loudest note; on the model, under `BASS_SUPPORT` in the head) is replaced by the chord's root before the hold and the vote, so a root bass may be that fallback and not a measured note (when `resolve_twins` respells a chord, an inferred bass moves to the new chord's root); `null` for `N`, when no beat has a note in the bass register (DSP), and when the head hears no bass and the register is silent (model) |
| `segments[].inversion` | `"root"`, `"first"`, `"second"`, `"third"`, `"non_chord"`, or `null` | `chord` over `bass`, by the bass's place among the chord's tones from the root up: `root`; `first`, the third, the fourth of a `sus4` or `sus4(b7)` or the second of a `sus2`; `second`, the fifth; `third`, the seventh of a `7`, `maj7`, `min7`, `hdim7`, `dim7` or `sus4(b7)`, or the added sixth of a `min6`; `non_chord` when it is not a chord tone; `null` whenever `bass` is `null` |
| `segments[].numeral` | str or `null` | Roman numeral of the root-position chord relative to `key`, `<accidental><roman><suffix>[/<target>]` (grammar above), e.g. `bVII`, `ii7`, `IVmaj7`, `#i°7`, `vii°`, `V+`, `V7sus4`, `viiø7/V`; `ø` and `°` are written as characters; `null` for `N` |
| `segments[].role` | `"diatonic"`, `"secondary_dominant"`, `"borrowed"`, `"chromatic"`, or `null` | how the chord relates to the key; `secondary_dominant` includes secondary leading-tone chords; `null` for `N` |
| `segments[].function` | `"tonic"`, `"predominant"`, `"dominant"`, or `null` | harmonic function; set only for `diatonic` chords |
| `segments[].target` | str or `null` | for `secondary_dominant`, the numeral of the chord it tonicizes (`V7/V` → `V`, `vii°7/ii` → `ii`); `null` otherwise |
| `segments[].edited` | bool | `false`: `chord` and `bass` are the analyzer's. `true`: the user set them in the viewer, either by choosing a chord or bass for this segment other than the one it had, or by a merge or removal that extended it over a neighbour with a different chord or bass, a span where the analyzer didn't hear it. A merge of neighbours with the same chord and bass is `true` only if either was; a split gives both halves the segment's flag |

A chord label is `<root>:<quality>` in Harte syntax. The root is one of `C C# D D# E F F# G G# A A# B`, spelled with sharps only, and the quality is one of `maj`, `min`, `7`, `maj7`, `min7`, `min6`, `hdim7`, `dim7`, `sus4`, `aug`, `dim`, `sus2` and `sus4(b7)`. `N` means no chord. A key label is the label of its tonic triad, `<root>:maj` or `<root>:min`, sharps only. `bass` is spelled the same way, as a bare root.

`chord` and `numeral` stay root-position labels. A slash chord is `chord` over `bass`: `C:maj` with bass `E` is C/E. Figured-bass numerals (`I6`, `V65`) are not written, since they follow from `numeral` and `inversion` by a fixed table. A bass move shorter than 2 beats under an unchanged chord is neither reported nor cut on, because it would turn a held chord into a flicker of inversions without changing the harmony. Consecutive segments may repeat a `chord` when the bass changes under it; in v1 and v2 they never did.

Segments are contiguous: each `start_beat` equals the previous `end_beat`, and the first starts at beat 0. Leading and trailing silence is labeled `N`. The only unlabeled span is the sub-beat head between the start of the audio and `beats[0]`, which is shorter than one beat.

The file is UTF-8, and non-ASCII characters are written as themselves rather than as `\u` escapes: the numerals' `ø` and `°`, and a non-ASCII `source.path`. A path that is not valid UTF-8 keeps `\u` escapes for the bytes that don't decode.

The schema is stable. Any change to the documented schema, an added field included, is breaking and bumps `schema_version`. Schema 4 kept schema 3's fields and widened what they hold: the chord qualities, the numerals, what `third` means in `inversion`, which chords `secondary_dominant` covers, and what `candidates[1]` means after a respelling. Schema 5 added `segments[].edited`, so a corrected chord is told apart from a heard one. Schema 6 added `generator.engine`; a file below 6 was written by the DSP. Schema 7 widened the chord vocabulary (`aug`, `dim`, `sus2`) and the numerals (`+`, `°`, `sus2`). Schema 8 widened the chord vocabulary (`sus4(b7)`) and the numerals (`7sus4`). The viewer reads 4 to 8 and saves an 8: it fills in `edited: false` on a 4, and on a 4 or 5 the engine `{"name": "dsp", "version": <generator.version>}`.

```json
{
  "schema_version": 8,
  "generator": {"name": "chordotomy", "version": "0.0.0", "engine": {"name": "dsp", "version": "0.0.0"}},
  "source": {"path": "song.mp3", "duration": 5.0},
  "key": {"label": "C:maj", "source": "estimated", "candidates": ["C:maj", "F:maj", "G:maj"]},
  "beats": [0.023, 0.534, 1.045, 1.533, 2.043, 2.531, 3.042, 3.529, 4.04, 4.528],
  "segments": [
    {
      "start_beat": 0, "end_beat": 2, "start_time": 0.023, "end_time": 1.045,
      "chord": "C:maj", "candidates": ["C:maj", "C:7", "C:maj7"],
      "bass": "C", "inversion": "root",
      "numeral": "I", "role": "diatonic", "function": "tonic", "target": null, "edited": false
    },
    {
      "start_beat": 2, "end_beat": 4, "start_time": 1.045, "end_time": 2.043,
      "chord": "C:maj", "candidates": ["C:maj", "C:7", "A:min7"],
      "bass": "E", "inversion": "first",
      "numeral": "I", "role": "diatonic", "function": "tonic", "target": null, "edited": false
    },
    {
      "start_beat": 4, "end_beat": 6, "start_time": 2.043, "end_time": 3.042,
      "chord": "F:maj7", "candidates": ["F:maj7", "F:maj", "F:7"],
      "bass": "F", "inversion": "root",
      "numeral": "IVmaj7", "role": "diatonic", "function": "predominant", "target": null, "edited": false
    },
    {
      "start_beat": 6, "end_beat": 8, "start_time": 3.042, "end_time": 4.04,
      "chord": "F#:hdim7", "candidates": ["F#:hdim7", "A:min6", "A:min"],
      "bass": "F#", "inversion": "root",
      "numeral": "viiø7/V", "role": "secondary_dominant", "function": null, "target": "V", "edited": false
    },
    {
      "start_beat": 8, "end_beat": 10, "start_time": 4.04, "end_time": 5.0,
      "chord": "G:7", "candidates": ["G:7", "G:maj", "E:min"],
      "bass": "B", "inversion": "first",
      "numeral": "V7", "role": "diatonic", "function": "dominant", "target": null, "edited": false
    }
  ]
}
```

## Editing in the viewer

The viewer corrects a timeline that `chordotomy analyze` wrote. The editing model is `viewer/edit.js`: pure functions that take a timeline and return a new one, sharing the segments they didn't change. `viewer/app.js` wires them to the page.

An edit acts on the current segment, the one under the playhead. A pick takes a moment, and playback may move on meanwhile. So while one of the Root, Quality and Bass selects has focus, or the pointer is pressed on it, the target is pinned to the segment that was current when that began. Split, Merge and Delete act on the segment that was current when their press began, for the same reason.

There are five operations:

- **Set a chord:** a chord and bass for one segment, from the selects or a candidate. `inversion` follows from the two. `candidates` stay what the analyzer heard, so its other readings stay on offer. Choosing the chord and bass the segment already has is not an edit.
- **Split** at a beat strictly inside a segment. Both halves keep everything the segment had, `edited` included, since neither half's chord changed.
- **Merge** a segment with the one before or after. It keeps its chord, bass and candidates over both spans.
- **Delete** a segment. The one before takes its span, or the next one for the first segment. A lone segment can't be deleted: nothing would take its span, and setting it to `N` silences it.
- **Set the key:** a key fixes it as `--key` does, with `source: given`, and Estimated estimates it again from the chords.

An edit never merges neighbours that end up with the same chord. The analyzer writes such neighbours itself when the bass changes under a chord, a split would undo itself before the user could change one half, and the analysis already reads them as one chord run. Merging is explicit.

Boundaries only move onto beats the analyzer found, so the viewer can correct a timeline but not start one. Segment times are read from `beats`, or `source.duration` at the end, as `chordotomy analyze` writes them. Nothing is computed, so an edit adds no rounding.

Every edit ends in a re-analysis. The segments are grouped into chord runs, and `viewer/harmony.js`, the port of "Harmonic analysis", estimates the key again and recomputes every segment's numeral, role, function and target. A given key keeps its label, and only its candidates follow the chords. Diminished and augmented twins are not respelled: a chord the user picks is spelled as picked, and the others keep the analyzer's spelling. Opening a file doesn't re-analyze, so the analyzer's fields stand until the first edit.

Undo keeps whole timelines, not inverse edits. They are small, and each snapshot shares the segments its edit didn't change. Undoing back to the timeline as opened or last saved gives back that very object, which is how the page knows nothing is unsaved. An edit that changes nothing adds no step.

`edited` keeps the provenance: it marks a segment whose chord and bass are the user's, not the analyzer's. The field's row above says what each operation does to it. The `explain-harmony` skill reads it, so it doesn't present an edited chord's candidates as alternative readings.

Saving downloads the timeline as `<stem>.edited.chords.json`, where `<stem>` is the basename of `source.path` without its extension, so `song.edited.mp3` saves as `song.edited.edited.chords.json`, the name the skill looks for next to the recording. Without a usable `source.path`, `<stem>` is the opened file's name without `.edited.chords.json`, `.chords.json` or `.json`. The file is a `Blob` downloaded through an `<a download>` link, because that works from `file://` in every browser and sends nothing anywhere. The viewer never writes to the file it opened, so what the analyzer wrote stays as it was, and the skill looks for the edited name first. The timeline counts as saved once the download starts; if the user cancels a browser's save dialog, the page can't tell.

A batch of dropped or picked files opens whole or not at all, so the recording and the timeline shown are always a pair the user chose together. The timeline is read and validated before anything changes, every field of every segment included, so whatever opens can be drawn and edited. With unsaved edits the viewer asks once before it replaces them, and the browser asks before the page closes. A batch with only a recording replaces the recording and keeps the edits.

## Evaluation

`chordotomy evaluate {tiny-aam,guitarset} [--limit N] [--engine auto|model|dsp]` scores the analyzer on real audio. It is opt-in and for development (the `eval` extra). Nothing in it reaches the timeline JSON. Both datasets are CC BY 4.0 on Zenodo. They are downloaded on demand into the checkout's gitignored `datasets/`, never committed.

- **Tiny AAM**: 20 mixed tracks with one chord per beat, reduced to major, minor and `N`. Its annotation has no bass, so its `majmin_inv` assumes every reference chord is in root position; read it as bass agreement with that assumption, not as inversion accuracy. The annotation stops at the last played beat. The reference gives that beat the length of the gap before it, so a tempo change at the end is respected, and labels the rest of the file `N`. Until stage II it ran the last chord to the end of the file, which called the silent tail a chord, so an analyzer that called the tail `N` lost about 1 pp of every chord metric ("Corrected Tiny AAM reference" below).
- **GuitarSet**: the 180 accompaniment takes (`_comp`, mono mic), scored against the performed chord annotation, which carries the bass.

Scoring is `mir_eval`, and the table is per track with an `overall` row weighted by duration. These things matter when reading it:

- `majmin` reduces sevenths and sixths to the triad. It leaves out power chords, sus, augmented and diminished chords, so those intervals are not counted at all.
- `N` against `N` counts as correct. A track the analyzer calls all `N` is scored right wherever the reference is also `N`, so `N_est` and `N_ref`, the shares of duration labeled `N`, are printed beside the scores. `N_prec` is the share of the estimate's `N` that is `N` in the reference, and `N_rec` the share of the reference's `N` that the estimate calls `N`, both by duration over the same intervals as the chord columns. Either is `nan` when there is no `N` to divide by; GuitarSet's reference has none.
- `beat_F`, `CMLt` and `AMLt` score the timeline's own `beats`, the extended grid that every consumer reads and both engines snap to, against Tiny AAM's annotated beat times and GuitarSet's `beat_position` annotation. They are mir_eval's F-measure, Correct Metric Level Total and Any Metric Level Total. `CMLt` needs the right metrical level and phase; `AMLt` also accepts double tempo, half tempo and the off-beat. Both datasets skip beats before `BEAT_MIN_TIME` = 5 s, mir_eval's default, passed explicitly; a median GuitarSet take loses about 17 % of its length to it. The beat columns are weighted by duration, like the chord columns. `period` is the median estimated beat gap over the median reference gap, and its overall is the median over tracks: near 2 is a grid locked at half tempo, near 0.5 one at double.
- `sevenths` scores only references that are `maj`, `min`, `7`, `maj7`, `min7` or `N`, and needs the seventh to match. On Tiny AAM, whose references are all major, minor or `N`, it is therefore a false-positive check (see "Tuning the v4 constants").
- `tetrads` needs the root and the whole pitch set to match. It is the metric that checks the full pitch set of a half-diminished, diminished-seventh, minor-sixth, sus4, augmented, diminished, sus2 or 7sus4 reference: `root` scores only their roots, `majmin` leaves out half-diminished, diminished-seventh, sus4, augmented, diminished, sus2 and 7sus4 references (it compares a minor-sixth one by its minor triad), and `sevenths` leaves out all of them.
- `majmin_inv` compares the bass as a scale degree above the root, so a right chord over the wrong bass, or over no detected bass (`bass` null), fails it.
- A segment whose bass is not its root is scored as a slash chord (`C:maj/3`), and mir_eval reads the slash's degree into the estimate's pitch set. A bass on a chord tone adds nothing, but a bass outside the chord adds a tone: `C:maj/2` is C–D–E–G. So a `non_chord` bass costs `sevenths` and `tetrads`, and `majmin` too when it lies within a perfect fifth above the root, the part of the pitch set `majmin` compares. `root` ignores the bass.
- `bass_ref`, `inv_prec`, `inv_rec` and `nonchord` score the bass beat by beat. Each beat lasts until the next one (the last until the end of the source), and its reference label is the interval holding the beat's midpoint; none, an `N` or an `X`, is a reference `N`. The first three are ratios with their own denominators, and the `overall` cell is the summed hits over the summed denominators, so a track weighs by what it adds to that metric, not by its length (a track's cell is `nan` only when its denominator is empty). `bass_ref`: of the beats where both the estimate and the reference are chords, the share whose written bass is the reference's; a null bass is a miss. An inversion is a bass off the root and on a tone of the chord, so a `non_chord` bass is not one. `inv_prec`: of the estimate's inversion beats, the share where the reference is an inversion over the same bass; `inv_rec`: of the reference's inversion beats, the share the estimate inverts over the same bass, an estimate `N` or null bass among them a miss. `nonchord` is the share of the duration in segments with `inversion == "non_chord"`, weighted by track duration. Tiny AAM's annotation has no bass, so its `bass_ref` reads the root, its `inv_rec` is `nan` and its `inv_prec` is 0 wherever an inversion is written, by assumption. Precision and recall count chord-tone inversions only: GuitarSet's non-chord reference slashes are its lowest string (4.4 % of its duration), not slashes a chart would write.

Each block of rows below records the analyzer at the commit that added it. The current rows are the last block, "Current rows".

Baseline, front end at `b70fb50`:

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.773 | 0.738 | 0.725 | — | 0.653 | 0.123 | 0.015 |
| GuitarSet (180 takes) | 0.485 | 0.519 | 0.460 | — | 0.335 | 0.450 | 0.000 |

On Tiny AAM the analyzer calls 12% of the duration `N` against 1.5% in the reference, and most of that is two tracks: 2720 (77% `N`) and 2990 (56%).

Whitened front end, at the commit that adds these rows. The root, majmin, sevenths and majmin_inv values reproduce the ones printed before `tetrads` existed. The decode constants were tuned on Tiny AAM; GuitarSet was held out. `BASS_WEIGHT`, `BASS_TONE`, `TEMPERATURE` and `CHORD_SECONDS` were the best Tiny AAM majmin among the values that kept the default test suite green. The suite is a hard constraint: two-beat chord changes and first-inversion chords must survive. Without it the best Tiny AAM majmin was about 0.823. The 0.788 below is the price of that constraint, chosen deliberately.

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.848 | 0.788 | 0.760 | 0.760 | 0.691 | 0.011 | 0.015 |
| GuitarSet (180 takes) | 0.688 | 0.619 | 0.492 | 0.317 | 0.373 | 0.007 | 0.000 |

v4 vocabulary, at the commit that adds these rows:

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.839 | 0.793 | 0.748 | 0.748 | 0.690 | 0.011 | 0.015 |
| GuitarSet (180 takes) | 0.720 | 0.661 | 0.531 | 0.347 | 0.395 | 0.007 | 0.000 |

GuitarSet's sevenths rise from 0.492 to 0.531, its majmin from 0.619 to 0.661 and its tetrads from 0.317 to 0.347, while Tiny AAM, annotated in major and minor only, gives up 0.9 pp of root and 1.2 pp of sevenths and calls a quality new in v4 on 3.7 % of its duration. The tuning signal was a sweep over cached features scored on the labels alone, without the bass. Those scores sit above these rows, because the CLI's scores also pay for basses outside the chord, as noted above for slash chords. At stage 1 the gap was up to 2.2 pp on Tiny AAM and 7.4 pp on GuitarSet, and the sweep raised each floor below by it. Under v4 it is larger, 2.5 pp of Tiny AAM sevenths and 9.0 pp of GuitarSet sevenths, and the sweep also checked every floor on the CLI's own scoring, reproduced from the cache.

### Tuning the v4 constants

The quality offsets, `TEMPERATURE`, `CHORD_SECONDS`, `BASS_WEIGHT`, `BASS_TONE` and `PARTIAL_DECAY` were tuned together by coordinate descent on the planned grid, the offsets and then the decode constants in turn until the point stopped moving. The objective is the highest GuitarSet sevenths over all 180 takes, whose two halves differ a lot. Tiny AAM is the false-positive guard: annotated in major and minor only, it scores a sus4 call as a majmin miss and a tetrad call as a sevenths miss. Its floors (root ≥ 0.835, majmin ≥ 0.775, sevenths ≥ 0.730, `N_est` within 0.02 of `N_ref`) bound how much of the vocabulary the decoder may use; GuitarSet has to keep majmin ≥ 0.60 and sevenths ≥ 0.512. The synthesized suite was a hard constraint on every point, the suspension test included: the offsets the datasets alone prefer, `sus4` at -0.3 or -0.4, smooth its four-beat `G:sus4` into the `G:maj` after it.

Each constant was then moved one grid step either way, and margin on the suite came first, because stage 1's point was one step from breaking an inversion test. At the descent's point, with `PARTIAL_DECAY` 0.6, one step of `TEMPERATURE` up, `BASS_WEIGHT` up, `BASS_TONE` down or `PARTIAL_DECAY` down smoothed away the two-beat `A:min/C` inside `C:maj`, the stage-1 binding case. Moving `PARTIAL_DECAY` to 0.8 was a cost: 0.3 pp of label-only GuitarSet sevenths, and Tiny AAM's root, majmin and sevenths from 0.844, 0.799 and 0.754 to 0.839, 0.793 and 0.748. It is what keeps the suite green at every one-step neighbour. `7`, `maj7`/`min7`, `min6`/`hdim7`, `dim7` and `CHORD_SECONDS` also hold every floor at both neighbours. Elsewhere Tiny AAM's root floor binds, cleared by 0.4 pp: one step of `sus4` up, `TEMPERATURE` down, `BASS_WEIGHT` down, `BASS_TONE` up or `PARTIAL_DECAY` up takes it to between 0.822 and 0.834. `sus4` is pinned from both sides, since at -0.3 the suspension test fails.

The chosen point is therefore not the objective's best. One step outside the grid, three neighbours score higher with the suite green and every floor held (GuitarSet sevenths on the CLI): `TEMPERATURE` 0.035 (0.534) and `BASS_TONE` 0.6 (0.532) were not taken because each uses up the `A:min/C` case's margin, which fails at `TEMPERATURE` 0.040 and with both moves together. `maj7`/`min7` at -0.05 (0.540) was not taken because it calls more sevenths on major and minor material: Tiny AAM sevenths falls to 0.744, and at the next step, 0, to 0.715, under its floor.

### Model engine

`chordotomy evaluate <dataset> --engine model` scores the lv-chordia engine, the default when the `model` extra is installed. The rows above are the DSP's, `--engine dsp`, which reproduced the v4 Tiny AAM row when the model engine was added.

Model engine, lv-chordia 1.1.0 on the DSP beat grid with the DSP bass, at the commit that adds these rows:

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.927 | 0.913 | 0.845 | 0.845 | 0.788 | 0.015 | 0.015 |
| Tiny AAM, labels only | 0.927 | 0.922 | 0.887 | 0.887 | — | 0.015 | 0.015 |
| GuitarSet (180 takes) | 0.827 | 0.787 | 0.676 | 0.441 | 0.466 | 0.032 | 0.000 |
| GuitarSet, labels only | 0.827 | 0.872 | 0.819 | 0.533 | — | 0.032 | 0.000 |

The rows were accepted against the planning spike's labels over the DSP's bass: lv-chordia's own labels, mapped to v4, snapped to the DSP's beats by the label covering most of each beat, and scored with the bass this engine writes. Those score 0.926, 0.912, 0.842 and 0.842 on Tiny AAM (root, majmin, sevenths, tetrads) and 0.827, 0.787, 0.676 and 0.440 on GuitarSet, and the CLI rows match them within 0.003. The labels-only rows score the same timelines without the bass. They match the spike's beat-snapped labels alone, 0.926, 0.922, 0.886 and 0.886 and 0.827, 0.872, 0.819 and 0.533, within 0.001, so the beat majority and the label mapping reproduce the spike's.

The CLI rows sit below the labels-only rows because of the bass. A DSP bass outside the model's chord becomes a slash degree, which mir_eval adds to the pitch set (see the slash-chord note above), on 5.0 % of Tiny AAM's duration and 19.4 % of GuitarSet's. The engine keeps it, because in band recordings such a bass is often real, a pedal point or a descending line, while on these two datasets it only costs: Tiny AAM's references carry no bass, and GuitarSet's solo guitar defeats `pick_bass`. Dropping those basses, which is not shipped, would give the labels-only majmin, sevenths and tetrads and a `majmin_inv` of 0.831 and 0.578.

`majmin_inv` here is the DSP's bass under the model's chords: 0.788 and 0.466, against the DSP engine's 0.690 and 0.395. The spike's `majmin_inv` with the model's own bass, 0.903 and 0.701, is not comparable. That bass is off the root on under 3 % of the duration, and the references are mostly in root position, on Tiny AAM all of them by assumption. A root-position prior scores well there without hearing a bass.

These rows are history. The engine's bass has since come from the bass head, and "Bass reliability" below has the rows that replace them.

The nets run in windows of at most `CHUNK_SECONDS` = 60 s. Tiny AAM's tracks are 123 to 181 s long, so each is split into three or four windows. On the whole track instead, Tiny AAM scores 0.926, 0.912, 0.843, 0.843, 0.786, 0.015 and 0.015, against the windows' 0.927, 0.913, 0.845, 0.845, 0.788, 0.015 and 0.015. The window would have gone up to 120 s had root, majmin or sevenths moved by more than 0.5 pp. They moved by 0.1 to 0.2 pp, so 60 s ships. GuitarSet's takes are 14 to 46 s, one window each.

Runtime and memory of `chordotomy analyze` on synthesized 3- and 6-minute mixes, on an Apple M4 (10 cores, torch 2.14.1). Time is wall time per audio minute, start-up included, the mean of two runs; memory is the peak resident set size. The whole-track rows set `CHUNK_SECONDS` above the clip's length.

| | 3 min: s per audio minute | 3 min: peak RSS | 6 min: s per audio minute | 6 min: peak RSS |
|---|---|---|---|---|
| `dsp` | 3.3 | 1.00 GB | 3.1 | 1.77 GB |
| model, 60 s windows (shipped) | 6.8 | 2.36 GB | 6.3 | 3.17 GB |
| model, whole track | 6.2 | 3.73 GB | 5.7 | 6.98 GB |

Importing torch and lv-chordia and loading the five nets takes 1.3 s and 0.28 GB, once per run; the model rows include it. The nets run on the CPU by construction, whatever torch is installed, so this is the only profile. Memory grows with length mostly through `beat_features`, by 0.26 to 0.27 GB per audio minute in both engines. The windows hold the nets' own share of the peak at 1.1 GB at both lengths, where the whole track took 2.5 GB at 3 minutes and 5.0 GB at 6. They make the run about 10 % slower than on the whole track.

### Corrected Tiny AAM reference

Corrected Tiny AAM reference, before the stage-II analyzer changes, at the commit that adds these rows. Both engines snap to the DSP's beat grid, so their beat columns are equal. GuitarSet's reference has no `N`, so its `N_rec` is `nan`.

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `dsp` | 0.848 | 0.802 | 0.758 | 0.758 | 0.700 | 0.011 | 0.032 | 0.951 | 0.324 | 0.826 | 0.686 | 0.766 | 0.999 |
| GuitarSet (180 takes), `dsp` | 0.720 | 0.661 | 0.531 | 0.347 | 0.395 | 0.007 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 |
| Tiny AAM (20 tracks), `model` | 0.939 | 0.924 | 0.857 | 0.857 | 0.800 | 0.015 | 0.032 | 0.965 | 0.442 | 0.826 | 0.686 | 0.766 | 0.999 |
| GuitarSet (180 takes), `model` | 0.827 | 0.787 | 0.676 | 0.441 | 0.466 | 0.032 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 |

With the analyzer unchanged, the Tiny AAM rows rise by the tail alone: the DSP's root, majmin and sevenths from the v4 row's 0.839, 0.793 and 0.748 to 0.848, 0.802 and 0.758, and the model's from 0.927, 0.913 and 0.845 to 0.939, 0.924 and 0.857. GuitarSet's reference did not change, and its chord and `N_est` columns equal the v4 and model rows above.

The period ratio and majmin on this grid of Tiny AAM's multi-tempo tracks:

| | period | majmin, `dsp` | majmin, `model` |
|---|---|---|---|
| 0080 | 2.018 | 0.570 | 0.602 |
| 0192 | 0.978 | 0.959 | 0.963 |
| 0620 | 1.000 | 0.907 | 0.959 |
| 1014 | 0.985 | 0.910 | 0.960 |
| 1050 | 1.505 | 0.848 | 0.887 |
| 1711 | 1.009 | 0.804 | 0.985 |
| 1941 | 0.657 | 0.802 | 0.897 |
| 2462 | 0.488 | 0.905 | 0.981 |
| 2720 | 1.013 | 0.575 | 0.858 |
| 2828 | 1.008 | 0.391 | 0.829 |
| 2990 | 1.013 | 0.626 | 0.895 |

And of every GuitarSet take whose ratio is within 10 % of 2 (nine: eight jazz takes and one bossa nova) or of 0.5 (six):

| | period | majmin, `dsp` | majmin, `model` |
|---|---|---|---|
| 03_Jazz1-200-B_comp | 1.897 | 0.000 | 0.000 |
| 04_Jazz1-200-B_comp | 1.937 | 0.445 | 0.803 |
| 05_Jazz1-200-B_comp | 1.937 | 0.000 | 0.000 |
| 04_Jazz2-187-F#_comp | 1.954 | 0.395 | 0.612 |
| 03_Jazz3-137-Eb_comp | 1.961 | 0.000 | 0.000 |
| 02_Jazz3-150-C_comp | 1.975 | 0.601 | 0.623 |
| 01_BN2-166-Ab_comp | 1.992 | 0.528 | 0.500 |
| 02_Jazz1-200-B_comp | 2.013 | 0.900 | 0.900 |
| 04_Jazz3-150-C_comp | 2.030 | 0.490 | 0.604 |
| 03_Funk3-98-A_comp | 0.493 | 0.634 | 0.693 |
| 04_Funk3-98-A_comp | 0.493 | 0.230 | 0.522 |
| 04_Rock2-85-F_comp | 0.493 | 0.923 | 0.989 |
| 05_Funk3-98-A_comp | 0.493 | 0.189 | 0.407 |
| 02_SS1-68-E_comp | 0.500 | 0.976 | 0.989 |
| 04_SS1-68-E_comp | 0.500 | 0.997 | 0.993 |

The zeros say little. 03_Jazz1-200 and 05_Jazz1-200 have no reference chord that `majmin` compares (each omits its root or fifth, or is a sus chord), and mir_eval scores an empty comparison as 0. 03_Jazz3-137 has one, a 1.75 s `G:min7/b7` out of 28 s, which both engines miss.

### The octave check

The octave check at the commit that adds these rows. That commit also had a tempo rule, which a later one removed ("Tempo changes are not followed"); its cells are not kept here. The check doubled no track: none of Tiny AAM's 20 (one, 0080, had a ratio within 10 % of 2 on the grid above) and none of GuitarSet's 180 (nine had). So there is no false trigger among the tracks whose ratio was within 10 % of 1 (16 and 104), and every track's period and majmin are the grid's, above. The half- and double-tempo tracks of the tables above and Tiny AAM's multi-tempo tracks follow: `changes` is the number of chord changes decoded on the doubled grid and `share` the share of them on inserted beats; the check doubles at 24 changes and 0.80. The model's columns are scored from its cached frames, which reproduce the CLI's rows within 0.001.

| | group | period | changes | share | majmin, `dsp` | majmin, `model` |
|---|---|---|---|---|---|---|
| 0080 | half tempo, multi-tempo | 2.018 | 78 | 0.19 | 0.570 | 0.602 |
| 01_BN2-166-Ab_comp | half tempo | 1.992 | 16 | 0.19 | 0.528 | 0.500 |
| 02_Jazz1-200-B_comp | half tempo | 2.013 | 6 | 0.67 | 0.900 | 0.900 |
| 02_Jazz3-150-C_comp | half tempo | 1.975 | 18 | 0.67 | 0.601 | 0.623 |
| 03_Jazz1-200-B_comp | half tempo | 1.897 | 14 | 0.57 | 0.000 | 0.000 |
| 03_Jazz3-137-Eb_comp | half tempo | 1.961 | 35 | 0.49 | 0.000 | 0.000 |
| 04_Jazz1-200-B_comp | half tempo | 1.937 | 22 | 0.41 | 0.445 | 0.803 |
| 04_Jazz2-187-F#_comp | half tempo | 1.954 | 30 | 0.33 | 0.395 | 0.612 |
| 04_Jazz3-150-C_comp | half tempo | 2.030 | 40 | 0.60 | 0.490 | 0.604 |
| 05_Jazz1-200-B_comp | half tempo | 1.937 | 20 | 0.65 | 0.000 | 0.000 |
| 2462 | double tempo, multi-tempo | 0.488 | 91 | 0.08 | 0.905 | 0.981 |
| 02_SS1-68-E_comp | double tempo | 0.500 | 10 | 0.50 | 0.976 | 0.989 |
| 04_SS1-68-E_comp | double tempo | 0.500 | 6 | 0.50 | 0.997 | 0.993 |
| 03_Funk3-98-A_comp | double tempo | 0.493 | 53 | 0.53 | 0.634 | 0.693 |
| 04_Funk3-98-A_comp | double tempo | 0.493 | 64 | 0.56 | 0.230 | 0.522 |
| 05_Funk3-98-A_comp | double tempo | 0.493 | 46 | 0.46 | 0.189 | 0.407 |
| 04_Rock2-85-F_comp | double tempo | 0.493 | 34 | 0.35 | 0.923 | 0.989 |
| 0192 | multi-tempo | 0.978 | 51 | 0.29 | 0.959 | 0.963 |
| 0620 | multi-tempo | 1.000 | 117 | 0.16 | 0.907 | 0.959 |
| 1014 | multi-tempo | 0.985 | 108 | 0.11 | 0.910 | 0.960 |
| 1050 | multi-tempo | 1.505 | 79 | 0.27 | 0.848 | 0.887 |
| 1711 | multi-tempo | 1.009 | 81 | 0.21 | 0.804 | 0.985 |
| 1941 | multi-tempo | 0.657 | 153 | 0.15 | 0.802 | 0.897 |
| 2720 | multi-tempo | 1.013 | 250 | 0.30 | 0.575 | 0.858 |
| 2828 | multi-tempo | 1.008 | 130 | 0.49 | 0.391 | 0.829 |
| 2990 | multi-tempo | 1.013 | 223 | 0.29 | 0.626 | 0.895 |

The ten half-tempo tracks score 0.19 to 0.67: their halved grids sit in phase, or half in phase, with the chord changes, not between them, so the check leaves them.

### Stage II

The octave check, the per-beat Viterbi and the `N` gate, with a tempo rule that a later commit removed ("Tempo changes are not followed"). The rows of the commit that had the rule are not kept: the rows at the end of this stage, below, are the shipped ones, and the section after this has the rule's key numbers.

The margin of the five constants this stage adds, each one grid step either way with the others at the shipped point (no tempo rule), measured on the shipped analyzer. The default suite is green at all ten neighbours. The `dsp` engine's Tiny AAM rows come from `evaluate.run` (the gate is the DSP's alone, and the model's rows follow the grid, which the gate constants do not touch). The four octave neighbours (`OCTAVE_INSERTED_SHARE` 0.75 and 0.85, `OCTAVE_MIN_CHANGES` 20 and 28) and the four of `ONSET_FRACTION` (0.25, 0.75) and `N_HARMONIC_SHARE` (0.2, 0.4) leave every column of the shipped row unchanged. `N_FLATNESS` 0.03 does too, and 0.01 raises root and majmin by 0.007 and 0.008 pp (to 0.83944 and 0.79486). On GuitarSet the octave check's logged shares reach 0.708 among takes with 20 or more changes, under the loosest share, 0.75. One neighbour misses a perturbation bar: at `N_FLATNESS` 0.03 the median drum stem is 0.663 `N` against the bar's 0.70. Stepping in to 0.01 would put 0.00 one step away, which costs GuitarSet 2.6 pp of majmin, so 0.03 is an allowed neighbour, bound by the drums-alone bar.

The octave constants were planned at 0.75 and 20 changes and moved inward to 0.80 and 24 before this run. At 0.70, a neighbour of 0.75, two correctly tracked GuitarSet takes would be doubled; they score 0.70 and 0.71. At 16 changes, a neighbour of 20, so would an 84 BPM take whose grid is right, which scores 0.84 on 19 changes.

The rows at the end of the stage, `chordotomy evaluate` on the final reference (the last beat lasts the gap before it), after the tempo rule was removed. They were scored by `evaluate.run` with the model's frames from a cache, which reproduces the CLI's rows to every digit:

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `dsp` | 0.839 | 0.795 | 0.750 | 0.750 | 0.692 | 0.003 | 0.032 | 0.819 | 0.071 | 0.827 | 0.686 | 0.766 | 0.999 |
| GuitarSet (180 takes), `dsp` | 0.721 | 0.662 | 0.531 | 0.347 | 0.395 | 0.005 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 |
| Tiny AAM (20 tracks), `model` | 0.939 | 0.924 | 0.857 | 0.857 | 0.800 | 0.015 | 0.032 | 0.966 | 0.447 | 0.827 | 0.686 | 0.766 | 0.999 |
| GuitarSet (180 takes), `model` | 0.826 | 0.787 | 0.676 | 0.441 | 0.466 | 0.032 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 |

The pre-stage analyzer scores 0.848, 0.802, 0.758, 0.758, 0.700, 0.011, 0.032, 0.951, 0.324, 0.826, 0.686, 0.766 and 0.999 (`dsp`) and 0.939, 0.924, 0.857, 0.857, 0.800, 0.015, 0.032, 0.965, 0.442, 0.826, 0.686, 0.766 and 0.999 (`model`) on the same reference, which is what the floors start from. Unrounded, the `dsp` Tiny AAM root is 0.83937 against its floor of 0.83944, the pre-stage row's 0.84764 less the tonal-tail price of 0.00819: 0.007 pp under, accepted as a rounding-level miss. Its majmin, 0.79478, clears its floor of 0.79421. The model's 0.93886 and 0.92429 clear its pre-stage row's 0.93867 and 0.92411. The octave check doubled no track on either dataset, at its chosen point or at any one-step neighbour of its two constants. The highest shares among tracks with 20 or more changes are 0.61 on Tiny AAM and 0.71 on GuitarSet.

Against the pre-stage rows, the model's Tiny AAM root and majmin are within 0.02 pp: the grid is the same, and the per-beat Viterbi and the gate are the DSP's alone. The DSP's fall by 0.83 and 0.76 pp, and the tonal-tail price is 0.82 pp. That price is the reference `N` the gate now keeps as a chord, mostly ring-outs still tonal one beat after the last annotated beat, which the level gate used to force to `N`. The rest of the stage nets to within 0.06 pp: the octave check doubled nothing, and the per-beat Viterbi reproduces librosa's path on a constant grid. Against the commit that still had the tempo rule (Tiny AAM CMLt 0.785, `dsp` root and majmin 0.847 and 0.801, `model` 0.944 and 0.930, on the first version of the reference), the removal gave back what the rule had gained on Tiny AAM besides the CMLt: 0.8 and 0.6 pp of the DSP's root and majmin, 0.5 and 0.6 pp of the model's. GuitarSet moved by at most 0.4 pp on any column.

The `N` gate's perturbations of the 20 Tiny AAM mixes, decoded by the `dsp` engine (the gate is the DSP's alone), with the level gate alone before the stage and the shipped analyzer after. They are made locally from the dataset's mixes and drum stems and never committed. `N` is the share of the perturbed region's beats labeled `N`, pooled over tracks; for the drum stem alone (19 tracks have one) it is the median stem's share over the beats where the stem sounds. Agreement is the share of beats labeled as in the same analyzer's decode of the unperturbed mix: inside the region for the quiet intros, outside it for the prepended drums and the appended silence. A beat is in a region when its midpoint is, except that the appended-silence bar reads beats by their start.

| case | `N`, before | `N`, after | agreement, before | agreement, after | bar |
|---|---|---|---|---|---|
| first 20 s at -45 dB | 0.992 | 0.001 | 0.008 | 0.857 | `N` <= 0.10, agreement >= 0.6: held |
| first 20 s at -55 dB | 0.993 | 0.001 | 0.007 | 0.855 | none |
| the drum stem alone | 0.000 | 0.812 | — | — | `N` >= 0.70: held |
| 10 s of the drum stem prepended | 0.029 | 0.791 | 0.979 | 0.978 | `N` >= 0.70, agreement >= 0.95: held |
| 5 s of digital silence appended | 1.000 | 0.995 | 0.998 | 0.997 | every beat that starts in the silence is `N`: held, 174 of 174 |

Before, a quiet intro was `N` almost throughout and a drum stem never was. With the gate on tonal evidence, 0.1 % of the quiet intros' beats are `N`, at -45 dB and at -55 dB, and 86 % carry the chord the loud mix decodes there. The median drum stem is 81 % `N`, and 10 s of drums before the mix are 79 % `N` while the rest of the mix agrees with its own decode as before. In the appended silence 181 of the 182 beats whose midpoint is there are `N`; the one that is not, on 2720, starts 0.27 s before the silence and has its midpoint 8 ms into it, so it still sounds the last chord.

### Tempo changes are not followed

The tracker keeps one tempo per file. Two rules that followed a tempo change inside a file were built and measured, and both are out. The hybrid: the tempogram's local tempo, median-filtered over 10 s, replaced the global tempo when it stayed more than 10 % off it, folded to the octave, for 16 s. It switched 9 Tiny AAM tracks and raised Tiny AAM's CMLt from 0.686 to 0.785, +9.9 pp. It also switched four of GuitarSet's 180 constant-tempo takes and an 86 BPM pop recording whose local tempo flickers between metrical levels (86, 112, 129 and 172 BPM): the median departs without any change, and following it gave the recording 668 beats of 0.30 to 0.88 s for the global tracker's 437 of 0.60 to 0.74 s. A gate that also required the departure to read one tempo (at least 0.75 of its unsmoothed frames within 10 % of its median) stopped all five and raised CMLt to 0.813, +12.7 pp, but a syncopated figure held over an unchanged pulse reads one tempo too. Synthesized at 74 to 105 BPM, 22 s of hats in 3-3-2 sixteenths or in quarter-note triplets after 22 s on the eighths switched 39 of 40 clips under both rules, hats at a tenth of the kick's level included. Seven of GuitarSet's 30 s takes already hold one steady off-tempo reading for 10 to 15.6 s, and with the gate, one step of the hybrid's window, departure or hold switched takes or the pop recording again. Tiny AAM's tempo changes are 4:3 and 3:2 metric modulations, the ratios syncopation reads, and nothing measured told them apart: not the tempogram's support for the global period inside the departure, not the global grid's onset strength there, and not a curve read from the harmonic part instead. Syncopation is everyday in pop and a tempo change inside a song is rare, so the beat grid stays on the pulse. `test_a_syncopated_constant_tempo_keeps_the_global_grid` holds it there.

### Vocabulary v5

Vocabulary v5 adds `aug`, `dim` and `sus2`. Model engine, at the commit that adds these rows: lv-chordia's `aug`, `dim` and `sus2` map to their own labels instead of `maj`, `dim7` and the sus4 a fifth up.

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `model` | 0.939 | 0.924 | 0.857 | 0.857 | 0.800 | 0.015 | 0.032 | 0.966 | 0.447 | 0.827 | 0.686 | 0.766 | 0.999 |
| GuitarSet (180 takes), `model` | 0.827 | 0.787 | 0.676 | 0.441 | 0.466 | 0.032 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 |

Against the end of stage II ("Stage II"), Tiny AAM is unchanged to every digit and GuitarSet's root rises from 0.826 to 0.827. Two takes move, 00_BN2-166-Ab and 03_Rock2-85-F, whose root rises by 6.3 and 6.2 pp: mapped to a `dim7`, a diminished triad could be respelled by where it leads as another root of its diminished-seventh set (`G:dim7` as `E:dim7`), and as a `dim` it keeps the model's root. The model labels `dim` on 0.03 % of Tiny AAM's duration and 0.69 % of GuitarSet's, and `aug` and `sus2` on neither.

DSP engine, at the commit that adds these rows (`aug` -0.25, `dim` -0.10, `sus2` never called):

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `dsp` | 0.842 | 0.796 | 0.750 | 0.750 | 0.693 | 0.003 | 0.032 | 0.819 | 0.071 | 0.827 | 0.686 | 0.766 | 0.999 |
| GuitarSet (180 takes), `dsp` | 0.722 | 0.661 | 0.529 | 0.345 | 0.395 | 0.005 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 |

Against the end of stage II, Tiny AAM's root and majmin rise by 0.2 pp, and GuitarSet's majmin and sevenths fall by 0.1 pp and 0.2 pp, with the beat columns unchanged. The DSP labels `dim` on 0.32 % of Tiny AAM's duration and 1.5 % of GuitarSet's, `aug` on neither, and never `sus2`.

#### Tuning the v5 offsets

The 145-state transition costs nothing and gains a little. With `aug`, `dim` and `sus2` at -1, so that they never win and the only change is that the Viterbi's switch probability now spreads over 144 other states instead of 108, Tiny AAM's root and majmin rise from 0.83937 and 0.79478 to 0.84094 and 0.79683 (+0.16 and +0.20 pp), its sevenths stay at 0.750, and GuitarSet's majmin and sevenths are 0.66298 and 0.53029 against 0.662 and 0.531. That diagnostic point is what the new qualities are priced against. It is never a candidate, since it calls no new quality at all.

The DSP does not call `sus2`. `C:sus2` is `G:sus4`'s pitch set, and two synthesized cases pull its offset apart. A played Csus2 between C chords must be told from the triad: `C:sus2` clears `C:maj` by 0.285 less the offset on its beats, so the pair must stay at -0.175 or higher. A C triad with an added D, first an octave above it and then inside the voicing (an added ninth), must stay `C:maj`, and `C:sus2` clears `C:maj` by 0.30 there, more than it does on the played chord, so the pair must be -0.275 or lower. The existing four-beat `G:sus4` into `G:maj` needs -0.25 or higher. No shared value passes all three, nor does any one-step move of the decode constants. The datasets agree: at -0.25 `sus2` labels 1.5 % of Tiny AAM and costs 1.0 pp of its majmin (0.78686 against 0.79683), and holding Tiny AAM's floors takes -0.30. `sus2` stays in the vocabulary, the harmony and the viewer, and comes from the model engine or a manual edit; its offset is -inf, which `smooth` reads as a label that is never chosen and `segment` ranks last, so never a candidate. `sus4` stays at -0.25.

`aug` and `dim` were swept on a 0.05 grid from 0 to -0.6, every other variable at its v4 value, against floors taken from the diagnostic point: Tiny AAM root 0.84094, majmin 0.79683, sevenths within 0.5 pp of 0.75020, `N_est` unchanged and the new qualities' share at most 1 %; GuitarSet majmin 0.66298 and sevenths 0.53029. The objective was GuitarSet sevenths, then tetrads. The points that hold the floors are all the same point: `aug` and `dim` so low that neither is ever called, which scores exactly the diagnostic row. The synthesized suite does not allow it. The `vii°` case needs `dim` at -0.15 or higher, and the floors need -0.225 or lower. The bass-less `V+` case needs `aug` at -0.30 or higher, a bound the floors do not touch: from -0.20 to -0.30 `aug` scores the same on both datasets, so it sits at -0.25, the middle of that plateau.

So `aug` and `dim` are called, at a stated price: any floor may give at most 0.3 pp against the diagnostic point, Tiny AAM's root and majmin stay at or above the end of stage II's values (0.83937 and 0.79478), and the new qualities stay under 1 % of Tiny AAM. At the chosen point, against the diagnostic point:

| | root | majmin | sevenths | tetrads |
|---|---|---|---|---|
| Tiny AAM | +0.07 pp | -0.05 pp | -0.01 pp | -0.01 pp |
| GuitarSet | -0.07 pp | -0.24 pp | -0.12 pp | -0.24 pp |

The 0.3 pp is the same price v4 paid for `PARTIAL_DECAY`. `dim` was chosen between -0.10 and -0.15 by suite margin, v4's rule. Each variable was moved one step either way, down being more negative or a smaller constant, with the suite and the floors checked at each. At `dim` -0.10, three neighbours fail the suite: `sus4` at -0.30 (the suspension test, as in v4), and `dim` at -0.05 and `dim7` at -0.15, each failing the same three `dim7` tests, because a played diminished seventh stays a `dim7` only while `dim` is not above it. At `dim` -0.15 four neighbours fail: `sus4` at -0.30, `dim` at -0.20 and `PARTIAL_DECAY` 0.9 (the `vii°` case), and `7` at +0.05 (the `vii°` case), so -0.10 is the point. `aug` at -0.20 and -0.30 keep the suite green and score the same. Elsewhere the floors bind, as in v4: one step of `sus4` up (-0.20), `TEMPERATURE` down (0.025) or `BASS_TONE` up (0.8) takes Tiny AAM's root and majmin to 0.8356 and 0.7882, 0.8360 and 0.7880, and 0.8307 and 0.7861, and `7` at +0.05 takes its majmin and sevenths to 0.7886 and 0.7403. `BASS_WEIGHT` 0.25 leaves Tiny AAM's majmin at 0.79476 against 0.79478, at its bar. On GuitarSet, `BASS_WEIGHT` 0.35, `min6`/`hdim7` at -0.05 and `PARTIAL_DECAY` 0.7 take majmin to 0.6569, 0.6564 and 0.6582, and `7` at -0.05 takes sevenths to 0.5242.

### Vocabulary v6

Vocabulary v6 adds `sus4(b7)`, the 7sus4. Model engine, at the commit that adds these rows: lv-chordia's `sus4(b7)` maps to its own label instead of `sus4`, and `11` stays `7` because Harte's 11 includes the third.

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `model` | 0.939 | 0.924 | 0.857 | 0.857 | 0.800 | 0.015 | 0.032 | 0.966 | 0.447 | 0.827 | 0.686 | 0.766 | 0.999 |
| GuitarSet (180 takes), `model` | 0.827 | 0.787 | 0.676 | 0.441 | 0.466 | 0.032 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 |

Every track's beat grid is unchanged on all 200 tracks, compared directly: the caches rebuilt at the 157-label set hold the same `times` as v5's, so the octave check doubled nothing new (the highest share among tracks with at least 24 decoded changes is 0.60 on Tiny AAM and 0.68 on GuitarSet, against 0.80). The chord columns equal v5's to every digit on every track, because the model emitted no `sus4(b7)` on either dataset. The exact mapping is checked by the unit tests and by a recording analyzed locally, where 17 beats of `A:sus4` became `A:sus4(b7)` (`V7sus4`, diatonic, dominant in D major) with the grid, the key and every other beat unchanged.

DSP engine, at the commit that adds these rows (`sus4(b7)` never called):

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `dsp` | 0.842 | 0.796 | 0.750 | 0.750 | 0.693 | 0.003 | 0.032 | 0.819 | 0.071 | 0.827 | 0.686 | 0.766 | 0.999 |
| GuitarSet (180 takes), `dsp` | 0.722 | 0.661 | 0.529 | 0.345 | 0.395 | 0.005 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 |

The rows equal v5's to the printed digits: the DSP never calls `sus4(b7)`, so it labels none of either dataset, and the only change is the 157-state transition (below). A locally analyzed recording, DSP engine, has the same beats and every beat's chord as under v5.

#### Tuning the v6 offset

The caches were rebuilt at the 157-label set before any point was scored, because the octave check ("The octave check") decodes the doubled grid with the vocabulary and the offsets, so v5's caches hold grids from a decoder that no longer exists. The direct comparison found every track's `times` equal to v5's, on all 200 tracks. Each swept point was scored on the grid it produces: the octave decision was recomputed per track from the cached inputs at that offset, and no track flipped at any point from 0 to -0.6, so no track was rebuilt. The highest share among tracks with at least 24 decoded changes at any swept point was 0.65 on Tiny AAM (track 1050) and 0.72 on GuitarSet (02_SS2-107-Ab_comp), against 0.80; at the committed point they are 0.60 and 0.68.

The diagnostic point, `sus4(b7)` never called, is the committed one, and the floors are taken from it. The 157-state transition (a switch costs 0.08 nats more) moves v5's shipped rows by +0.00 pp on Tiny AAM's root and majmin and +0.01 pp on its sevenths (0.75005 to 0.75020), and on GuitarSet's majmin, sevenths and tetrads by +0.04, +0.04 and +0.01 pp (0.66055, 0.52905 and 0.34458 to 0.66096, 0.52941 and 0.34467). The floors: Tiny AAM root and majmin at most 0.3 pp under it and at or above v5's 0.84161 and 0.79635, which are the diagnostic values to five digits; sevenths within 0.5 pp; `N_est` unchanged; `sus4(b7)` at most 1 % of its duration; GuitarSet majmin and sevenths at most 0.3 pp under it.

`sus4(b7)` was swept alone on a 0.05 grid from 0 to -0.6, refined to steps as small as 0.0025 where a bound fell between points. Three synthesized cases bound it, and no shared value passes them and the floors:

- A played V7sus4 in the D major cadence (A3 D4 E4 G4 over an A2 bass, then the dominant seventh) needs -0.23 or higher: the suite is green at -0.23 and the cadence case fails at -0.2325.
- A plain Asus4 into A and the existing G:sus4 and added-ninth cases need -0.0875 or lower: the suite is green at -0.0875, the G:sus4 suspension and the added ninth fail at -0.075, and the plain Asus4 fails too at -0.0625.
- The floors need -0.2375 or lower. Above it Tiny AAM's root or majmin is under v5's, by 0.03 pp of root at -0.22 to -0.23 (0.84132), 0.06 pp of majmin at -0.20 (0.79572), and 0.33 pp of majmin at -0.15, where `sus4(b7)` also covers 1.5 % of Tiny AAM, over the 1 % bar. At -0.10 the loss is 0.35 pp of root, 0.91 pp of majmin and 0.46 pp of GuitarSet's majmin.

The interval is empty. The cadence needs -0.23 and the floors -0.2375, 0.0075 apart; at -0.2375 the suite fails only the cadence and every floor holds, and at -0.23 the suite is green and Tiny AAM's root is 0.03 pp under (0.84132 against 0.84161), with GuitarSet's majmin and sevenths 0.66011 and 0.52852. Nor would -0.23 pass v5's margin rule: it lies 0.0025 above the cadence's failure, so a one-step neighbour fails the suite and the other the floors. The DSP therefore never calls `sus4(b7)`: its offset is -inf, as `sus2`'s is, and `test_the_dsp_never_calls_a_seventh_sus4` and `test_the_decoder_never_calls_a_seventh_sus4` hold it there. `sus4(b7)` stays in the vocabulary, the harmony and the viewer, and comes from the model engine or a manual edit. The plain Asus4 into A and the dominant seventh stay in the suite as synthesized cases.

### Bass reliability

`segment` takes one bass per beat, and when no value holds `BASS_HOLD` beats the vote ranks a tied bass by count, then by being a tone of the segment's chord, then by being a note, then by the earliest beat. A two-beat chord whose beats disagreed took beat 1 before, so a passing note on the first beat was written as a slash: `[D#, C]` under `C:maj` wrote `C/D#` and now writes `C`. `[E, C]` still writes `E` (both chord tones, earliest), and `[D, C#]` writes `D` (neither, earliest). A synthesized `G` for six beats and then `C` over D#2 and C2 is the red case, and a held `D/E` stays a slash. The grid and the chroma are untouched: only `bass`, `inversion` and what `resolve_twins` reads from the bass can move, and `root` does not move on either engine or dataset.

The tie-break, at the commit that adds these rows. The first two rows are the DSP engine, the last two the model engine, whose bass is still the DSP's pick:

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period | bass_ref | inv_prec | inv_rec | nonchord |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `dsp` | 0.842 | 0.799 | 0.756 | 0.756 | 0.697 | 0.003 | 0.032 | 0.819 | 0.071 | 0.827 | 0.686 | 0.766 | 0.999 | 0.838 | 0.000 | nan | 0.034 |
| GuitarSet (180 takes), `dsp` | 0.722 | 0.675 | 0.551 | 0.359 | 0.407 | 0.005 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 | 0.478 | 0.170 | 0.231 | 0.153 |
| Tiny AAM (20 tracks), `model` | 0.939 | 0.926 | 0.864 | 0.864 | 0.804 | 0.015 | 0.032 | 0.966 | 0.447 | 0.827 | 0.686 | 0.766 | 0.999 | 0.851 | 0.000 | nan | 0.041 |
| GuitarSet (180 takes), `model` | 0.827 | 0.800 | 0.699 | 0.455 | 0.476 | 0.032 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 | 0.503 | 0.202 | 0.227 | 0.163 |

Against the rows before it (the unrounded baselines, with the four bass columns scored on them), in percentage points. No floor is given back, and `root`, `N_est` and the beat columns do not move.

| | majmin | sevenths | tetrads | majmin_inv | bass_ref | inv_prec | inv_rec | nonchord |
|---|---|---|---|---|---|---|---|---|
| Tiny AAM, `dsp` | +0.23 | +0.57 | +0.57 | +0.43 | +0.46 | 0.00 | nan | -1.24 |
| GuitarSet, `dsp` | +1.41 | +2.14 | +1.40 | +1.26 | +1.34 | -0.00 | +1.65 | -4.25 |
| Tiny AAM, `model` | +0.15 | +0.72 | +0.72 | +0.37 | +0.45 | 0.00 | nan | -0.89 |
| GuitarSet, `model` | +1.27 | +2.26 | +1.45 | +1.04 | +1.02 | -0.18 | +1.10 | -3.00 |

The scores gain because a non-chord bass is scored as a slash that adds a tone to the estimate's pitch set (see above), and the tie-break removes the passing notes that did that.

#### The DSP's salience test

`beat_basses(states, cqt)` gives `segment` the DSP's per-beat basses. It is `pick_bass` per column, except that a pick outside the beat's chord must be at least `NONCHORD_SALIENCE` of the register's strongest note (`_bass_peak` returns the bin `pick_bass` picks and that height), else the beat reads the chord's root. A chord tone is written as heard whatever its height; an `N` beat and a silent register give the plain pick. At 0.5 (`BASS_SALIENCE`) every pick passes and the rule is the tie-break's. The root is a fallback, not a measured note: a segment whose weak non-chord bass fell back reads root position. `beat_basses` (and the model's `beat_bass`) flag each beat whose value is the fallback, and `segment` turns those flags into a segment's internal `bass_heard`, whether its bass was heard on any beat; `resolve_twins` counts only a heard root as evidence, so a fallback root does not hold a `min6` or `aug` spelling. `features` still zeroes the bass chroma with the plain `pick_bass`, so the grid, the chroma and `root` are the same as before the rule.

Branch R, shipped: `NONCHORD_SALIENCE = 1.0`, a non-chord pick must be the loudest note of the register. The sweep scores the cached v6 DSP features per point (the suite is `test_timeline.py`, `test_chords.py` and `test_features.py`; the bridge column counts how many of the recording's five bridge spots, 201.4, 204.2, 207.1, 208.5 and 215.5 s, read without a non-chord slash on its DSP timeline, and the two `D/E` and the `A` at 209.2 s kept their bass at every point). Tiny AAM and GuitarSet cells are majmin / sevenths / majmin_inv:

| `NONCHORD_SALIENCE` | suite | bridge spots | Tiny AAM | GuitarSet | GuitarSet inv_rec | nonchord, Tiny AAM / GuitarSet |
|---|---|---|---|---|---|---|
| 0.50 (tie-break only) | green | 2 | 0.7987 / 0.7559 / 0.6973 | 0.6750 / 0.5508 / 0.4071 | 0.2310 | 0.0339 / 0.1532 |
| 0.55 | green | 3 | 0.7995 / 0.7574 / 0.6987 | 0.6791 / 0.5556 / 0.4158 | 0.2303 | 0.0321 / 0.1423 |
| 0.60 | green | 4 | 0.8000 / 0.7611 / 0.7027 | 0.6821 / 0.5614 / 0.4213 | 0.2277 | 0.0280 / 0.1323 |
| 0.65 | green | 4 | 0.8002 / 0.7616 / 0.7036 | 0.6829 / 0.5621 / 0.4229 | 0.2267 | 0.0272 / 0.1261 |
| 0.70 | green | 4 | 0.8002 / 0.7627 / 0.7049 | 0.6853 / 0.5670 / 0.4291 | 0.2270 | 0.0248 / 0.1182 |
| 0.75 | green | 5 | 0.8002 / 0.7627 / 0.7057 | 0.6863 / 0.5688 / 0.4311 | 0.2267 | 0.0247 / 0.1136 |
| 0.80 | green | 5 | 0.8004 / 0.7636 / 0.7069 | 0.6878 / 0.5720 / 0.4349 | 0.2273 | 0.0238 / 0.1069 |
| 0.85 | green | 5 | 0.8023 / 0.7661 / 0.7097 | 0.6906 / 0.5745 / 0.4384 | 0.2273 | 0.0211 / 0.1013 |
| 0.90 | green | 5 | 0.8027 / 0.7673 / 0.7113 | 0.6921 / 0.5784 / 0.4416 | 0.2248 | 0.0198 / 0.0957 |
| 0.95 | green | 5 | 0.8027 / 0.7673 / 0.7118 | 0.6932 / 0.5801 / 0.4436 | 0.2258 | 0.0198 / 0.0924 |
| **1.00** | green | 5 | 0.8027 / 0.7675 / 0.7126 | 0.6958 / 0.5825 / 0.4460 | 0.2258 | 0.0197 / 0.0871 |
| 1.01 | red | 5 | 0.8054 / 0.7745 / 0.7237 | 0.7226 / 0.6197 / 0.4755 | 0.2007 | 0.0000 / 0.0000 |

Every point meets the floors and `N_est` is unchanged. GuitarSet's `inv_rec` stays above 0.9 of the baseline's 0.2145 (0.1931) at every point, and `root` does not move at the shipped value (at 0.60 one `resolve_twins` respelling moves GuitarSet's below the fifth digit). The objective, in order, is the bridge spots freed, then GuitarSet majmin_inv, then the lower `nonchord`: five spots from 0.75 up, then 1.00 on the second and third. Nothing is a tie, since each step up adds 0.2 to 0.4 pp of GuitarSet majmin_inv. Above 1.0 even the loudest pick fails the test, so no non-chord slash is ever written, and `test_a_held_non_chord_slash_survives` and `test_bass_and_inversion_follow_the_bass_line` fail: 1.01 is red, and its higher scores are the price of writing none. 1.0 is therefore the top of the range the rule means, not a plateau with a neighbour above it; its neighbour below, 0.95, meets every constraint. The chart's rejected picks have heights 0.53 to 0.74 (the one-beat `Bm7/G`, `F#7/C` and `Bm7/D#`) and the kept `D/E` and `Bm/A` beats sit at 1.0.

`test_a_weak_non_chord_bass_reads_root_position` is a synthesized case: a D1 struck with a C2 under `C:maj` is the lowest salient note but 0.85 of the register's strongest, and reads `C` in root position (it reads `C/D` at 0.5).

The rule at the commit that adds these rows, scored by the CLI, against the tie-break's rows above (percentage points; the model engine is unchanged):

| | majmin | sevenths | tetrads | majmin_inv | bass_ref | inv_prec | inv_rec | nonchord |
|---|---|---|---|---|---|---|---|---|
| Tiny AAM, `dsp` | +0.41 | +1.16 | +1.16 | +1.53 | +1.30 | 0.00 | nan | -1.42 |
| GuitarSet, `dsp` | +2.08 | +3.17 | +2.04 | +3.89 | +2.84 | +0.37 | -0.52 | -6.62 |

On the recording's DSP timeline the chords do not change and 18 beats change their bass, which takes the seconds written as `non_chord` from 23.3 to 10.6. The bridge: `Edim/A` at 201.4 s reads `Edim/G` (the tie-break already, a chord tone), `F#/C` at 207.1 s reads `F#`, `Bm/G` at 208.5 s reads `Bm` and `Bm/D#` at 215.5 s reads `Bm`; 204.2 s was `F#m` already. The weak picks elsewhere go the same way: `A7/A#` at 108.9 s and `A7/D#` at 177.4 s read `A7`, and `Em/A` at 154.8 s keeps its `A` for one beat group and then reads `Em`. Kept: the `D/E` reads at 64.5 s and 160.5 s (the DSP spells them `E7/E` and `Esus4/E`, their bass `E`), `D/A` at 209.2 s, and the unverified `D/D#` at 115.3 s, `G/F#` at 146.4 s and `D/B` at 285.8 s, whose picks are the register's loudest.

#### The model's bass head

The model engine's bass comes from lv-chordia's bass head, which the engine computed and threw away before: `recognize` returns it as a third array, `(n_frames, 13)` with index 0 "no bass" and `1 + pitch class` otherwise, and `timeline` averages it over each beat's frames as it does the scores, giving `(13, n_beats)`. `beat_bass(head, states, picks)` then gives `segment` one bass per beat. Per chord beat the candidates are the DSP's plain `pick_bass` (absent when the register is silent) and then the head's note (the argmax of the twelve notes, absent when "no bass" is the largest of the thirteen). The first candidate that is a tone of the chord is the bass, never gated; otherwise the first non-chord candidate whose posterior in the head is at least `BASS_SUPPORT`; otherwise the chord's root, which is a fallback and not a measured note; and `null` only when there was no candidate, the head hearing no bass and the register silent. An `N` beat has `null`. So "no bass" is consulted only after a DSP pick has failed its test or was absent.

Branch H, shipped: variant A (the DSP's pick first) with `BASS_SUPPORT = 0.7`. Variant B considers the head's note alone, and was swept beside A at the same eight values. The ship rule's constraints are the floors (the unrounded rows before the bass work: neither majmin, sevenths nor majmin_inv on either dataset falls below them, and `N_est` does not move), GuitarSet `inv_rec` at or above 0.9 of the tie-break's 0.2273 (0.2046), and on the recording's model timeline the two `D/E` keeping `E`, the `Bm/A` keeping `A`, the five bridge spots at the root and the `C#7` at the root. The objective is GuitarSet majmin_inv, then `bass_ref`, then Tiny AAM majmin_inv. Cells are majmin / sevenths / majmin_inv; the last two columns are the share of GuitarSet's chord beats whose bass fell back to the root and the share that wrote `null`. "Chart" says whether the recording's constraints held:

| | tau | floors | GuitarSet inv_rec | chart | Tiny AAM | GuitarSet | bass_ref, Tiny AAM / GuitarSet | nonchord, Tiny AAM / GuitarSet | fallback / null, GuitarSet |
|---|---|---|---|---|---|---|---|---|---|
| A | 0.10 | met | 0.2106 | kept | 0.9340 / 0.8974 / 0.8668 | 0.8713 / 0.8171 / 0.5901 | 0.9149 / 0.6056 | 0.0021 / 0.0061 | 0.0003 / 0.0006 |
| A | 0.20 | met | 0.2097 | kept | 0.9340 / 0.8974 / 0.8668 | 0.8710 / 0.8167 / 0.5898 | 0.9149 / 0.6057 | 0.0021 / 0.0063 | 0.0004 / 0.0006 |
| A | 0.30 | met | 0.2097 | kept | 0.9340 / 0.8977 / 0.8671 | 0.8715 / 0.8176 / 0.5898 | 0.9153 / 0.6059 | 0.0018 / 0.0055 | 0.0022 / 0.0006 |
| A | 0.40 | met | 0.2084 | kept | 0.9340 / 0.8977 / 0.8671 | 0.8715 / 0.8181 / 0.5898 | 0.9153 / 0.6053 | 0.0018 / 0.0031 | 0.0085 / 0.0006 |
| A | 0.50 | met | 0.2084 | kept | 0.9340 / 0.8982 / 0.8676 | 0.8716 / 0.8189 / 0.5909 | 0.9155 / 0.6055 | 0.0010 / 0.0010 | 0.0131 / 0.0006 |
| A | 0.60 | met | 0.2079 | kept | 0.9340 / 0.8982 / 0.8676 | 0.8717 / 0.8190 / 0.5921 | 0.9155 / 0.6066 | 0.0010 / 0.0010 | 0.0158 / 0.0006 |
| A | 0.70 | met | 0.2079 | kept | 0.9340 / 0.8984 / 0.8678 | 0.8719 / 0.8193 / 0.5923 | 0.9157 / 0.6070 | 0.0005 / 0.0004 | 0.0166 / 0.0006 |
| A | 0.80 | met | 0.2079 | kept | 0.9340 / 0.8986 / 0.8680 | 0.8721 / 0.8195 / 0.5925 | 0.9155 / 0.6072 | 0.0000 / 0.0000 | 0.0171 / 0.0006 |
| B | 0.10 | met | 0.0312 | kept | 0.9340 / 0.8973 / 0.9140 | 0.8708 / 0.8166 / 0.6977 | 0.9643 / 0.6977 | 0.0026 / 0.0090 | 0.0000 / 0.0010 |
| B | 0.20 | met | 0.0312 | kept | 0.9340 / 0.8973 / 0.9140 | 0.8708 / 0.8166 / 0.6977 | 0.9643 / 0.6977 | 0.0026 / 0.0090 | 0.0003 / 0.0010 |
| B | 0.30 | met | 0.0312 | kept | 0.9340 / 0.8976 / 0.9143 | 0.8708 / 0.8169 / 0.6977 | 0.9646 / 0.6970 | 0.0023 / 0.0078 | 0.0027 / 0.0010 |
| B | 0.40 | met | 0.0312 | kept | 0.9340 / 0.8978 / 0.9145 | 0.8711 / 0.8176 / 0.6980 | 0.9650 / 0.6963 | 0.0019 / 0.0040 | 0.0112 / 0.0010 |
| B | 0.50 | met | 0.0312 | kept | 0.9340 / 0.8983 / 0.9150 | 0.8716 / 0.8189 / 0.6993 | 0.9650 / 0.6965 | 0.0009 / 0.0010 | 0.0180 / 0.0010 |
| B | 0.60 | met | 0.0312 | kept | 0.9340 / 0.8984 / 0.9152 | 0.8717 / 0.8190 / 0.6993 | 0.9652 / 0.6965 | 0.0006 / 0.0010 | 0.0220 / 0.0010 |
| B | 0.70 | met | 0.0312 | kept | 0.9340 / 0.8984 / 0.9152 | 0.8719 / 0.8193 / 0.6995 | 0.9651 / 0.6969 | 0.0005 / 0.0004 | 0.0232 / 0.0010 |
| B | 0.80 | met | 0.0312 | kept | 0.9340 / 0.8986 / 0.9154 | 0.8721 / 0.8195 / 0.6997 | 0.9649 / 0.6971 | 0.0000 / 0.0000 | 0.0237 / 0.0010 |

At the tie-break the rows were Tiny AAM 0.9258 / 0.8644 / 0.8042 and GuitarSet 0.7997 / 0.6990 / 0.4761, `inv_rec` 0.2273.

B ends on the inversion floor at every `tau`: its `inv_rec` is 0.031 against 0.205, because the head leans root: where the DSP hears a chord-tone inversion the head does not, B writes what the head says. Its majmin_inv is higher (0.915 on Tiny AAM and 0.70 on GuitarSet, where the references are mostly in root position), which is what the floor is there to refuse. A never gates a chord-tone pick, so it keeps the DSP's inversions: its `inv_rec` is 0.208 to 0.211. A meets every constraint from 0.1 to 0.8. At 0.85 the `Bm/A` loses its `A` (and so does 0.9), which bounds `tau` from above; the diagnosed wrong picks sit at posteriors of 0.00 to 0.02, so no point in the sweep keeps them. GuitarSet's majmin_inv rises from 0.5901 at 0.1 to 0.5925 at 0.8, and 0.6, 0.7 and 0.8 are within 0.05 pp of each other on majmin_inv, `bass_ref` and Tiny AAM's majmin_inv, so they tie and the middle, 0.7, is chosen: 0.6 and 0.8 pass on both sides. Its margins are 0.3 pp of `inv_rec` over its floor and a step of 0.15 to the point where the `Bm/A` is lost.

`nonchord` falls to 0.0005 and 0.0004, the share of duration written as a non-chord bass. The datasets hold almost none to find (Tiny AAM's true non-chord bass is under 0.4 % and GuitarSet's 4.4 % is mostly its lowest string), and the held non-chord slash is guarded by the synthesized test and the chart instead: GuitarSet's per-beat recall of a non-chord reference bass is 0.021 at the tie-break and 0.028 at the shipped point (470 beats).

The shipped rows, scored by the CLI, against the tie-break's (percentage points; `root`, `N_est` and the beat columns do not move):

| | majmin | sevenths | tetrads | majmin_inv | bass_ref | inv_prec | inv_rec | nonchord |
|---|---|---|---|---|---|---|---|---|
| Tiny AAM, `model` | +0.82 | +3.41 | +3.41 | +6.36 | +6.51 | 0.00 | nan | -4.03 |
| GuitarSet, `model` | +7.22 | +12.03 | +7.77 | +11.62 | +10.35 | +0.28 | -1.94 | -16.30 |

The scores gain for the reason the tie-break's did: a non-chord bass is scored as a slash that adds a tone to the estimate's pitch set, and the head's bass is a chord tone far more often than the DSP's pick.

On the recording's model timeline the chords do not change, the beats are equal and the key stays `D:maj`; 33 beats change their bass, which takes the seconds written as `non_chord` from 26.9 to 12.0. The chart's wrong readings go to the root: `Gm/A` at 201.4 s reads `Gm`, `Bm7/G` at 204.2 s and 208.5 s read `Bm7`, `F#7/C` at 207.1 s reads `F#7` and `Bm7/D#` at 215.5 s reads `Bm7`. Kept: the `D/E` at 64.5 s and 160.5 s (their bass `E`, `non_chord`), `Bm/A` at 209.2 s and `C#7` at 212.7 s at the root. The head also takes the unverified `D/D#` at 115.3 s, `G/F#` at 146.4 s, `A/D#` at 178.8 s and `D/A#` at 285.8 s to the root, and writes `Bm/A` for the second half of two `Bm` chords (94.1 s and 260.7 s) that read `Bm/B` before.

### Current rows

The rows of the shipped bass rules (the DSP's salience test and the model's bass head, "Bass reliability" above), scored by the CLI (`chordotomy evaluate`) on the final reference. "Vocabulary v5" has the rows before v6 and what moved in v5, and "Vocabulary v6" what moved in v6 and why.

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period | bass_ref | inv_prec | inv_rec | nonchord |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `dsp` | 0.842 | 0.803 | 0.768 | 0.768 | 0.713 | 0.003 | 0.032 | 0.819 | 0.071 | 0.827 | 0.686 | 0.766 | 0.999 | 0.851 | 0.000 | nan | 0.020 |
| GuitarSet (180 takes), `dsp` | 0.722 | 0.696 | 0.583 | 0.379 | 0.446 | 0.005 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 | 0.507 | 0.174 | 0.226 | 0.087 |
| Tiny AAM (20 tracks), `model` | 0.939 | 0.934 | 0.898 | 0.898 | 0.868 | 0.015 | 0.032 | 0.966 | 0.447 | 0.827 | 0.686 | 0.766 | 0.999 | 0.916 | 0.000 | nan | 0.000 |
| GuitarSet (180 takes), `model` | 0.827 | 0.872 | 0.819 | 0.533 | 0.592 | 0.032 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 | 0.607 | 0.205 | 0.208 | 0.000 |

## Design decisions

### An analyzer, not a transcriber

Chord timelines (Chordify, Moises) and audio → score (Klangio) are already commercial products. Automatic harmonic analysis with an explanation, the "why does this progression work" part, is the gap. So chordotomy stops at chords and their function. Staff notation, melody → MIDI, and section detection are out. The first two need note-level rhythm, meaning quantization and triplets, which is the hardest and least distinctive part of the problem. Section detection is a research problem of its own. Model training is out as well: DSP and pretrained models only.

Chord extraction will sometimes be wrong, and the analysis is only as good as the chords. That's why correcting chords and entering a progression by hand are core features rather than extras.

### Key from chords, not audio

The key is estimated from the chord segments, not from the recording. Corrected or hand-entered chords then get the same analysis as extracted ones, and the estimator can be tested with plain progressions instead of synthesized audio.

### Re-analysis in the browser, Python as the reference

A corrected chord changes the key estimate, the numerals and the roles around it, and the viewer shows that at once. So the viewer runs the harmonic analysis itself, in a JavaScript port. It has to work opened from `file://`, with no build step and a CSP that allows no network, and the alternatives don't fit that. Pyodide would run the Python itself, but it is a large runtime loaded over the network and needs `wasm-unsafe-eval`. A local server would be one more thing to install and run. Saving the edits unanalyzed for the CLI to finish would not show the analysis while editing.

The port is small: key estimation, numerals and roles, inversions, and the grouping into chord runs. Python stays the reference, and a rule changes there first. The golden vectors make drift a test failure on whichever side changed: pytest fails until the vectors are regenerated from the Python, and node fails until the port agrees with them.

### Local-first

People will feed it commercial recordings. A hosted upload service would mean storing copyrighted audio, so audio never leaves the machine.

### Bass from DSP, not Demucs

The bass note comes from a low-register CQT (see Stages implemented), not from a Demucs bass stem. Demucs's code is MIT, but its pretrained weights on Hugging Face (`adefossez/HTDemucs`) carry no license statement. They were trained on MUSDB18-HQ, which is licensed for non-commercial research, plus private songs, so the terms of the output could not be stated. DSP also keeps the bass off torch, which only the optional model engine installs (see "A pretrained model as the recognizer"). The model engine, which brings torch anyway, takes lv-chordia's MIT bass head to judge the bass, and the DSP engine keeps the CQT (see "A weak non-chord bass stays at root position").

The tradeoff is lower accuracy than a separated stem when other low instruments or kick drums share the register. HPSS removes most of the kick.

### Explanations from an agent skill

The analyzer never calls an LLM. The repo is a Claude Code plugin whose `explain-harmony` skill (`skills/explain-harmony/`) runs `chordotomy analyze`, reads the JSON, and writes the explanations. The app then needs no API key, SDK dependency, or network code, and it stays deterministic and testable. The agent can also take follow-up questions. The audio stays local; only the chord timeline, as text, reaches the model. The tradeoffs: explanations are not stored in the JSON, so a viewer can't show them without a separate write-back, and getting them needs an agent.

### Whitened chroma and an N gate on tonal evidence

The first front end summed the CQT into a chroma, added a floor, and scored it by cosine against binary templates plus a flat template for `N`. On real mixes it called 12 % of Tiny AAM `N`, and 77 % of track 2720. On that track the `N` similarity had a median of 0.774 against 0.731 for the best chord.

The flat template wins because a real mix's chroma is never sparse. The flat template beats a triad whenever the chord-tone bins are under 3.0 times the others (for a `7` chord, 2.73 times), and harmonics, drums and melody keep a mix under that. Mauch & Dixon measured the same thing: without preprocessing, many chords in noisier songs become "no chord". In their Table 1, without NNLS, chord recognition is 38.6 % with no preprocessing, 74.5 % with background subtraction and 79.0 % with standardisation. So the chroma is whitened against its octave background before it is scored. This is implemented from the paper, never from their GPL plugin (see "Licenses").

`N` is a gate and a constant, not a template, because no template shape is right for it. A quiet-but-tonal beat is a chord, so `N_SCORE` is a bar the correlation has to clear, and a flat chroma correlates 0 against every chord. The gate cannot be read from the chroma, because whitening is scale-free. At first it read the level alone: a beat more than `N_GATE_DB` = 40 dB below the loud beats was `N`.

The evidence is the Tiny AAM rows in Evaluation: `N` falls from 12.3 % to 1.1 % of the duration (the reference has 1.5 %), and majmin rises from 0.738 to 0.788. GuitarSet, held out, goes from 0.519 to 0.619.

The bass evidence is a chord-tone profile because a root-only term pulled first inversions toward the chord rooted on the bass (`A:min/C` read as `C:maj`, `G:maj/B` as `B:min`), and slash chords are a product feature.

The self-loop is in seconds because a tracker locked at half or double tempo would otherwise double or halve the expected chord length. It is per beat because one transition matrix for the whole track assumes evenly spaced beats, and a grid that bends to the performance is not.

The constants trade Tiny AAM score for the test suite; see the notes under the Evaluation tables. The wider vocabulary came next, as v4 and v5 (below), and then the gate on tonal evidence. "Chord vocabulary v4" lists the qualities it left out, and v5 took three of them. Track 0080's half-tempo grid is left by design (see "One tempo per file, and a half-tempo grid doubled only against the chord changes").

Stage II replaced the level gate with one on tonal evidence. The level gate forced a quiet passage to `N`, held chords included: a Tiny AAM intro attenuated by 45 dB was 99 % `N`. And it let drums through as chords: a drum stem alone was 0 % `N` (the perturbation table under Evaluation). `N` now means no tonal content of the beat's own, a harmonic part that is noise-like or close to empty; "Stages implemented" gives the rule.

Flatness tells drums from chords. 1 of about 17,000 chord beats of Tiny AAM and GuitarSet has a flatness over `N_FLATNESS` = 0.02, against 61 % of the beats of Tiny AAM's drum stems. Flatness alone was not taken. The suite's `mix` fixture, white noise at a few dB SNR by design, measures 0.08 to 0.2, flatter than most real drums, and would lose its chords (`test_a_mix_like_clip_keeps_its_chords`). Its harmonic share, 0.47 to 0.64, is what keeps them, so the share is the second condition: 93 % of drum-stem beats are under `N_HARMONIC_SHARE` = 0.3, and the 1st percentile of Tiny AAM's chord beats is 0.42. The share alone was not taken either. GuitarSet's percussive strums dip under 0.1 on 1.7 % of beats, with zero flatness and at full level, so a loud tonal beat is never forced.

A tonal beat with harmonic energy of its own is never forced, however quiet, because a held chord has no onset on most of its beats; its harmonic evidence is what says it is a chord. A chord struck once and held from -43 to -54 dB keeps its chord on all eight of its beats (`test_a_quiet_held_chord_keeps_its_chord`). A quiet, noise-like beat with nothing struck is `N`. That condition is the onset-aware gate measured during planning, under which a -45 dB intro went from 100 % `N` to 0 to 6 %.

`N_FLATNESS` has one allowed neighbour. At 0.03 the median Tiny AAM drum stem is 0.663 `N`, under the perturbation bar of 0.70. Stepping in to 0.01 would put 0.00 one step away, which costs GuitarSet 2.6 pp of majmin, so the constant stays at 0.02, and 0.03 is bound by the drums-alone bar.

Tiny AAM's N.C. over bass and drums stays a chord. The annotation means "no chord instrument", but to chordotomy a bass line is harmony, and its bass note is a product feature. On track 0080, whose reference is 39 % `N`, the DSP calls 0.1 % of the duration `N`.

One known price: the corrected reference calls Tiny AAM's tails `N` from one beat after the last annotated beat, and a ring-out still tonal there is now a chord. It costs the DSP about 0.8 pp of Tiny AAM root and majmin. So the DSP's Tiny AAM floor for the stage was its corrected-reference row less that price ("Stage II" under Evaluation).

### One tempo per file, and a half-tempo grid doubled only against the chord changes

The beat grid keeps one tempo per file. A rule that followed a sustained tempo change was built, measured and removed. A local tempo flickers between metrical levels over an unchanged pulse, and syncopation, which is everyday in pop, switched the rule, while a tempo change inside a song is rare. "Tempo changes are not followed" under Evaluation has the measurements. The rule took its idea from Davies & Plumbley's two-state tracker, which holds the tempo in one state and finds a new one in the other; their qm-dsp code is GPL, so only the idea was used. Left: Tiny AAM's 4:3 and 3:2 metric modulations stay on one tempo.

The tracker also locks some grids at half tempo: Tiny AAM's 0080 and nine GuitarSet takes, eight of them jazz, at period ratios of 1.90 to 2.03. No cue measured during planning tells these grids from genuinely slow tracks, which have to keep theirs. Their tempo estimates, 68 to 108 BPM, overlap those of correctly tracked slow tracks, 68 to 92 BPM. The tempogram's strength at twice the estimate, over its strength at the estimate, overlaps too: 0.38 to 1.20 against 0.02 to 0.91. So does the share of decoded chord changes between their beats, 0.19 to 0.67 against 0.17 to 0.84.

So on 2026-10-01 the user chose a safeguard, not a correction. The octave check doubles a grid only in the pattern that does harm, the chord changes between its beats. The real half-locked grids sit in phase, or half in phase, with their chord changes, so they cost granularity, not chords, and the check leaves them. The rejected alternative would have doubled every grid whose tempo estimate is under 100 BPM, since a doubled grid loses no chord. It would have corrected 9 of the 10 half-locked tracks. But it would also have given a double-tempo grid to every genuinely slow track under 100 BPM: 5 of Tiny AAM's 20 tracks, about 33 of GuitarSet's 180 takes, and an 86 BPM pop recording used as a check. Their beat F and CMLt would fall and their cells in the viewer would halve, for no chord gain.

The check reads decoded chord changes, after Goto & Muraoka's inference of the metrical level from chord changes. A form that compared the chroma of a beat's two halves was measured and rejected: real music moves inside beats, so correctly tracked tracks scored up to 0.40 on Tiny AAM and 0.65 on GuitarSet, against 1.00 and 0.50 for the two synthesized half-locks. The check doubles the whole track, not a section, and it never halves: a grid at double tempo loses no chord, since the self-loop is in seconds, while halving could merge real two-beat chords.

The synthesized half-lock scores 1.00 on 35 changes (`test_a_half_tempo_lock_is_doubled`), and correctly tracked tracks score up to 0.34 on Tiny AAM and 0.71 on GuitarSet takes with 24 or more changes. With fewer changes the share is noise. "The octave check" and "Stage II" under Evaluation have the per-track shares and why the constants moved inward. Left: a half lock against one-beat chords at the true tempo, which scores 0.50, and the granularity the real half-locked grids lose.

### Chord vocabulary v4

Through v3 the qualities were `maj`, `min` and `7`. Pop harmony leans on more than that: major and minor sevenths as colour, the minor sixth on the subdominant, passing diminished and half-diminished sevenths, and suspensions. v3 had to name each of them by a triad, often the wrong one. v4 adds `maj7`, `min7`, `min6`, `hdim7`, `dim7` and `sus4`, written on a chart as Cmaj7, Cm7, Cm6, Cm7♭5, Cdim7 and Csus4.

Left out, until v5:

- `maj6`: its pitch set is `min7`'s (C6 is Am7), and an `I6` numeral would read as a first inversion.
- `sus2`: its pitch set is `sus4`'s (Csus2 is Gsus4).
- The augmented and diminished triads: rare in pop, and "dim" on a pop chart usually means the diminished seventh.
- Extensions (9, 11, 13, add9): beyond a beat-median chroma. The ninth is where the fifth's own twelfth lands.

The new qualities bring pitch-set twins: a `min6` has the notes of the `hdim7` a minor third below (Gm6 and Em7♭5 are both G–Bb–D–E), and a `dim7` the notes of three other `dim7`s. The treble can't tell twins apart; only the bass profile, which favours the root, can. So `min6` and `hdim7` share one offset, and the bass, not the offset, decides between them. Without a bass on one of their roots they tie, and label order picks one, which is arbitrary. A musician spells a diminished chord by where it leads, its root a half step below the next chord's root, so the analyzer respells twins that way after segmentation (see Stages implemented). For a `dim7` the bass can't settle the root at all: the chord is symmetric, so its bass is its inversion. An `hdim7` is never respelled, because it only wins over its `min6` twin on bass evidence; a tie goes to the `min6`.

Tetrads and `sus4` pay an offset because without one, extended chords win by default. A triad's own partials land on tetrad tones: the third's twelfth on the seventh (E → B under C, C → G under A:min), the fifth's twelfth on the ninth. Whitening lifts a lone partial in a sparse region, so a played triad shows a trace of its seventh, and a tetrad's template, the triad plus one tone, collects it. Templates with partials (below) take some of that back; the offsets take the rest. Played chords clear their triads by different margins, so each group has its own offset. The `7` needs none to hold Tiny AAM's floors. `sus4` has the largest: Tiny AAM, annotated in major and minor only, scores every sus4 call as a majmin miss, and a played sus4 clears its triad by more than a played seventh does.

Templates carry partials. Through v3 they were binary: 1 on each chord tone, 0 elsewhere. Now each tone also has its octave, twelfth and double octave, weighted by `PARTIAL_DECAY`, so a template expects a triad's own partials and stops reading them as a tetrad. In the planning sweep, at a decay of 0.6 and the same offsets, partials gained 2 to 3 pp of root, majmin and sevenths on GuitarSet and moved Tiny AAM by up to 0.5 pp either way. The bass profiles and `inversion` keep the binary chord tones: they ask which tone the bass is, not what it sounds like.

NNLS note profiles (Mauch & Dixon 2010, from the paper, not the GPL plugin) were tried during planning and rejected. Each frame of the whitened spectrum was decomposed into 84 note profiles with partials by non-negative least squares, then folded through the same pitch windows. On Tiny AAM that cost 2 pp of majmin at every offset tried; on GuitarSet it gained 2 pp. This stage's bar was to lift sevenths without costing majmin, so no code implements it.

### Chord vocabulary v5

v5 adds `aug` (0, 4, 8), `dim` (0, 3, 6) and `sus2` (0, 2, 7), written on a chart as Caug, Cdim and Csus2.

Why: the lv-chordia model emits all three, and until v5 the model engine approximated each. `aug` became `maj` and kept the root but lost the raised fifth. `dim` became `dim7`, which added a diminished seventh nobody heard, so a diatonic `vii°` in major read as a borrowed `vii°7`. `sus2` became the `sus4` a fifth up, the same pitch set under another root. With the three exact, the numerals say what a chart says: the passing `vii°` and the leading-tone `vii°/ii`, harmonic minor's `III+` and `#vii°`, and the `Vsus2` colour. On the evaluation datasets the exact mapping moved little, because the model hardly emits them (`dim` on 0.03 % of Tiny AAM and 0.69 % of GuitarSet, `aug` and `sus2` on neither); two GuitarSet takes gained 6 pp of root, because a `dim` keeps the model's root where a `dim7` could be respelled as another root of its set ("Vocabulary v5" under Evaluation).

Left out, and why. `maj6` stays out: its pitch set is `min7`'s, `I6` reads as a first-inversion figure, and the model never emits it. `add9` and the 9, 11 and 13 stay out: they are beyond a beat-median chroma, the ninth being where the fifth's own twelfth lands, a false-positive risk for the DSP, and the model maps them to sevenths.

Twins. `C:aug`, `E:aug` and `G#:aug` are one pitch set. The bass profile roots the decode on the bass, and a tie goes to the earliest root, as for `dim7`. `resolve_twins` then respells an `aug` run as the twin rooted a fifth above the next chord's root when one exists and no segment of the run has a heard bass on the decoded root, which is the `min6` shape: a heard bass on the root is evidence for that reading, and label order says nothing. The one strong convention for an augmented triad is the dominant resolution, `V+` to `I`; before a chord with no such twin, before `N` or at the end the decode stays. The diminished triad is not a twin of anything: it is a subset of `dim7` and `hdim7`, so it has its own template, and it is never respelled. `C:sus2` is `G:sus4`'s pitch set, but the pair is a twin in the vocabulary only: the DSP never calls `sus2`, so it has nothing to decide, and `resolve_twins` leaves a `sus2` from the model alone, since a suspension resolves on its own root and the next chord's root is no evidence for it.

The offsets. `aug` is -0.25 and `dim` -0.10, `sus2` is minus infinity, and "Tuning the v5 offsets" under Evaluation has the sweep. The DSP's `sus2` fails on the synthesized suite: a played Csus2 needs the pair at -0.175 or higher, a triad with an added ninth needs it at -0.275 or lower, and sus2 calls cost Tiny AAM 1.0 pp of majmin at -0.25. `aug` and `dim` pay a stated price instead: against never calling them, at most 0.24 pp on any column, because the synthesized suite needs both called (`dim` at -0.15 or higher for the `vii°` case, `aug` at -0.30 or higher for a bass-less `V+`).

The false-positive guard. Tiny AAM is annotated in major and minor only, so every `aug`, `dim` or `sus2` call there is a miss. The floors were taken from a diagnostic point where the new qualities never win, Tiny AAM's root and majmin must stay at or above the stage II rows, and the new qualities may take under 1 % of Tiny AAM (the shipped point takes 0.32 % for `dim` and none for `aug`).

The harmony. `aug` is uppercase with `+` and `dim` is lowercase with `°` and takes the raised-root spelling of `dim7` (`#i°`, never `bii°`). `aug` is never a secondary dominant: the chord is symmetric, so a `V+/x` by the fifth relation would follow an arbitrary spelling, and the tonic's `V+` is chromatic. Harmonic minor admits `III+` and `#vii°` beside V, V7 and `#vii°7`. The borrowed rule learned sevenths in the same stage: a tetrad is borrowed when its triad is diatonic in the parallel mode and its seventh lies in either mode's scale, so `A#:maj7` in C major is a borrowed `bVIImaj7` instead of chromatic. The viewer and the schema moved together: schema 7, and the viewer names, spells, plays and offers the three qualities in the commit that grew the label set, so no version of it accepts a label it cannot render.

### Chord vocabulary v6

v6 adds `sus4(b7)` (0, 5, 7, 10), the dominant seventh suspended fourth, written on a chart as C7sus4.

Why: the user's J-pop recording writes the dominant before the tonic as IIm7 over V, Em7/A in D major, an A9sus4 voicing of the suspended dominant that the vocabulary reduces to `A:sus4(b7)`. lv-chordia's raw output there is `A:sus4(b7)`, 11.8 s of its frames, which v5 folded to `sus4`, so the timeline's 17 beats there (11.9 s) read `Asus4`, a chord without the seventh that gives the sound its name. The 7sus4 is a staple of J-pop and gospel, and a chart writes it often. On the datasets it is rare, 0.07 % of GuitarSet's performed annotations and none of Tiny AAM's, and the model emitted none, so the rows did not move ("Vocabulary v6" under Evaluation).

The label. The quality string is Harte's, `A:sus4(b7)`, because the JSON states Harte syntax and `evaluate` hands labels to mir_eval, which parses it and its slash forms (`A:sus4(b7)/b7` is bass 10) and would reject an ad-hoc `7sus4`. It is appended after `sus2`, so every existing label index and tie-break holds. The parentheses touched two regular expressions in the viewer, and nothing in Python: every Python parse splits on `:` or `/`. `CHORD_LABEL` in `core.js` joins the quality names into a RegExp, where a bare `sus4(b7)` is `sus4` followed by a capturing group and would accept `A:sus4b7` and refuse `A:sus4(b7)`, so the names are escaped before joining. And `numeralParts` needed `7sus4` ahead of `7` in its suffix alternation, or `7` alone would match and leave `sus4` unmatched. Viewer tests pin both.

The numeral and the inversion. The suffix is `7sus4`, uppercase, with no figured bass, like `sus4` and `sus2`. By position in (0, 5, 7, 10), `first` is the fourth, `second` the fifth and `third` the seventh. It is diatonic by the scale test alone, so the sets above hold. `TRIAD` maps it to `sus4` to keep the table complete for every tetrad; for this quality the parallel-mode test already covers every borrowed case (a `7sus4` whose `sus4` lies in the parallel mode has its seventh there too), so the entry reclassifies nothing, which a comparison of every chord in C major and A minor against v5's golden vectors confirmed. A `7sus4` is never a secondary dominant: it has no third, so no leading tone, and the suspension is the point. `_tonic_triad` is unchanged. It folds `maj7` and `min7` onto the tonic triad that names a key in the tie-breaks, and a suspended chord has no third, so it cannot name a key's mode. (A 7sus4 does take tonic function on I, III and VI where the diatonic sets put it, but that is the degree's function, not a key's name.)

The model engine maps `sus4(b7)` to `sus4(b7)`. `11` keeps mapping to `7`, since Harte's 11 includes the third.

The DSP does not call it. The offset was swept alone, as v5's were, against floors taken from the never-called point, with the synthesized suite as the hard constraint. The V7sus4 cadence needs -0.23 or higher, and the floors allow -0.2375 or lower ("Tuning the v6 offset" under Evaluation): the interval is empty, by 0.0075, and -0.23 would also fail v5's margin rule, a one-step neighbour failing the suite and the other the floors. So `sus4(b7)` is minus infinity, as `sus2` is. The caches were rebuilt at the 157-label set before the sweep, because the octave check decodes the doubled grid with the vocabulary and the offsets; no track's grid moved. Only the model engine or an edit writes the 7sus4, Em7/A included.

### A pretrained model as the recognizer

Until this stage the chords came from DSP alone. Pretrained models were never ruled out (see "An analyzer, not a transcriber"), but the one weighed before, Demucs for the bass, was turned down for its weights' terms, which could not be stated, and for torch's size (see "Bass from DSP, not Demucs"). lv-chordia answers both. Its weights are MIT: the authors committed them to the same MIT repository as the code, and the lv-chordia wheel ships them, so nothing is downloaded at run time. torch comes only with the optional `model` extra, so the default install, `chordotomy --version` and the DSP engine never import it or lv_chordia. What moved the stance was a local comparison on the two evaluation datasets, where the model scored above the DSP on every metric (see "Model engine" under Evaluation). On 2026-10-01 the user decided that the model is the default when it is installed.

The training data, stated plainly: lv-chordia's authors trained the nets on 1217 songs from Isophonics, Billboard, RWC-Pop and USPOP, public chord annotations over commercial recordings. Nothing is trained here. The user accepted weights trained that way. The README states the training data, so that anyone who would rather not can leave the extra out and keep the DSP.

The model replaces the chord recognizer only. The rest stays DSP:

- The beats. The model labels frames, while the timeline, the bass and the viewer's edits are on beats, so its labels are snapped to the DSP's.
- The bass. Superseded. The engine first kept the DSP's `pick_bass` even outside the model's chord, because in band music such a bass is often real; on the evaluation datasets it only cost (see "Model engine" under Evaluation), and the model's own bass is off the root on under 3 % of their duration, closer to a root-position prior than a heard bass. Now lv-chordia's bass head judges the bass, with the DSP's pick as its first candidate: model majmin_inv went from 0.804 to 0.868 on Tiny AAM and from 0.476 to 0.592 on GuitarSet ("Bass reliability" under Evaluation).
- The `N` gate, for the DSP engine only. Whitening is scale-free, so the DSP needs the gate's evidence to keep silence and drums `N`; the model decodes its own `N`.
- The twin respelling and the harmony. They read chord labels, not audio, so they treat both engines' chords, and the viewer's edits, alike (see "Key from chords, not audio").

Importing any lv_chordia submodule runs its `__init__`, which imports `chord_recognition`, `audio_utils` and `mir`, and with them pydub and the package's cache module. The package also has a URL download, a disk cache, and a path that runs Chordino through an external sonic-annotator (Vamp). The engine never calls any of them and never imports the Vamp extractor. It passes the nets the signal it already decoded, so the audio stays local.

Inference is pinned to the CPU. The package moves the nets to CUDA whenever torch has it; the engine clears that choice before it loads them. A run then has one runtime and memory profile, the one measured under Evaluation, on the one path the tests exercise. Needing no CUDA, the Linux install takes torch from the PyTorch CPU index, where PyPI's Linux wheel would pull in CUDA. And the model engine takes about twice the DSP's time per audio minute, so a GPU would have little to win.

The heads are softmaxes, but nothing calibrated them, so the scores folded from them only rank the labels. They are not written out, and the candidates stay a ranking (see "Confidence is a rank, not a percentage").

The dictionary has no `maj6`, `add9` or `min6`, so the model never emits them, and they stay out of the vocabulary ("Chord vocabulary v5"). It does have `aug`, `dim` and `sus2`, which the engine first approximated with `maj`, `dim7` and the `sus4` a fifth up; v5 took all three as they are. It also has `sus4(b7)`, which v5 folded to `sus4`; v6 takes it as it is.

### A weak non-chord bass stays at root position

A bass outside the chord, written as a slash chord, is a claim that the music has that inversion or that non-chord bass. Both engines made it too easily. The evidence is a locally analyzed J-pop recording checked against a chart: every verse and chorus slash was right, and 4 of the 5 non-chord slashes in the bridge were wrong, all on two-beat chords. On the DSP the pick was a weaker, lower note at 0.53 to 0.74 of the register's loudest under a louder root, and some wrong picks were the loudest too. The model's bass head matched the chart on every verified case, and its posterior on the wrong DSP picks was 0.00 to 0.02. One miss is shared and left: the `C#7/E#` the chart has, which both engines read as `C#7` (the head says `C#` at 0.95).

The rule, in both engines: a per-beat bass that is a tone of the beat's chord is written as heard; one outside the chord is written as heard only if the engine's test passes, and otherwise the beat reads the chord's root, before the hold and the vote, so the segment reads root position. It is root position and not `null` because `null` says no bass was heard, which drops the inversion and breaks a bass line for the `explain-harmony` skill, while a chord at root position claims nothing the music may not have. The root is written although it is not measured: a `bass` that equals the chord's root may be that fallback and not a note heard, and the JSON row says so.

The tie-break ships with it, in both engines: a segment with no held value votes its per-beat basses by count, then by being a tone of the segment's chord, then by being a note, then by the earliest beat. That alone fixed the two-beat chords whose passing note on beat 1 was written as a slash.

The DSP's test is salience: `NONCHORD_SALIENCE` = 1.0, so a non-chord pick must be the register's loudest note. The sweep ("The DSP's salience test") met the floors at every point, and 1.0 is the top of the range: above it the loudest pick fails too, a held non-chord slash is never written, and two synthesized tests fail. The held `D/E` sits at 1.0 and bounds it from above; the chart's rejected picks, at 0.53 to 0.74, bound it from below. The DSP's majmin_inv went from 0.697 to 0.713 on Tiny AAM and from 0.407 to 0.446 on GuitarSet, and the share of duration written as a non-chord bass from 3.4 % to 2.0 % and from 15.3 % to 8.7 %. The DSP engine's picks outside the chord are still wrong in some places; the test removes the weak ones only.

The model's test is the bass head, with one precedence: per chord beat the DSP's plain pick first and then the head's note (variant A); the first chord tone wins, ungated; else the first non-chord candidate with a posterior of at least `BASS_SUPPORT` = 0.7; else the root; `null` only when there was no candidate. Variant B, the head's note alone, scored higher on majmin_inv but wrote almost no inversions (GuitarSet `inv_rec` 0.031 against 0.208), because the head leans root; the ship rule floors `inv_rec` for that reason, and A passed. 0.7 is the middle of the plateau from 0.6 to 0.8. The model engine's majmin_inv went from 0.804 to 0.868 on Tiny AAM and from 0.476 to 0.592 on GuitarSet. The two engines therefore differ in their bass values, and so in where they cut segments, although they share the cut rule.

What the datasets can and cannot see: Tiny AAM's true non-chord bass is under 0.4 % of its duration and GuitarSet's 4.4 % is mostly its lowest string, not a slash a chart would write. So the scores reward the rule mostly for removing false slashes, inversion recall is floored (GuitarSet `inv_rec` 0.226 on the DSP, 0.208 on the model, against the tie-break's 0.231 and 0.227), and a held non-chord slash is guarded by the synthesized tests and the chart, not by the datasets.

A corner of `resolve_twins`: a `min6` or `aug` run with a heard bass on its decoded root is left as spelled, but a fallback root was not heard and decides nothing, so such a run is respelled by where it leads like a bass-less one. A respelled segment whose bass was inferred takes the new chord's root as its bass, so it reads root position and not a slash on the old root (`F#:hdim7`, not `F#:hdim7/A`). A heard bass is kept. The model never calls `min6` and emitted no `aug` on the datasets, so this is the DSP's corner.

Left out: reconciling the chord with the bass (`Bm/A` could be a `D/A`, which is a chord decision), the missed `C#7/E#`, and source separation, since no separator has weights with stated terms.

### Confidence is a rank, not a percentage

Template similarity is not a probability. Showing "GM7 81%" would claim precision the method doesn't have. Candidates are shown as a ranked list. Percentages appear only if a calibrated model produces them. lv-chordia's probabilities are not calibrated either, so the model engine's candidates are a ranking too.

### Licenses

The project is MIT, so it takes no GPL or AGPL dependencies. That rules out Essentia (AGPL-3.0) and Chordino / NNLS Chroma (GPL); their ideas get reimplemented on librosa instead. librosa (ISC) and music21 (BSD-3) are fine. Demucs's code is MIT, but its pretrained weights are a separate question; see "Bass from DSP, not Demucs". Pretrained weights can carry terms separate from their code, such as non-commercial model files, so check both.

The `model` extra was checked from the installed packages' metadata. lv-chordia's code is MIT ("Copyright (c) 2023 Music X Lab", the LICENSE in the wheel). Its weights are MIT as well: the authors committed them to the same repository, and the wheel redistributes them. Their training data is a separate question from their license; see "A pretrained model as the recognizer". torch is permissive, with the License-Expression `Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT`. The extra also brings audioop-lts (PSF-2.0) on Python 3.13 and later, h5py (BSD-3), pydub (MIT), and pretty-midi and mido (MIT). Nothing in the extra is GPL or AGPL. soxr (LGPL-2.1-or-later) is in the environment as librosa's dependency, not a new one. The package's Chordino path is never called.

### Synthesized test fixtures

Tests build audio in code, for example additive tones for known chords at a known tempo. The fixtures are license-free, and the ground truth is exact.
