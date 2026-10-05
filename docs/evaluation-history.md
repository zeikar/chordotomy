# Evaluation history

Each block of rows below records the analyzer at the commit that added it, oldest first; the current rows are in ["Current rows"](evaluation.md#current-rows). [Evaluation](evaluation.md) has the method, the datasets and what each metric means.

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

GuitarSet's sevenths rise from 0.492 to 0.531, its majmin from 0.619 to 0.661 and its tetrads from 0.317 to 0.347, while Tiny AAM, annotated in major and minor only, gives up 0.9 pp of root and 1.2 pp of sevenths and calls a quality new in v4 on 3.7 % of its duration. The tuning signal was a sweep over cached features scored on the labels alone, without the bass. Those scores sit above these rows, because the CLI's scores also pay for basses outside the chord, as noted in [Evaluation](evaluation.md) for slash chords. At stage 1 the gap was up to 2.2 pp on Tiny AAM and 7.4 pp on GuitarSet, and the sweep raised each floor below by it. Under v4 it is larger, 2.5 pp of Tiny AAM sevenths and 9.0 pp of GuitarSet sevenths, and the sweep also checked every floor on the CLI's own scoring, reproduced from the cache.

## Tuning the v4 constants

The quality offsets, `TEMPERATURE`, `CHORD_SECONDS`, `BASS_WEIGHT`, `BASS_TONE` and `PARTIAL_DECAY` were tuned together by coordinate descent on the planned grid, the offsets and then the decode constants in turn until the point stopped moving. The objective is the highest GuitarSet sevenths over all 180 takes, whose two halves differ a lot. Tiny AAM is the false-positive guard: annotated in major and minor only, it scores a sus4 call as a majmin miss and a tetrad call as a sevenths miss. Its floors (root ≥ 0.835, majmin ≥ 0.775, sevenths ≥ 0.730, `N_est` within 0.02 of `N_ref`) bound how much of the vocabulary the decoder may use; GuitarSet has to keep majmin ≥ 0.60 and sevenths ≥ 0.512. The synthesized suite was a hard constraint on every point, the suspension test included: the offsets the datasets alone prefer, `sus4` at -0.3 or -0.4, smooth its four-beat `G:sus4` into the `G:maj` after it.

Each constant was then moved one grid step either way, and margin on the suite came first, because stage 1's point was one step from breaking an inversion test. At the descent's point, with `PARTIAL_DECAY` 0.6, one step of `TEMPERATURE` up, `BASS_WEIGHT` up, `BASS_TONE` down or `PARTIAL_DECAY` down smoothed away the two-beat `A:min/C` inside `C:maj`, the stage-1 binding case. Moving `PARTIAL_DECAY` to 0.8 was a cost: 0.3 pp of label-only GuitarSet sevenths, and Tiny AAM's root, majmin and sevenths from 0.844, 0.799 and 0.754 to 0.839, 0.793 and 0.748. It is what keeps the suite green at every one-step neighbour. `7`, `maj7`/`min7`, `min6`/`hdim7`, `dim7` and `CHORD_SECONDS` also hold every floor at both neighbours. Elsewhere Tiny AAM's root floor binds, cleared by 0.4 pp: one step of `sus4` up, `TEMPERATURE` down, `BASS_WEIGHT` down, `BASS_TONE` up or `PARTIAL_DECAY` up takes it to between 0.822 and 0.834. `sus4` is pinned from both sides, since at -0.3 the suspension test fails.

The chosen point is therefore not the objective's best. One step outside the grid, three neighbours score higher with the suite green and every floor held (GuitarSet sevenths on the CLI): `TEMPERATURE` 0.035 (0.534) and `BASS_TONE` 0.6 (0.532) were not taken because each uses up the `A:min/C` case's margin, which fails at `TEMPERATURE` 0.040 and with both moves together. `maj7`/`min7` at -0.05 (0.540) was not taken because it calls more sevenths on major and minor material: Tiny AAM sevenths falls to 0.744, and at the next step, 0, to 0.715, under its floor.

## Model engine

`chordotomy evaluate <dataset> --engine model` scores the lv-chordia engine, the default when the `model` extra is installed. The rows above are the DSP's, `--engine dsp`, which reproduced the v4 Tiny AAM row when the model engine was added.

Model engine, lv-chordia 1.1.0 on the DSP beat grid with the DSP bass, at the commit that adds these rows:

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref |
|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks) | 0.927 | 0.913 | 0.845 | 0.845 | 0.788 | 0.015 | 0.015 |
| Tiny AAM, labels only | 0.927 | 0.922 | 0.887 | 0.887 | — | 0.015 | 0.015 |
| GuitarSet (180 takes) | 0.827 | 0.787 | 0.676 | 0.441 | 0.466 | 0.032 | 0.000 |
| GuitarSet, labels only | 0.827 | 0.872 | 0.819 | 0.533 | — | 0.032 | 0.000 |

The rows were accepted against the planning spike's labels over the DSP's bass: lv-chordia's own labels, mapped to v4, snapped to the DSP's beats by the label covering most of each beat, and scored with the bass this engine writes. Those score 0.926, 0.912, 0.842 and 0.842 on Tiny AAM (root, majmin, sevenths, tetrads) and 0.827, 0.787, 0.676 and 0.440 on GuitarSet, and the CLI rows match them within 0.003. The labels-only rows score the same timelines without the bass. They match the spike's beat-snapped labels alone, 0.926, 0.922, 0.886 and 0.886 and 0.827, 0.872, 0.819 and 0.533, within 0.001, so the beat majority and the label mapping reproduce the spike's.

