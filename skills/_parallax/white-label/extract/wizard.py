"""Wizard-mode placeholder. Real implementation is in SKILL.md orchestration
via AskUserQuestion. This function exists so callers have a uniform API."""

from datetime import datetime, timezone
from typing import Any, Dict


def extract_from_wizard() -> Dict[str, Any]:
    """Guided intake via interactive questions.

    Wizard extraction requires interactive input; the actual prompts are
    issued by SKILL.md via AskUserQuestion. This function returns a stub
    so upstream code has a uniform return shape to test against.
    """
    return {
        "colors": {},
        "logos": {},
        "fonts": {},
        "source": {
            "type": "wizard",
            "reference": None,
        },
        "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        "confidence_scores": {},
        "note": "Wizard extraction requires interactive input; implement in SKILL.md orchestration",
    }
