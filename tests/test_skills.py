import re
from pathlib import Path

import pytest

from chordotomy import __version__
from chordotomy.timeline import SCHEMA_VERSION

SKILL = Path(__file__).resolve().parents[1] / "skills" / "extract-chords"

# The sdist carries the tests but not the skill, which stays in the repository.
pytestmark = pytest.mark.skipif(not SKILL.is_dir(), reason="no skills/ outside a checkout")


def test_uvx_pins_are_this_release():
    # Outside the plugin the skill runs the release it pins, so the pins move with the version.
    text = (SKILL / "references" / "get-timeline.md").read_text(encoding="utf-8")
    assert re.findall(r"chordotomy(?:\[model\])?==([\w.]+)", text) == [__version__] * 2


def test_skill_is_written_for_this_schema():
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert re.findall(r"written for version (\d+)", skill) == [str(SCHEMA_VERSION)]
    get_timeline = (SKILL / "references" / "get-timeline.md").read_text(encoding="utf-8")
    versions = re.search(r'schema_version"\) not in \(([\d, ]+)\)', get_timeline).group(1)
    assert str(SCHEMA_VERSION) in versions.split(", ")


def test_references_need_no_plugin_root():
    # Claude Code substitutes ${CLAUDE_PLUGIN_ROOT} only in SKILL.md, never in the files it names.
    for path in (SKILL / "references").glob("*.md"):
        assert "CLAUDE_PLUGIN_ROOT" not in path.read_text(encoding="utf-8"), path.name