The CLI rows sit below the labels-only rows because of the bass. A DSP bass outside the model's chord becomes a slash degree, which mir_eval adds to the pitch set (see the slash-chord note in [Evaluation](evaluation.md)), on 5.0 % of Tiny AAM's duration and 19.4 % of GuitarSet's. The engine keeps it, because in band recordings such a bass is often real, a pedal point or a descending line, while on these two datasets it only costs: Tiny AAM's references carry no bass, and GuitarSet's solo guitar defeats `pick_bass`. Dropping those basses, which is not shipped, would give the labels-only majmin, sevenths and tetrads and a `majmin_inv` of 0.831 and 0.578.

`majmin_inv` here is the DSP's bass under the model's chords: 0.788 and 0.466, against the DSP engine's 0.690 and 0.395. The spike's `majmin_inv` with the model's own bass, 0.903 and 0.701, is not comparable. That bass is off the root on under 3 % of the duration, and the references are mostly in root position, on Tiny AAM all of them by assumption. A root-position prior scores well there without hearing a bass.

These rows are history. The engine's bass has since come from the bass head, and "Bass reliability" below has the rows that replace them.

The nets run in windows of at most `CHUNK_SECONDS` = 60 s. Tiny AAM's tracks are 123 to 181 s long, so each is split into three or four windows. On the whole track instead, Tiny AAM scores 0.926, 0.912, 0.843, 0.843, 0.786, 0.015 and 0.015, against the windows' 0.927, 0.913, 0.845, 0.845, 0.788, 0.015 and 0.015. The window would have gone up to 120 s had root, majmin or sevenths moved by more than 0.5 pp. They moved by 0.1 to 0.2 pp, so 60 s ships. GuitarSet's takes are 14 to 46 s, one window each.

Runtime and memory of `chordotomy analyze` on synthesized 3- and 6-minute mixes, on an Apple M4 (10 cores, torch 2.14.1). Time is wall time per audio minute, start-up included, the mean of two runs; memory is the peak resident set size. The whole-track rows set `CHUNK_SECONDS` above the clip's length.

| | 3 min: s per audio minute | 3 min: peak RSS | 6 min: s per audio minute | 6 min: peak RSS |
|---|---|---|---|---|
| `dsp` | 3.3 | 1.00 GB | 3.1 | 1.77 GB |
| model, 60 s windows (shipped) | 6.8 | 2.36 GB | 6.3 | 3.17 GB |
| model, whole track | 6.2 | 3.73 GB | 5.7 | 6.98 GB |

Importing torch and lv-chordia and loading the five nets takes 1.3 s and 0.28 GB, once per run; the model rows include it. The nets run on the CPU by construction, whatever torch is installed, so this is the only profile. Memory grows with length mostly through `beat_features`, by 0.26 to 0.27 GB per audio minute in both engines. The windows hold the nets' own share of the peak at 1.1 GB at both lengths, where the whole track took 2.5 GB at 3 minutes and 5.0 GB at 6. They make the run about 10 % slower than on the whole track. The model engine's runtime with Beat This!'s beats is under "Beat tracking" below.

## Corrected Tiny AAM reference

Corrected Tiny AAM reference, before the stage-II analyzer changes, at the commit that adds these rows. Both engines snap to the DSP's beat grid here (until the Beat This! stage, "Beat tracking" below), so their beat columns are equal. GuitarSet's reference has no `N`, so its `N_rec` is `nan`.

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

## The octave check

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

## Stage II

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

## Tempo changes are not followed

The tracker keeps one tempo per file. Two rules that followed a tempo change inside a file were built and measured, and both are out. The hybrid: the tempogram's local tempo, median-filtered over 10 s, replaced the global tempo when it stayed more than 10 % off it, folded to the octave, for 16 s. It switched 9 Tiny AAM tracks and raised Tiny AAM's CMLt from 0.686 to 0.785, +9.9 pp. It also switched four of GuitarSet's 180 constant-tempo takes and an 86 BPM pop recording whose local tempo flickers between metrical levels (86, 112, 129 and 172 BPM): the median departs without any change, and following it gave the recording 668 beats of 0.30 to 0.88 s for the global tracker's 437 of 0.60 to 0.74 s. A gate that also required the departure to read one tempo (at least 0.75 of its unsmoothed frames within 10 % of its median) stopped all five and raised CMLt to 0.813, +12.7 pp, but a syncopated figure held over an unchanged pulse reads one tempo too. Synthesized at 74 to 105 BPM, 22 s of hats in 3-3-2 sixteenths or in quarter-note triplets after 22 s on the eighths switched 39 of 40 clips under both rules, hats at a tenth of the kick's level included. Seven of GuitarSet's 30 s takes already hold one steady off-tempo reading for 10 to 15.6 s, and with the gate, one step of the hybrid's window, departure or hold switched takes or the pop recording again. Tiny AAM's tempo changes are 4:3 and 3:2 metric modulations, the ratios syncopation reads, and nothing measured told them apart: not the tempogram's support for the global period inside the departure, not the global grid's onset strength there, and not a curve read from the harmonic part instead. Syncopation is everyday in pop and a tempo change inside a song is rare, so the beat grid stays on the pulse. `test_a_syncopated_constant_tempo_keeps_the_global_grid` holds it there.

The model engine's grid keeps one tempo too, and the price was measured again on it ("Beat tracking" below). Three ways of reading Beat This!'s output follow a tempo change: its own peak picking, madmom's DBN (a dynamic Bayesian network, madmom's beat decoder), and librosa's DP with its tempo following Beat This!'s beat spacing. On Tiny AAM they reach a beat F of 0.946, 0.933 and 0.936 against the one-tempo DP's 0.896, and all three a snapped majmin of 0.953 against 0.950. So Tiny AAM keeps one tempo per file at a price: the readings that follow tempo gain about 0.3 pp of its snapped majmin and 4 to 5 pp of its beat F. The DBN and the tempo-following DP switch on the syncopated fixture as the hybrid did: in its quarter-note triplet bars both move to a 0.465 s pulse, two-thirds of the true 0.698 s, and the fixture's largest gap becomes 1.63 times its smallest, where the test allows 1.2 and the one-tempo DP keeps 1.07. The test's copy in `test_beats_engine.py` holds the model engine's grid there.

