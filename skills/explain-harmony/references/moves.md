# Explaining the moves

How to turn chordotomy's labels into short explanations. The JSON supplies the facts; this file supplies the reasons those facts work.

The rules the analyzer used to assign each role are in the plugin's `docs/ARCHITECTURE.md`, section "Harmonic analysis". SKILL.md gives the full path as `${CLAUDE_PLUGIN_ROOT}/docs/ARCHITECTURE.md`. Don't resolve it against the user's working directory.

## Spelling

The JSON spells every root with sharps. Respell for the reader.

**The key.** Use the conventional name:

| JSON | say |
| --- | --- |
| `A#:maj` | B♭ major |
| `D#:maj` | E♭ major |
| `G#:maj` | A♭ major |
| `C#:maj` | D♭ major |
| `A#:min` | B♭ minor |
| `D#:min` | E♭ minor |

Keep the rest as written: F♯ major, C♯ minor, G♯ minor, F♯ minor.

**A chord symbol.** Write the quality the way a pop chart does:

| JSON | say |
| --- | --- |
| `C:maj` | C |
| `C:min` | Cm |
| `C:7` | C7 |
| `C:maj7` | Cmaj7 |
| `C:min7` | Cm7 |
| `C:min6` | Cm6 |
| `C:hdim7` | Cm7♭5 |
| `C:dim7` | Cdim7 |
| `C:sus4` | Csus4 |

The numerals keep `ø7` and `°7`; the chord symbols use m7♭5 and dim7.

**A chord root.** Take the letter from the numeral's degree in the key:

- `bVII` in C is B♭ and `bVI` is A♭.
- `#IV` in C is F♯.
- A secondary dominant's root is a fifth above its target: `V7/V` in A♭ is B♭7, and `V7/vi` in C is E7.
- A secondary leading-tone chord's root is a half step below its target: `vii°7/ii` in C is C♯dim7, and `viiø7/V` is F♯m7♭5.
- A diminished chord's root is spelled raised, as its numeral is: `#i°7` in C is C♯dim7, and `#v°7` is G♯dim7. Where that would take a double sharp, use the plain letter (`#i°7` in F♯ is Gdim7). Every other chromatic root keeps the key's degree spelling: `bII` in C is D♭.
- A plain numeral takes the key's own spelling: `IV` in F is B♭.

**The bass.** Spell it as the chord member that `inversion` names. The first-inversion bass of B♭ is D. A diminished fifth stays a fifth: the second-inversion bass of F♯m7♭5 is C, not B♯. For `min6`, `third` is the added sixth (E under Gm6); for `sus4`, `first` is the fourth (C under Gsus4).

## Figured-bass numerals

Build the progression line from `numeral` and `inversion`:

| chord in `numeral` | `root` | `first` | `second` | `third` |
| --- | --- | --- | --- | --- |
| triad (`I`, `vi`, `bVII`, …) | I | I6 | I64 | none |
| seventh (`V7`, `VII7`, `IV7`, …) | V7 | V65 | V43 | V42 |
| major seventh (`IVmaj7`, `Imaj7`, …) | IVmaj7 | IVmaj65 | IVmaj43 | IVmaj42 |
| minor seventh (`ii7`, `vi7`, …) | ii7 | ii65 | ii43 | ii42 |
| half-diminished (`viiø7`, `iiø7`, …) | viiø7 | viiø65 | viiø43 | viiø42 |
| diminished seventh (`vii°7`, `#i°7`, …) | vii°7 | vii°65 | vii°43 | vii°42 |

- **`add6` and `sus4`** take no figure in any inversion: their inversions are not stacks of thirds. Write the numeral and name the bass, e.g. "ivadd6 (bass A♭)".
- **Secondary dominant or leading-tone chord:** put the figure before the slash. `V7/V` in first inversion is V65/V, `V/vi` in first inversion is V6/vi, and `vii°7/ii` in first inversion is vii°65/ii.
- **`non_chord`:** keep the numeral and name the bass, e.g. "I (bass D)".
- **`null`:** use the numeral alone.

## Secondary dominants (`role: secondary_dominant`, `V/x` or `V7/x`)

The chord is V (or V7) of the chord named in `target`. It lends that chord a leading tone: its third sits a half step below the target's root. In C, D7 carries F♯, which pulls up to G. The seventh adds a tritone that wants to resolve toward the target.

