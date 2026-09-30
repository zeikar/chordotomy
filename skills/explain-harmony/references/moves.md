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

**A chord root.** Take the letter from the numeral's degree in the key:

- `bVII` in C is B♭ and `bVI` is A♭.
- `#IV` in C is F♯.
- A secondary dominant's root is a fifth above its target: `V7/V` in A♭ is B♭7, and `V7/vi` in C is E7.
- A plain numeral takes the key's own spelling: `IV` in F is B♭.

**The bass.** Spell it as the chord member that `inversion` names. The first-inversion bass of B♭ is D.

## Figured-bass numerals

Build the progression line from `numeral` and `inversion`:

| chord in `numeral` | `root` | `first` | `second` | `third` |
| --- | --- | --- | --- | --- |
| triad (`I`, `vi`, `bVII`, …) | I | I6 | I64 | none |
| seventh (`V7`, `VII7`, `IV7`, …) | V7 | V65 | V43 | V42 |

- **Secondary dominant:** put the figure before the slash. `V7/V` in first inversion is V65/V, and `V/vi` in first inversion is V6/vi.
- **`non_chord`:** keep the numeral and name the bass, e.g. "I (bass D)".
- **`null`:** use the numeral alone.

## Secondary dominants (`role: secondary_dominant`)

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

Common in major:

- **`iv`:** the minor subdominant. The ♭6 sinks toward 5, so `iv` → `I` gives a wistful, darkened close.
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

The chord vocabulary is only maj, min and 7. So a bass that is not a chord tone most often means a richer chord that the analyzer had to name by its upper part:

| label + bass | likely chord |
| --- | --- |
| C over A | Am7 |
| Am over F | Fmaj7 |
| Em over C | Cmaj7 |
| F over G, when G is the key's dominant | G9sus4 / G11, a sus dominant acting as V |

Offer that reading.

A pedal point is different: the same `bass` held across segments whose `chord` changes, typically the tonic or the dominant. Its inversions vary (root, second, `non_chord`). A loud pedal can also drag the chord label itself; the architecture notes that a D pedal under Am reads as D7.

## When everything is diatonic

Describe motions, not phrase-level cadences, because the analyzer knows no phrase boundaries and no melody. Never say "perfect authentic".

| major | minor | motion |
| --- | --- | --- |
| `V` / `V7` → `I` | `V` / `V7` → `i` | dominant to tonic, the authentic motion |
| `IV` → `I` | `iv` → `i` | plagal |
| `V` → `vi` | `V` → `VI` | deceptive |
| `ii` → `V` → `I` | | predominant → dominant → tonic, a phrase model |
| a run that stops on `V` before `N` | same | half-cadence-like |