## Vocabulary v5

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

### Tuning the v5 offsets

The 145-state transition costs nothing and gains a little. With `aug`, `dim` and `sus2` at -1, so that they never win and the only change is that the Viterbi's switch probability now spreads over 144 other states instead of 108, Tiny AAM's root and majmin rise from 0.83937 and 0.79478 to 0.84094 and 0.79683 (+0.16 and +0.20 pp), its sevenths stay at 0.750, and GuitarSet's majmin and sevenths are 0.66298 and 0.53029 against 0.662 and 0.531. That diagnostic point is what the new qualities are priced against. It is never a candidate, since it calls no new quality at all.

The DSP does not call `sus2`. `C:sus2` is `G:sus4`'s pitch set, and two synthesized cases pull its offset apart. A played Csus2 between C chords must be told from the triad: `C:sus2` clears `C:maj` by 0.285 less the offset on its beats, so the pair must stay at -0.175 or higher. A C triad with an added D, first an octave above it and then inside the voicing (an added ninth), must stay `C:maj`, and `C:sus2` clears `C:maj` by 0.30 there, more than it does on the played chord, so the pair must be -0.275 or lower. The existing four-beat `G:sus4` into `G:maj` needs -0.25 or higher. No shared value passes all three, nor does any one-step move of the decode constants. The datasets agree: at -0.25 `sus2` labels 1.5 % of Tiny AAM and costs 1.0 pp of its majmin (0.78686 against 0.79683), and holding Tiny AAM's floors takes -0.30. `sus2` stays in the vocabulary, the harmony and the viewer, and comes from the model engine or a manual edit; its offset is -inf, which `smooth` reads as a label that is never chosen and `segment` ranks last, so never a candidate. `sus4` stays at -0.25.

`aug` and `dim` were swept on a 0.05 grid from 0 to -0.6, every other variable at its v4 value, against floors taken from the diagnostic point: Tiny AAM root 0.84094, majmin 0.79683, sevenths within 0.5 pp of 0.75020, `N_est` unchanged and the new qualities' share at most 1 %; GuitarSet majmin 0.66298 and sevenths 0.53029. The objective was GuitarSet sevenths, then tetrads. The points that hold the floors are all the same point: `aug` and `dim` so low that neither is ever called, which scores exactly the diagnostic row. The synthesized suite does not allow it. The `vii°` case needs `dim` at -0.15 or higher, and the floors need -0.225 or lower. The bass-less `V+` case needs `aug` at -0.30 or higher, a bound the floors do not touch: from -0.20 to -0.30 `aug` scores the same on both datasets, so it sits at -0.25, the middle of that plateau.

So `aug` and `dim` are called, at a stated price: any floor may give at most 0.3 pp against the diagnostic point, Tiny AAM's root and majmin stay at or above the end of stage II's values (0.83937 and 0.79478), and the new qualities stay under 1 % of Tiny AAM. At the chosen point, against the diagnostic point:

| | root | majmin | sevenths | tetrads |
|---|---|---|---|---|
| Tiny AAM | +0.07 pp | -0.05 pp | -0.01 pp | -0.01 pp |
| GuitarSet | -0.07 pp | -0.24 pp | -0.12 pp | -0.24 pp |

The 0.3 pp is the same price v4 paid for `PARTIAL_DECAY`. `dim` was chosen between -0.10 and -0.15 by suite margin, v4's rule. Each variable was moved one step either way, down being more negative or a smaller constant, with the suite and the floors checked at each. At `dim` -0.10, three neighbours fail the suite: `sus4` at -0.30 (the suspension test, as in v4), and `dim` at -0.05 and `dim7` at -0.15, each failing the same three `dim7` tests, because a played diminished seventh stays a `dim7` only while `dim` is not above it. At `dim` -0.15 four neighbours fail: `sus4` at -0.30, `dim` at -0.20 and `PARTIAL_DECAY` 0.9 (the `vii°` case), and `7` at +0.05 (the `vii°` case), so -0.10 is the point. `aug` at -0.20 and -0.30 keep the suite green and score the same. Elsewhere the floors bind, as in v4: one step of `sus4` up (-0.20), `TEMPERATURE` down (0.025) or `BASS_TONE` up (0.8) takes Tiny AAM's root and majmin to 0.8356 and 0.7882, 0.8360 and 0.7880, and 0.8307 and 0.7861, and `7` at +0.05 takes its majmin and sevenths to 0.7886 and 0.7403. `BASS_WEIGHT` 0.25 leaves Tiny AAM's majmin at 0.79476 against 0.79478, at its bar. On GuitarSet, `BASS_WEIGHT` 0.35, `min6`/`hdim7` at -0.05 and `PARTIAL_DECAY` 0.7 take majmin to 0.6569, 0.6564 and 0.6582, and `7` at -0.05 takes sevenths to 0.5242.

## Vocabulary v6

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

### Tuning the v6 offset

The caches were rebuilt at the 157-label set before any point was scored, because the octave check ("The octave check") decodes the doubled grid with the vocabulary and the offsets, so v5's caches hold grids from a decoder that no longer exists. The direct comparison found every track's `times` equal to v5's, on all 200 tracks. Each swept point was scored on the grid it produces: the octave decision was recomputed per track from the cached inputs at that offset, and no track flipped at any point from 0 to -0.6, so no track was rebuilt. The highest share among tracks with at least 24 decoded changes at any swept point was 0.65 on Tiny AAM (track 1050) and 0.72 on GuitarSet (02_SS2-107-Ab_comp), against 0.80; at the committed point they are 0.60 and 0.68.

