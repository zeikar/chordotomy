# Spelling

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
| `C:aug` | Caug |
| `C:dim` | Cdim |
| `C:sus2` | Csus2 |
| `C:sus4(b7)` | C7sus4 |
| `C:maj(9)` | Cadd9 |
| `C:min(9)` | Cmadd9 |

The numerals keep `+`, `ø7`, `°7` and `°`; the chord symbols use aug, m7♭5, dim7 and dim.

**A chord root.** Take the letter from the numeral's degree in the key:

- `bVII` in C is B♭ and `bVI` is A♭.
- `#IV` in C is F♯.
- A secondary dominant's root is a fifth above its target: `V7/V` in A♭ is B♭7, and `V7/vi` in C is E7.
- A secondary leading-tone chord's root is a half step below its target: `vii°7/ii` in C is C♯dim7, `vii°/ii` is C♯dim, and `viiø7/V` is F♯m7♭5.
- A diminished chord's root is spelled raised, as its numeral is: `#i°7` in C is C♯dim7, `#i°` is C♯dim, and `#v°7` is G♯dim7. Where that would take a double sharp, use the plain letter (`#i°7` in F♯ is Gdim7, `#i°` is Gdim). Every other chromatic root keeps the key's degree spelling: `bII` in C is D♭.
- A plain numeral takes the key's own spelling: `IV` in F is B♭.

**The bass.** Spell it as the chord member that `inversion` names. The first-inversion bass of B♭ is D. A diminished fifth stays a fifth: the second-inversion bass of F♯m7♭5 is C, not B♯. For `min6`, `third` is the added sixth (E under Gm6); for `sus4`, `first` is the fourth (C under Gsus4); for `sus2`, `first` is the second (D under Csus2); for `sus4(b7)`, `first` is the fourth and `third` the seventh (D and G under A7sus4); for `maj(9)` and `min(9)`, `third` is the added ninth (D under Cadd9).
