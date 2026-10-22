"""Voice corpus assembly. LLM-driven voice extraction lives in SKILL.md;
this module only normalizes and packages source text for the prompt."""

import re
from typing import Any, Dict


def _voice_corpus_from_text(text: str, max_words: int = 3000) -> Dict[str, Any]:
    """Package body text for downstream voice extraction.

    Voice is extracted via LLM prompting in SKILL.md orchestration, not here.
    This helper just normalizes the corpus and reports its size so the
    SKILL knows whether the sample is large enough.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    words = cleaned.split() if cleaned else []
    retained_words = words[:max_words]
    retained_text = " ".join(retained_words)
    return {
        "text": retained_text,
        "word_count": len(retained_words),
        "truncated": len(words) > max_words,
    }