The diagnostic point, `sus4(b7)` never called, is the committed one, and the floors are taken from it. The 157-state transition (a switch costs 0.08 nats more) moves v5's shipped rows by +0.00 pp on Tiny AAM's root and majmin and +0.01 pp on its sevenths (0.75005 to 0.75020), and on GuitarSet's majmin, sevenths and tetrads by +0.04, +0.04 and +0.01 pp (0.66055, 0.52905 and 0.34458 to 0.66096, 0.52941 and 0.34467). The floors: Tiny AAM root and majmin at most 0.3 pp under it and at or above v5's 0.84161 and 0.79635, which are the diagnostic values to five digits; sevenths within 0.5 pp; `N_est` unchanged; `sus4(b7)` at most 1 % of its duration; GuitarSet majmin and sevenths at most 0.3 pp under it.

`sus4(b7)` was swept alone on a 0.05 grid from 0 to -0.6, refined to steps as small as 0.0025 where a bound fell between points. Three synthesized cases bound it, and no shared value passes them and the floors:

- A played V7sus4 in the D major cadence (A3 D4 E4 G4 over an A2 bass, then the dominant seventh) needs -0.23 or higher: the suite is green at -0.23 and the cadence case fails at -0.2325.
- A plain Asus4 into A and the existing G:sus4 and added-ninth cases need -0.0875 or lower: the suite is green at -0.0875, the G:sus4 suspension and the added ninth fail at -0.075, and the plain Asus4 fails too at -0.0625.
- The floors need -0.2375 or lower. Above it Tiny AAM's root or majmin is under v5's, by 0.03 pp of root at -0.22 to -0.23 (0.84132), 0.06 pp of majmin at -0.20 (0.79572), and 0.33 pp of majmin at -0.15, where `sus4(b7)` also covers 1.5 % of Tiny AAM, over the 1 % bar. At -0.10 the loss is 0.35 pp of root, 0.91 pp of majmin and 0.46 pp of GuitarSet's majmin.

The interval is empty. The cadence needs -0.23 and the floors -0.2375, 0.0075 apart; at -0.2375 the suite fails only the cadence and every floor holds, and at -0.23 the suite is green and Tiny AAM's root is 0.03 pp under (0.84132 against 0.84161), with GuitarSet's majmin and sevenths 0.66011 and 0.52852. Nor would -0.23 pass v5's margin rule: it lies 0.0025 above the cadence's failure, so a one-step neighbour fails the suite and the other the floors. The DSP therefore never calls `sus4(b7)`: its offset is -inf, as `sus2`'s is, and `test_the_dsp_never_calls_a_seventh_sus4` and `test_the_decoder_never_calls_a_seventh_sus4` hold it there. `sus4(b7)` stays in the vocabulary, the harmony and the viewer, and comes from the model engine or a manual edit. The plain Asus4 into A and the dominant seventh stay in the suite as synthesized cases.

## Bass reliability

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

The scores gain because a non-chord bass is scored as a slash that adds a tone to the estimate's pitch set (see [Evaluation](evaluation.md)), and the tie-break removes the passing notes that did that.

### The DSP's salience test

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

### The model's bass head

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

### Rows at the end of the bass stage

