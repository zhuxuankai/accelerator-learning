from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "tools" / "skill-src" / "accelerator-study-copilot"


def test_skill_references_exist_and_are_linked():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    references = [
        "retrieval-and-citations.md",
        "weekly-maintenance.md",
        "progress-and-reading.md",
        "translation-and-math.md",
    ]
    for name in references:
        assert (SKILL / "references" / name).exists()
        assert name in text


def test_skill_ui_metadata_is_valid_and_auto_discoverable():
    data = yaml.safe_load((SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    assert data["interface"]["display_name"]
    assert "$accelerator-study-copilot" in data["interface"]["default_prompt"]
    assert data["policy"]["allow_implicit_invocation"] is True