Judge the resolution by roots, not by numeral strings. The "next chord" is defined in SKILL.md.

- **Resolved.** The next chord's root (from `chord`) is the target's root. The chord briefly makes the target sound like a temporary tonic; this is called tonicization.
- **A chain.** The next chord is itself a secondary dominant on the target's root, e.g. E7 → A7 → D7 → G7 in C. Each chord resolves by fifth into the next dominant. Describe the chain as one move.
- **Delayed.** The next chord is the tonic in second inversion before V (`V/V` → `I64` → `V`). The resolution waits one chord for the cadential six-four.
- **Swerved.** Anything else follows. Name it: `V7/vi` → `IV` sets up vi and swerves away, the way a deceptive cadence does.
- **Unresolved.** `N` follows, so the chord hangs over silence or a passage with no clear harmony.

Common ones:

- **In major:**
  - `V/V` → `V`, the classic push into the dominant.
  - `V/vi` → `vi`, E → Am in C, which is very common in pop.
  - `V/ii` → `ii`.
  - `V7/IV` → `IV`.
- **In minor:** `V/V` (B → E in A minor), `V/iv` (a major tonic leading into iv), `V7/VI` (C7 → F in A minor), and `V/VII`. G and G7 in A minor are diatonic `VII` and `VII7`, so neither V/III nor V7/III ever appears.
- **Blues:** in a blues, I7 is labeled `V7/IV`. When I7, IV7 and V7 all appear, the sevenths are blues colour, not repeated tonicization. Say that instead.

## Secondary leading-tone chords (`vii°7/x`, `viiø7/x`)

These also have `role: secondary_dominant`. The chord is vii°7 or viiø7 of the chord named in `target`: its root sits a half step below the target's root and leads up into it, the way the leading tone leads to the tonic. Like a dominant seventh it holds a tritone, which resolves onto the target.

The analyzer gives this label only when the next chord is diatonic on the target's root, so a `vii°7/x` or `viiø7/x` is always resolved, in the terms above. A diminished chord that swerves, or hangs over `N`, gets no target: it keeps its plain numeral (`#ivø7`, `#i°7`) and is chromatic or borrowed. Judge where it goes as you would for a dominant. An `ø7` sets up the chord a half step above its root. A `°7` is spelled by the next chord only when one of its notes is a half step below that chord's root; otherwise its root is one of four spellings, so call it a passing or common-tone diminished chord and name no target.

Common in J-pop, as passing chords in major:

- **`vii°7/ii` → `ii`:** `#i°7`, C♯dim7 → Dm in C. Between I and ii it fills the whole step, often over a bass climbing C – C♯ – D.
- **`viiø7/V` → `V`:** `#ivø7`, F♯m7♭5 → G in C, a push into the dominant.

The analyzer spells a diminished chord by where it leads. A dim7's four notes are the notes of three other dim7s (C♯dim7, Edim7, Gdim7 and B♭dim7 sound the same), and a m6 has the notes of the m7♭5 a minor third below (Am6 is F♯m7♭5). When one of them leads into the next chord, the JSON names that one, unless an m6 has its own root in the bass. So a `candidates` entry with the same notes as `chord` is not a different sound, only the same notes spelled from another root. Don't present it as a misheard chord.

## Borrowed chords (`role: borrowed`)

This is modal mixture: a chord taken from the parallel key, which shares the tonic but has the other mode. Name the borrowed tones.

In C major:

| chord | borrowed tones |
| --- | --- |
| Cm | E♭ (♭3) |
| Fm | A♭ (♭6) |
| Gm | B♭ (♭7) |
| B♭ | B♭ (♭7) |
| B♭7 | B♭ and A♭ (♭7, ♭6) |
| A♭ | A♭ and E♭ (♭6, ♭3) |
| E♭ | E♭ and B♭ (♭3, ♭7) |
| Fm6 | A♭ (♭6) |
| Bdim7 | A♭ (♭6) |
| Dm7♭5 | A♭ (♭6) |

Common in major:

- **`iv`:** the minor subdominant. The ♭6 sinks toward 5, so `iv` → `I` gives a wistful, darkened close.
- **`ivadd6`:** IVm6 on a chart, Fm6 in C. The same ♭6 sinking to 5 as `iv`, with the added sixth (D in C) as colour.
- **`vii°7`:** the diminished seventh on the leading tone, from the parallel minor's harmonic form (Bdim7 in C). It acts like a dominant: B leads up to C and A♭ sinks to G.
- **`iiø7`:** Dm7♭5 in C, the minor key's ii before V; its A♭ sinks to G.
- **`bVII` → `I`:** the Mixolydian cadence of rock. In jazz, the "backdoor" is the related ♭VII7 → I.
- **`bVI` → `bVII` → `I`:** an Aeolian approach to the major tonic, informally the "Mario cadence". Describe it rather than lean on the nickname.
- **`bIII`, `i`, `v`:** a darker, modal shade of the major key.

Common in minor:

- **`I`:** a major tonic. As the last chord it is the Picardy third.
- **`IV`:** the Dorian IV, with the raised sixth.
- **`ii`, `#iii`, `#vi`:** rarer.

## Chromatic chords (`role: chromatic`)

The chord is neither diatonic, nor a secondary dominant, nor borrowed. Describe how its root and its direction of motion relate to the key.

- **`bII7` → `I`:** the tritone substitute for V7. Its root slides down a half step to the tonic.
- **`bVI7` in major, `VI7` in minor, → `V`:** the German-sixth sound. Its root slides down a half step to the dominant.
- **`bII`:** a half step above the tonic, which gives a Neapolitan colour.
- **`IV7`:** a subdominant whose own seventh (E♭ over F in C) is the key's blue ♭3. It is common in blues.
- **`#ivø7` that does not go to `V`:** F♯m7♭5 in C, the descending #IVm7♭5 → IV of J-pop. The root falls a half step to IV instead of rising to V.

Chromatic labels are the likeliest extraction errors. When a segment's `candidates` include a diatonic chord, mention it as the alternative reading.

## Inversions and bass lines

- **First inversion** (third in the bass): lighter than root position, and it usually lets the bass move by step, as in C – G/B – Am.
- **Second inversion** (fifth in the bass): read it from the bass around it.
  - `I64` right before `V` is the cadential six-four, which works as a decorated dominant. The JSON still gives it `function: tonic`, so present the dominant reading as interpretation.
  - A passing six-four's bass moves by step through the chord.
  - A pedal six-four keeps the same bass on both sides.
- **Seventh chord in third inversion** (`V42`): the seventh is in the bass and resolves down a step to `I6`.
- **Stepwise bass line:** describe the line itself, such as a descending walk C–B–A–G. Name a pattern (lament bass, Pachelbel-like) only when the line clearly is one.

## A `non_chord` bass

A bass that is not a chord tone usually means a chord outside the vocabulary (add9, 6/9, an eleventh chord) that the analyzer had to name by its upper part, or a passing note in the bass:

| label + bass | likely chord |
| --- | --- |
| F over G, when G is the key's dominant | G9sus4 / G11, a sus dominant acting as V |

Offer that reading.

A pedal point is different: the same `bass` held across segments whose `chord` changes, typically the tonic or the dominant. Its inversions vary (root, second, `non_chord`). A loud pedal can also drag the chord label itself toward chords that contain the pedal note.

## Colour tones

`Imaj7`, `IVmaj7`, `ii7`, `iii7` and `vi7` are diatonic chords with their seventh added. The seventh is colour, not a new function: `IVmaj7` is still a predominant. Mention the sevenths once for the song, not chord by chord.

`Vsus4` → `V` is a suspension: the fourth (C over G in C) resolves down to the third (B). It decorates V; it is not a substitute dominant.

## When everything is diatonic

Describe motions, not phrase-level cadences, because the analyzer knows no phrase boundaries and no melody. Never say "perfect authentic".

| major | minor | motion |
| --- | --- | --- |
| `V` / `V7` → `I` | `V` / `V7` → `i` | dominant to tonic, the authentic motion |
| `IV` → `I` | `iv` → `i` | plagal |
| `V` → `vi` | `V` → `VI` | deceptive |
| `ii` → `V` → `I` | | predominant → dominant → tonic, a phrase model |
| a run that stops on `V` before `N` | same | half-cadence-like |