The rows of the shipped bass rules (the DSP's salience test and the model's bass head, above), scored by the CLI (`chordotomy evaluate`) on the final reference, at the commit that adds these rows. They were ["Current rows"](evaluation.md#current-rows) until the Beat This! stage, whose `dsp` rows equal them. Both engines snap to the DSP's beat grid here, so their beat columns are equal.

| | root | majmin | sevenths | tetrads | majmin_inv | N_est | N_ref | N_prec | N_rec | beat_F | CMLt | AMLt | period | bass_ref | inv_prec | inv_rec | nonchord |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tiny AAM (20 tracks), `dsp` | 0.842 | 0.803 | 0.768 | 0.768 | 0.713 | 0.003 | 0.032 | 0.819 | 0.071 | 0.827 | 0.686 | 0.766 | 0.999 | 0.851 | 0.000 | nan | 0.020 |
| GuitarSet (180 takes), `dsp` | 0.722 | 0.696 | 0.583 | 0.379 | 0.446 | 0.005 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 | 0.507 | 0.174 | 0.226 | 0.087 |
| Tiny AAM (20 tracks), `model` | 0.939 | 0.934 | 0.898 | 0.898 | 0.868 | 0.015 | 0.032 | 0.966 | 0.447 | 0.827 | 0.686 | 0.766 | 0.999 | 0.916 | 0.000 | nan | 0.000 |
| GuitarSet (180 takes), `model` | 0.827 | 0.872 | 0.819 | 0.533 | 0.592 | 0.032 | 0.000 | 0.000 | nan | 0.517 | 0.410 | 0.570 | 1.005 | 0.607 | 0.205 | 0.208 | 0.000 |

## Beat tracking

The model engine's beats come from Beat This!'s activation through librosa's one-tempo DP, at the commit that adds these rows ([Recognition](recognition.md), and ["The model engine's beats come from Beat This!"](decisions.md#the-model-engines-beats-come-from-beat-this)). The DSP keeps `beat_track(y=y)`, and its rows equal the bass stage's to every digit. Everything here ran on the Apple M4's CPU with beat-this 1.1.0 and torch 2.14.1; the CLI's rows are ["Current rows"](evaluation.md#current-rows).

GuitarSet is in Beat This!'s training data, and that decides how its rows are read. The training split is exactly the 180 `_comp` takes scored here: Beat This! trained on their `_mix` audio, where chordotomy scores their mono microphone recording (`_mic.wav`). So the shipped checkpoint, `final0`, has heard every one of them, and its GuitarSet scores are not a test. The authors also published the eight checkpoints of their cross-validation, `fold0` to `fold7`, where `fold<k>` did not train on the takes of fold k. The folds are assigned per take, and none of GuitarSet's 30 tunes keeps all its takes in one fold, so a fold checkpoint has still heard other players perform the same chart at the same tempo. Its scores are "take held out, tune seen", the fairest GuitarSet number there is; the two are reported side by side and never pooled. Tiny AAM is not in the training data, and its rows are `final0`'s.

The held-out run. The split is `guitarset/8-folds.split` in CPJKU/beat_this_annotations, one `<stem>_mix<TAB><fold>` line per take: 180 takes, 23 in each of folds 0 to 3 and 22 in each of folds 4 to 7. beat_this's source fixes the direction: its dataset uses the given fold for validation and the rest for training, and `train.py`'s `--fold` is "the CV fold number to *not* train on". The fold checkpoints are fetched from `<CHECKPOINT_URL>/fold<k>.ckpt`, `beats.CHECKPOINT_URL` being the directory `final0.ckpt` comes from, and pinned by their SHA-256. No hook in the repo selects them. A script outside it registers their pins in `beats.CHECKPOINTS`, points `beats.CACHE_DIR` at the verified files with downloads disabled, and wraps `timeline.analyze` so that each take runs with `beats.CHECKPOINT` set to its fold's checkpoint, clearing the cached net when the fold changes; `evaluate.run("guitarset", None, "model")` then scores the takes. All 180 ran on the checkpoint the split names.

| checkpoint | bytes | SHA-256 |
|---|---|---|
| `final0` (shipped) | 81,058,141 | `8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331` |
| `fold0` | 81,054,590 | `f5c6b6726179e20710e4be6a0fba4018f6cbc89f32f9c0dfd15072cb047578ad` |
| `fold1` | 81,054,590 | `617b5b9641cefa585c975c97ac4e7fb9c00165ec9827303e8a88fdbd5ff3b71f` |
| `fold2` | 81,054,590 | `cece4323bccc50738e415c91c204c93ca7021e42ab3a24da6a84dccaa7cc0d4c` |
| `fold3` | 81,054,590 | `849de186a21ed1cd41d0ac78dc412c61f5283dcafffa9dd32f390674c50792cf` |
| `fold4` | 81,054,590 | `0a17b1691edbae73a7fac35f6d26d5f8f9aa483b0e3aff5d891c74140f836c52` |
| `fold5` | 81,054,590 | `ea651e7a0d1a1b243ad3ff268969c8c3d4b7e6d06b1bfb451b020d40526275c2` |
| `fold6` | 81,054,590 | `07b32a484f2c99b676e7061650ea2cd2f9f889d87ea6c712782c5855742070b1` |
| `fold7` | 81,054,590 | `f26bed3c18c8f338a39b5a9524ffea7dce654e847ccf3d006e147fa7bf71d43f` |

The beat scores of the grid as the CLI writes it (`beats`, extended and rounded to the millisecond), F / CMLt / AMLt, and the tracks per error class. A track's class comes from its period ratio, within 10 %: half at 2, double at 0.5, 3:2 at 1.5 or 2/3, and at 1, correct when its CMLt is at least 0.5 and off-beat when its CMLt is under 0.5 and its AMLt at least 0.5. Other is anything else.

| grid | F / CMLt / AMLt | correct | half | double | 3:2 | off-beat | other |
|---|---|---|---|---|---|---|---|
| Tiny AAM, `dsp` | 0.827 / 0.686 / 0.766 | 15 | 1 | 1 | 2 | 0 | 1 |
| Tiny AAM, `model` | 0.896 / 0.797 / 0.802 | 17 | 1 | 0 | 1 | 0 | 1 |
| GuitarSet, `dsp` | 0.517 / 0.410 / 0.570 | 72 | 9 | 6 | 33 | 20 | 40 |
| GuitarSet, `model`, take held out | 0.919 / 0.839 / 0.940 | 149 | 27 | 0 | 3 | 1 | 0 |
| GuitarSet, `model`, `final0` (trained on these takes) | 0.958 / 0.889 / 0.978 | 156 | 23 | 1 | 0 | 0 | 0 |

The trackers' own beats, before the edge extension and the rounding, fall in the same classes. They score 0.833 / 0.693 / 0.774 and 0.519 / 0.408 / 0.568 on librosa's grids, and the same as above on Beat This!'s but for the held-out F, 0.920. These raw scores are what the variants below compare with.

On Tiny AAM, librosa's 3:2 lock on 1050 and double lock on 2462 become correct. Left on Beat This!'s grid are 0080's half lock, on both grids, 1941 at 3:2 (a ratio of 1.35, librosa's 0.66) and 0192, a tempo-change track at a ratio of 0.98 whose CMLt and AMLt are 0.44. On GuitarSet, librosa's other takes are 26 at a ratio of 0.74 to 0.81, a 4:3 lock, 12 near 1 whose CMLt and AMLt are both under 0.5, a drift, and two elsewhere (1.26, 1.66). Held out, 87 of librosa's 108 wrong takes become correct. Beat This! half-locks 27: 6 that librosa half-locks too, 9 that librosa had right and 12 it had wrong otherwise; one more take librosa had right goes to 3:2. Its other wrong takes are 3:2 locks on 01_SS1-68-E_comp, 02_SS1-68-E_comp (ratio 0.66) and 01_SS2-88-F_comp (0.68) and an off-beat lock on 01_SS2-107-Ab_comp (CMLt 0.00, AMLt 0.98), all four correct with `final0`; `final0`'s one double lock, 04_SS1-68-E_comp (0.50), is correct with its fold checkpoint. The research spike counted 22 off-beat and 24 3:2 takes on librosa's grid with other tolerances (3:2 at 1.5 only, off-beat at a CMLt under 0.1).

