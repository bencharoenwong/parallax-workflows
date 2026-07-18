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
    words = cleaned.split(" ")
    n_words = len([w for w in words if w])
    truncated = " ".join(words[:max_words]) if n_words > max_words else cleaned
    return {
        "text": truncated,
        "word_count": n_words,
        "truncated": n_words > max_words,
    }
