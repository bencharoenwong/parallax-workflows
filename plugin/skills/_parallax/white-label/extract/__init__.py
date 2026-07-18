"""Brand asset extraction package.

Re-exports all public symbols at package level so existing imports
(`from extract import ColorExtractor`, etc.) keep working unchanged.

Module map:
  - colors    — hex regex extractor, normalization, role assignment by frequency
  - voice     — voice corpus assembly (LLM-driven extraction lives in SKILL.md)
  - ooxml     — PPTX/DOCX/theme-XML extraction
  - web_pdf   — URL and PDF extraction (LogoExtractor, FontExtractor)
  - wizard    — wizard-mode stub
  - merge     — cross-source validation and draft merging
"""

from .colors import (
    ColorExtractor,
    _normalize_hex,
    _is_pure_white,
    _is_dark_text_candidate,
    _is_neutral_grey,
    _assign_color_roles_by_frequency,
)
from .voice import _voice_corpus_from_text
from .ooxml import (
    _OOXML_A_NS,
    _parse_ooxml_theme,
    _theme_to_role_map,
    extract_from_pptx,
    extract_from_docx,
)
from .web_pdf import (
    LogoExtractor,
    FontExtractor,
    extract_from_url,
    extract_from_pdf,
)
from .wizard import extract_from_wizard
from .merge import (
    cross_validate_visual,
    merge_drafts,
)

__all__ = [
    # colors
    "ColorExtractor",
    "_normalize_hex",
    "_is_pure_white",
    "_is_dark_text_candidate",
    "_is_neutral_grey",
    "_assign_color_roles_by_frequency",
    # voice
    "_voice_corpus_from_text",
    # ooxml
    "_OOXML_A_NS",
    "_parse_ooxml_theme",
    "_theme_to_role_map",
    "extract_from_pptx",
    "extract_from_docx",
    # web_pdf
    "LogoExtractor",
    "FontExtractor",
    "extract_from_url",
    "extract_from_pdf",
    # wizard
    "extract_from_wizard",
    # merge
    "cross_validate_visual",
    "merge_drafts",
]