The variants, from the research spike that chose the tracker, run on 2026-10-02 in an environment of its own (Python 3.13.2, librosa 1.0.0, torch 2.14.1, beat-this 1.1.0): each tracker's raw beats, without the octave check or the edge extension, scored as `evaluate.beat_metrics` scores them, F / CMLt / AMLt. Beat This!'s GuitarSet column is the fold checkpoints'. The last column is the syncopated 86 BPM fixture's largest beat gap over its smallest, which `test_a_syncopated_constant_tempo_keeps_the_global_grid` bounds at 1.2.

| tracker | Tiny AAM | GuitarSet | GuitarSet, `final0` | syncopated fixture |
|---|---|---|---|---|
| librosa's onset strength → DP (the `dsp` engine) | 0.833 / 0.693 / 0.774 | 0.519 / 0.408 / 0.568 | — | 1.14, on the eighths (128 beats) |
| librosa's PLP (predominant local pulse), its local maxima | 0.661 / 0.104 / 0.609 | 0.536 / 0.055 / 0.426 | — | — |
| Beat This!'s own peak picking | 0.946 / 0.869 / 0.869 | 0.911 / 0.811 / 0.887 | 0.967 / 0.916 / 0.961 | 2.04 |
| Beat This! with madmom's DBN (λ = 100) | 0.933 / 0.867 / 0.867 | 0.927 / 0.851 / 0.957 | — | 1.63 |
| Beat This!'s activation → DP, its tempo following Beat This!'s beat spacing | 0.936 / 0.858 / 0.858 | 0.909 / 0.819 / 0.903 | 0.964 / 0.911 / 0.962 | 1.63 |
| Beat This!'s activation → DP, one tempo (the `model` engine) | 0.896 / 0.797 / 0.802 | 0.920 / 0.839 / 0.940 | 0.958 / 0.889 / 0.978 | 1.07 |
| the same with `small0` | 0.898 / 0.796 / 0.801 | no held-out checkpoint | — | 1.07 |

Through the snap (labels only, majmin), the peak picking, the DBN and the tempo-following DP score 0.953 on Tiny AAM, all three, and 0.899, 0.901 and 0.900 on GuitarSet, against the one-tempo DP's 0.950 and 0.900; `small0` scores 0.951 on Tiny AAM. A tempo taken from Beat This!'s median beat spacing instead of librosa's prior scored lower, F / CMLt 0.881 / 0.749 against 0.896 / 0.797 on Tiny AAM and 0.912 / 0.831 against 0.920 / 0.839 on GuitarSet.

The labels-only snap: the cached lv-chordia frames quantized onto each grid's `beats` by the beat majority, without the bass, as in ["Where the beat snap costs"](evaluation.md#where-the-beat-snap-costs).

| | root | majmin | sevenths | tetrads |
|---|---|---|---|---|
| Tiny AAM, librosa's grid | 0.9389 | 0.9340 | 0.8987 | 0.8987 |
| Tiny AAM, Beat This!, `final0` | 0.9552 | 0.9503 | 0.9141 | 0.9141 |
| GuitarSet, librosa's grid | 0.8272 | 0.8721 | 0.8195 | 0.5331 |
| GuitarSet, Beat This!, take held out | 0.8535 | 0.9002 | 0.8465 | 0.5504 |
| GuitarSet, Beat This!, `final0` (trained on these takes) | 0.8547 | 0.9018 | 0.8484 | 0.5518 |

Rounded to three digits, the librosa rows' majmin, 0.934 and 0.872, is that section's row for librosa's tracker. `final0` scores 0.16 pp of GuitarSet majmin above the held-out checkpoints.

The octave check on the new grid. It doubled no track on any grid: Tiny AAM with `final0`, GuitarSet with the fold checkpoints and with `final0`, and librosa's grids of both. Beat This!'s tracker grids are half-locked, at a period ratio within 10 % of 2, on one Tiny AAM track, 0080, which librosa half-locks too, and on 27 GuitarSet takes held out and 23 with `final0`, against librosa's 9. The 27 are 13 bossa nova and 13 jazz takes at 131 to 200 BPM and a rock take at 142, and the check catches none of them. Held out, `changes` is the number of chord changes decoded on the doubled grid and `share` the share of them on inserted beats:

