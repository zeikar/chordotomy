# CLAUDE.md

Project-specific instructions for chordotomy. The global ~/.claude/CLAUDE.md still applies; this only adds project rules.

## Documentation map

- [README.md](README.md): what it does, what it won't do, roadmap, dev commands
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): pipeline, the chord-timeline JSON, design decisions and their reasons
- CLAUDE.md (this file): rules to follow while working

## Rules

The reasons are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#design-decisions).

- **Stay an analyzer.** Staff notation, melody → MIDI, section detection, and model training are out. Changing that takes an explicit decision from the user, not a drive-by feature.
- Chord correction and manual entry are core features. Don't treat them as polish.
- **No GPL/AGPL dependencies.** Essentia and Chordino are out. Check the license before adding a dependency, including the terms on any pretrained weights.
- **The `model` extra is optional.** The default install, `chordotomy --version` and the DSP path never import torch or lv_chordia. The default suite runs without them, model tests skip without the extra, and the engine runs on the CPU.
- Show chord candidates as a ranked list. Don't show percentages unless a calibrated model produced them.
- Audio never leaves the machine. No upload service.
- Tests synthesize their audio. Never commit recordings.
- The version lives only in `pyproject.toml`; code reads it through `importlib.metadata`. like-surgeon kept a second copy in `__init__.py`, and the two drifted.
- Once the chord-timeline JSON has a schema, document it in ARCHITECTURE.md and treat changes to it as breaking. The `explain-harmony` skill reads it too, so a schema change updates `skills/explain-harmony/` (its version check and field list).