| | changes | share | period |
|---|---|---|---|
| 00_BN2-166-Ab_comp | 26 | 0.42 | 1.99 |
| 00_BN3-154-E_comp | 15 | 0.27 | 2.03 |
| 00_Jazz1-200-B_comp | 12 | 0.67 | 2.01 |
| 00_Jazz2-187-F#_comp | 14 | 0.36 | 2.03 |
| 00_Jazz3-150-C_comp | 19 | 0.53 | 1.97 |
| 01_BN2-166-Ab_comp | 18 | 0.39 | 1.99 |
| 01_Jazz1-200-B_comp | 8 | 0.25 | 2.01 |
| 01_Jazz2-187-F#_comp | 19 | 0.47 | 2.03 |
| 02_BN1-147-Gb_comp | 10 | 0.50 | 1.99 |
| 02_BN2-131-B_comp | 13 | 0.00 | 1.98 |
| 02_BN2-166-Ab_comp | 23 | 0.52 | 1.99 |
| 02_Jazz1-200-B_comp | 6 | 0.33 | 2.01 |
| 02_Jazz2-187-F#_comp | 18 | 0.33 | 2.03 |
| 03_BN2-166-Ab_comp | 22 | 0.64 | 1.99 |
| 03_BN3-154-E_comp | 25 | 0.60 | 2.00 |
| 03_Jazz1-200-B_comp | 16 | 0.44 | 2.01 |
| 03_Jazz2-187-F#_comp | 24 | 0.42 | 1.95 |
| 04_BN1-147-Gb_comp | 10 | 0.50 | 1.99 |
| 04_BN2-166-Ab_comp | 19 | 0.58 | 1.99 |
| 04_Jazz1-200-B_comp | 22 | 0.32 | 2.01 |
| 04_Jazz2-187-F#_comp | 31 | 0.61 | 2.03 |
| 04_Rock2-142-D_comp | 14 | 0.43 | 1.98 |
| 05_BN1-147-Gb_comp | 23 | 0.70 | 1.99 |
| 05_BN2-166-Ab_comp | 27 | 0.44 | 1.99 |
| 05_BN3-154-E_comp | 29 | 0.48 | 2.03 |
| 05_Jazz1-200-B_comp | 22 | 0.41 | 2.01 |
| 05_Jazz2-187-F#_comp | 22 | 0.55 | 2.03 |

The highest shares, among tracks with at least 20 and at least 24 changes, the two neighbours of the change count:

| grid | half-locked (ratio near 2) | right period (ratio near 1) |
|---|---|---|
| Tiny AAM, `final0` | 0080: 0.35 on 72 changes | 2720: 0.33 on 224, 2990: 0.32 on 213 |
| GuitarSet, held out, 20 or more changes | 05_BN1-147-Gb_comp: 0.70 on 23, 03_BN2-166-Ab_comp: 0.64 on 22 | 01_SS2-107-Ab_comp: 0.72 on 29 (the off-beat lock), 01_BN3-119-G_comp: 0.67 on 24 |
| GuitarSet, held out, 24 or more | 04_Jazz2-187-F#_comp: 0.61 on 31, 03_BN3-154-E_comp: 0.60 on 25 | the same |
| GuitarSet, `final0`, 20 or more and 24 or more | 03_Jazz2-187-F#_comp: 0.62 on 24, 03_BN3-154-E_comp: 0.60 on 25 | 01_Funk2-119-G_comp: 0.68 on 25, 01_BN3-119-G_comp: 0.67 on 24 |

On GuitarSet the right-period takes reach higher shares than the half-locked ones, so no threshold separates them; on Tiny AAM every share is at most 0.35. Each one-step neighbour of the two constants, and the check switched off, leaves every grid as it is (labels-only snapped majmin):

| setting | Tiny AAM, `final0` | GuitarSet, held out | GuitarSet, `final0` | tracks doubled |
|---|---|---|---|---|
| 0.80, 24 changes (shipped) | 0.9503 | 0.9002 | 0.9018 | none |
| share 0.75 | 0.9503 | 0.9002 | 0.9018 | none |
| share 0.85 | 0.9503 | 0.9002 | 0.9018 | none |
| 20 changes | 0.9503 | 0.9002 | 0.9018 | none |
| 28 changes | 0.9503 | 0.9002 | 0.9018 | none |
| check off | 0.9503 | 0.9002 | 0.9018 | none |

So the constants, tuned on librosa's grids, stay at 0.80 and 24: no neighbour moves a track, so none can gain. The check stays for the case it was built for, which Beat This! has too: it locks the synthesized 180 BPM fixture at 36 beats, as librosa does, and the check doubles it on the model engine (`test_a_half_tempo_lock_is_doubled` in `test_beats_engine.py`).

Runtime and memory of `chordotomy analyze` on synthesized 3- and 6-minute mixes (the suite's `mix` fixture, a 16-beat progression repeated), on the same M4 with nothing else running, start-up included. Time is wall time per audio minute, the mean of two runs for the model and one for the DSP; memory is the peak resident set size. The DSP ran in the same session as a control.

| | 3 min: s per audio minute | 3 min: peak RSS | 6 min: s per audio minute | 6 min: peak RSS |
|---|---|---|---|---|
| `dsp` | 2.3 | 1.02 GB | 2.2 | 1.77 GB |
| model, Beat This!'s beats | 4.6 | 2.59 GB | 4.4 | 3.37 GB |

The DSP control ran faster than in the table under "Model engine" (3.3 and 3.1 s per audio minute there), so times from the two sessions do not compare; within this one, the model engine takes about twice the DSP's time, as before. Its peak memory is 0.23 and 0.20 GB above that table's. Beat This!'s activation alone takes 1.83 s on a 3-minute clip with the net loaded, and 2.5 s when the run includes importing torch and loading the net. The extra installs about 4.5 MB more packages, and the first model run adds the 81 MB checkpoint to the cache; the whole `model` extra installs 599 MB, 526 MB of it torch.

On the 86 BPM recording used as a check ("Tempo changes are not followed"), the model engine's grid has 435 beats of 0.650 to 0.859 s, median 0.697 s, against librosa's 437 of 0.604 to 0.743 s, also median 0.697 s; both read 86.1 BPM. Five gaps of 0.79 to 0.86 s, near 12.8 s and between 287 and 296 s, take its largest gap to 1.32 times its smallest (librosa's 1.23), while its 95th-percentile gap is 1.03 times its 5th. The gaps from 287 s fall in the outro, which slows down (the user confirmed it), so there the grid follows the music. Sampled every 0.1 s, its chords agree with the librosa-grid timeline's on 97.6 % of the recording.

Against the bass stage's rows ("Rows at the end of the bass stage"), the `model` rows gain on every chord column. Tiny AAM's root, majmin, sevenths, tetrads and majmin_inv go from 0.939, 0.934, 0.898, 0.898 and 0.868 to 0.955, 0.950, 0.914, 0.914 and 0.889, and GuitarSet's, held out, from 0.827, 0.872, 0.819, 0.533 and 0.592 to 0.854, 0.900, 0.847, 0.550 and 0.611; `final0`'s row is 0.001 to 0.003 above the held-out one. Tiny AAM's `N_est` stays at 0.015, its `N_prec` rises from 0.966 to 0.988 and its `N_rec` falls from 0.447 to 0.444. The bass columns move with the grid, since the bass head is averaged per beat: `bass_ref` rises from 0.916 to 0.926 on Tiny AAM and from 0.607 to 0.616 on GuitarSet, and GuitarSet's `inv_prec` and `inv_rec` fall from 0.205 and 0.208 to 0.199 and 0.191. That `inv_rec`, and `final0`'s 0.197, are under 0.2046, the floor the bass head's sweep held ("The model's bass head"). The lead accepted this for the stage on 2026-10-02, for three reasons: this stage's floors were the chord columns, with the bass columns reported; `inv_rec` moves with the grid, as above; and `majmin_inv` rose, from 0.592 to 0.611. A follow-up measured where the loss is. `BASS_SUPPORT` cannot recover it: from 0.5 to 0.8 it leaves `inv_rec` at 0.1912, since it gates only non-chord candidates and the inversions come from the DSP's chord-tone picks. Nor do the half-locks explain it: the 27 half-locked takes add 0.17 pp, and doubling their grid moves `inv_rec` by 0.04 pp. The loss is in takes the new grid tracks correctly, whose beats moved: Beat This!'s beats sit a median 6 ms after the annotated beats, where librosa's sat about 35 ms late, and which bass holds two beats depends on where the beats fall. One fingerpicked take, 00_SS1-100-C#_comp, whose lowest note cycles through the chord within each beat, costs about 0.95 pp alone. The metric swings by about a point with the grid itself: the new grid shifted by −1 to +4 frames gives 0.179 to 0.201, and librosa's own grid shifted by two frames either way gives 0.199 and 0.192, both under the floor. Raising it back costs `majmin_inv`: a `BASS_HOLD` of 1 gives 0.211 for −2.6 pp, and the bass on a doubled grid 0.211 for −1.3 pp. So the drop stands. Per take, 144 of the 180 held-out GuitarSet takes gain majmin over the librosa-grid timelines and 21 lose. The largest losses are takes Beat This! half-locks: 00_Jazz2-187-F#_comp from 0.787 to 0.696, 04_Jazz1-200-B_comp from 0.803 to 0.747 and 03_Jazz2-187-F#_comp from 0.856 to 0.806.

## The head's confident inversion

The model engine's bass took the DSP's pick first whenever it was a chord tone ("The model's bass head"). On adrenaline!!! (lv-chordia 1.1.0) that pick dropped a first inversion the chorus has: the reference's G – D/F♯ – Em at 2:24 came out as D/F♯ for two beats and D for two. lv-chordia decoded `D:maj/3` over all four, and its bass head heard F♯ at 0.85 on the third beat, but the DSP's pick there, the register's lowest salient note, was D, while the beat's bass chroma has F♯ loudest and D at 0.8 of it. The rule since: when the pick is the chord's root and the head's note is another chord tone with a posterior of at least `INVERSION_SUPPORT`, the head's note is the bass.

The datasets never meet the case. Scored through `evaluate.run` on cached model outputs (GuitarSet with `final0`, as `chordotomy evaluate` runs it), `INVERSION_SUPPORT` at 0.7, 0.8 and 0.9 leaves every column of both datasets equal to the current rows to the fifth digit: the rule changes no beat of Tiny AAM, one beat of GuitarSet at 0.7 and none at 0.8. Solo guitar has its bass on the lowest string, which the pick finds, and on Tiny AAM's mixes the head is never sure of a non-root tone over a root pick. So the value rests on the recordings. At 0.8 adrenaline!!!'s D/F♯ keeps its F♯ over all four beats and no other segment moves, there or in the ハロ/ハワユ cover; at 0.9 the rule no longer reaches the 0.85, which bounds it from above, and 0.8 is the middle of 0.7 to 0.85. It agrees with the bass stage: variant B lost because the head leans root and misses inversions, not because the inversions it names are wrong, and the head matched the chart on every verified case.

The rule moves only the bass, so it leaves the reference's G/D at 0:54 reading D, and that is the chord's call, not the bass's. lv-chordia decodes `D:maj` on 18 to 20 of each of the four beats' frames, and its posterior gives `G:maj/5` at most 0.10. The treble chroma of the first three beats is D with G and A, with B, G's third, under 0.1 and F♯, D's third, under 0.2: a suspended sound that is neither chord's triad. Only the fourth beat has B loudest, over G and D. Nothing in the model's output prefers G, so the chord stays the model's.

`BASS_SUPPORT` at 0.6 was measured on the same cache and refused. It would keep the cover's `A/B` at 1:41, IV over the dominant in E major, where the pick and the head both hear B and the head's posterior is 0.68 and 0.64, under 0.7. But on Beat This!'s grid it costs GuitarSet 0.04 to 0.05 pp of majmin, sevenths, majmin_inv and `bass_ref` (0.90176 to 0.90132, 0.84838 to 0.84792, 0.61376 to 0.61332 and 0.61680 to 0.61635) and doubles the share written as a non-chord bass (0.039 % to 0.084 %), with Tiny AAM unchanged: the non-chord basses it admits there mostly disagree with the reference. On librosa's grid 0.6 had tied 0.7.
