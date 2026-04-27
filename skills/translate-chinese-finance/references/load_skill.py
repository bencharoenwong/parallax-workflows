"""
load_skill.py - Loads Chinese translation rules from runtime-config-{zh-CN,zh-TW}.md

The auto-generated runtime configs use ## CONSTANT_NAME headers (e.g., ## COUNTRY_MAP),
matching the constant names in chinese_translation_config.py. This loader parses those
headers and returns python dict / list / scalar values.

Usage:
    from load_skill import get_dictionaries, get_prompts, build_replacement_dict

    # Default: zh-CN
    dicts = get_dictionaries()

    # Or pick a locale:
    dicts = get_dictionaries(locale="zh-TW")
    prompts = get_prompts(locale="zh-CN")

CLI smoke test:
    python3 load_skill.py             # zh-CN
    python3 load_skill.py --locale zh-TW

Skill path resolution order:
    1. CHINESE_SKILL_DIR env var (path to a directory containing runtime-config-*.md)
    2. ~/.claude/skills/translate-chinese-finance/references/
    3. The directory containing this script (works when bundled in CIO report scripts)
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

VALID_LOCALES = ("zh-CN", "zh-TW")


_LOCALE_FILES = {
    "zh-CN": ("skill_simplified.md", "runtime-config-zh-CN.md"),
    "zh-TW": ("skill_traditional.md", "runtime-config-zh-TW.md"),
}


def _candidate_dirs() -> list[Path]:
    """Search order: env override → installed skill (top + references) → bundled location."""
    cands: list[Path] = []
    env = os.environ.get("CHINESE_SKILL_DIR")
    if env:
        cands.append(Path(env))

    skill_root = Path.home() / ".claude" / "skills" / "translate-chinese-finance"
    cands.extend([skill_root, skill_root / "references"])

    here = Path(__file__).resolve().parent
    cands.extend([here.parent, here])  # top of skill, then references/

    # Dedup while preserving order
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _config_path(locale: str) -> Path:
    if locale not in VALID_LOCALES:
        raise ValueError(f"locale must be one of {VALID_LOCALES}, got {locale!r}")
    primary, legacy = _LOCALE_FILES[locale]
    for d in _candidate_dirs():
        for fname in (primary, legacy):
            p = d / fname
            if p.exists():
                return p
    raise FileNotFoundError(
        f"Neither {primary} nor {legacy} found in any of: "
        + ", ".join(str(d) for d in _candidate_dirs())
    )


# ---------- section parsing ----------

_SECTION_HEADER_RE = re.compile(r"^##\s+([A-Z][A-Z0-9_]*)\s*$", re.MULTILINE)


def _split_sections(content: str) -> dict[str, str]:
    """Return {SECTION_NAME: section_body} for every ## CONSTANT_NAME heading."""
    matches = list(_SECTION_HEADER_RE.finditer(content))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections[name] = content[body_start:body_end].strip()
    return sections


def _parse_table(body: str) -> dict[str, str]:
    """Parse a 2-column markdown table into {english: chinese}."""
    result: dict[str, str] = {}
    lines = [ln for ln in body.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return result
    # lines[0] = header, lines[1] = separator
    for line in lines[2:]:
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) >= 2 and not parts[0].startswith("_(empty)"):
            result[parts[0]] = parts[1]
    return result


def _parse_python_block(body: str):
    """Extract a ```python ...``` literal and ast.literal_eval it."""
    m = re.search(r"```python\s*\n(.*?)```", body, re.DOTALL)
    if not m:
        return None
    return ast.literal_eval(m.group(1))


def _parse_text_block(body: str) -> str | None:
    """Extract a ```text ...``` block as a string."""
    m = re.search(r"```text\s*\n(.*?)```", body, re.DOTALL)
    if not m:
        return None
    return m.group(1).rstrip()


def _parse_scalar(body: str):
    """Parse `bool: True`, `int: 5`, `str: foo` lines."""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("bool:"):
            return line.split(":", 1)[1].strip().lower() == "true"
        if line.startswith("int:"):
            return int(line.split(":", 1)[1].strip())
        if line.startswith("str:"):
            return line.split(":", 1)[1].strip()
    return None


def _parse_section(body: str):
    """Try parsers in order: scalar -> python literal -> text block -> table."""
    scalar = _parse_scalar(body)
    if scalar is not None:
        return scalar
    py = _parse_python_block(body)
    if py is not None:
        return py
    text = _parse_text_block(body)
    if text is not None:
        return text
    return _parse_table(body)


# ---------- public API ----------


def load_raw(locale: str = "zh-CN") -> dict:
    """Load all sections from the runtime config as a single dict."""
    path = _config_path(locale)
    content = path.read_text(encoding="utf-8")
    sections = _split_sections(content)
    return {name: _parse_section(body) for name, body in sections.items()}


# Mapping from CONSTANT_NAME (in runtime config) → snake_case key (in returned dict).
# Mirrors the Thai loader's get_dictionaries() interface.
SECTION_ALIASES = {
    "country_names": "COUNTRY_MAP",
    "months": "MONTH_MAP",
    "months_list": "MONTHS_LIST",
    "fiscal_year_formats": "FISCAL_YEAR_FORMATS",
    "currency_names": "CURRENCY_NAME_MAP",
    "currency_format_standards": "CURRENCY_FORMAT_STANDARDS",
    "stock_ratings": "RATING_TRANSLATIONS",
    "scenarios": "SCENARIO_FIXES",
    "factor_labels": "SCORE_LABEL_FIXES",
    "section_headers": "SECTION_HEADER_TRANSLATIONS",
    "sectors": "SECTOR_MAP",
    "stock_exchanges": "EXCHANGE_MAP",
    "recommendation_labels": "REC_LABEL_MAP",
    "stat_labels": "STAT_LABEL_MAP",
    "info_labels": "INFO_LABEL_MAP",
    "info_values": "INFO_VALUE_MAP",
    "peer_table_headers": "PEER_HEADER_MAP",
    "market_abbreviations": "MARKET_ABBREV_MAP",
    "financial_table_headers": "FINANCIAL_HEADER_MAP",
    "financial_statement_labels": "FINANCIAL_ROW_MAP",
    "financial_metrics": "FINANCIAL_METRICS",
    "portfolio_terms": "PORTFOLIO_TERMS",
    "risk_metrics": "RISK_METRICS",
    "macro_indicators": "MACRO_INDICATORS",
    "technical_terms": "TECHNICAL_TERMS",
    "number_units": "NUMBER_UNITS",
    "footer_text": "FOOTER_TEXT",
    "footer_page_formats": "FOOTER_PAGE_FORMATS",
    "duplicated_word_fixes": "DUPLICATED_CHAR_FIXES",
    "post_processing_fixes": "POST_PROCESSING_FIXES",
    "common_phrase_fixes": "COMMON_PHRASE_FIXES",
    "fixed_phrase_translations": "FIXED_PHRASE_TRANSLATIONS",
    "page_header_map": "PAGE_HEADER_MAP",
    "title_map": "TITLE_MAP",
    "stats_header_map": "STATS_HEADER_MAP",
    "equity_research_label": "EQUITY_RESEARCH_LABEL",
    "analyst_name_map": "ANALYST_NAME_MAP",
    "company_name_map": "COMPANY_NAME_MAP",
    "company_name_by_english": "COMPANY_NAME_BY_ENGLISH",
    "hallucination_cell_keywords": "HALLUCINATION_CELL_KEYWORDS",
}


def get_dictionaries(locale: str = "zh-CN") -> dict:
    """Return a dict of all translation tables, keyed with snake_case names.

    Adds a few constant fields for parity with Thai loader.
    """
    raw = load_raw(locale)
    out: dict = {}
    for snake, const in SECTION_ALIASES.items():
        out[snake] = raw.get(const, {})

    # Locale metadata
    out["language_code"] = raw.get("LANGUAGE_CODE", locale)
    out["language_name"] = raw.get("LANGUAGE_NAME", "")
    out["language_script"] = raw.get("LANGUAGE_SCRIPT", "")

    # Hard-coded code-switching lists (kept in English regardless of locale).
    # These mirror the Thai loader's list shape so downstream scripts can reuse logic.
    out["financial_ratios_keep_english"] = [
        "P/E", "P/B", "P/S", "P/FCF", "EV/EBITDA", "EV/Revenue",
        "ROE", "ROA", "ROIC", "EPS", "EBITDA", "YTD", "MTD", "QoQ", "YoY", "D/E",
    ]
    out["risk_terms_keep_english"] = [
        "Tracking Error", "Sector Rotation", "Expected Shortfall", "CVaR", "VaR",
        "Alpha", "Beta", "Max Drawdown", "Information Ratio", "Sharpe Ratio",
        "Sortino Ratio", "Active Share", "Hit Ratio",
        "Effective Number of Holdings", "Performance Attribution",
    ]
    out["acronyms_keep_english"] = [
        "ETF", "REIT", "GDP", "CPI", "PMI", "CIO", "CEO", "CFO", "ESG",
        "IPO", "M&A", "AUM", "AI", "ML", "IoT", "5G", "EV", "AR", "VR",
        "SaaS", "API",
    ]
    return out


def get_prompts(locale: str = "zh-CN") -> dict:
    """Return prompt templates for translate / review / final-filter passes."""
    raw = load_raw(locale)
    translation = raw.get("TRANSLATION_PROMPT") or ""
    review = raw.get("REVIEW_PROMPT") or ""

    return {
        "condensed": translation[:2000] if translation else "",
        "translation": translation,
        "review": review,
        "final_filter": (
            review
            + "\n\nFinal-pass focus: naturalness, terminology consistency, "
            "no doubled chars, correct script (no mixed Simplified/Traditional)."
        ),
    }


def build_replacement_dict(locale: str = "zh-CN") -> dict:
    """All wrong→correct replacement rules merged (post-processing pass)."""
    d = get_dictionaries(locale)
    combined: dict = {}
    for key in (
        "scenarios",
        "post_processing_fixes",
        "common_phrase_fixes",
        "fixed_phrase_translations",
    ):
        if isinstance(d.get(key), dict):
            combined.update(d[key])
    # duplicated_word_fixes is a list of (wrong, correct) tuples
    dup = d.get("duplicated_word_fixes")
    if isinstance(dup, list):
        for entry in dup:
            if isinstance(entry, tuple) and len(entry) == 2:
                combined[entry[0]] = entry[1]
    return combined


def build_label_dict(locale: str = "zh-CN") -> dict:
    """All English→Chinese translation mappings merged."""
    d = get_dictionaries(locale)
    combined: dict = {}
    for key in (
        "country_names",
        "months",
        "currency_names",
        "stock_ratings",
        "factor_labels",
        "recommendation_labels",
        "info_labels",
        "info_values",
        "section_headers",
        "sectors",
        "stock_exchanges",
        "stat_labels",
        "peer_table_headers",
        "market_abbreviations",
        "financial_table_headers",
        "financial_statement_labels",
        "financial_metrics",
        "portfolio_terms",
        "risk_metrics",
        "macro_indicators",
        "technical_terms",
        "page_header_map",
        "title_map",
        "stats_header_map",
        "analyst_name_map",
    ):
        if isinstance(d.get(key), dict):
            combined.update(d[key])
    return combined


# Aliases for parity with Thai loader
def get_all_replacements(locale: str = "zh-CN") -> dict:
    return build_replacement_dict(locale)


def get_all_translations(locale: str = "zh-CN") -> dict:
    return build_label_dict(locale)


# ---------- CLI smoke test ----------


def _main():
    parser = argparse.ArgumentParser(description="Smoke test load_skill.py")
    parser.add_argument("--locale", choices=VALID_LOCALES, default="zh-CN")
    args = parser.parse_args()

    print(f"Loading runtime config for locale={args.locale} from "
          f"{_config_path(args.locale)}")

    dicts = get_dictionaries(args.locale)
    print(f"\nlanguage_code={dicts['language_code']}  "
          f"language_name={dicts['language_name']}  "
          f"script={dicts['language_script']}")

    print("\nDictionary sizes:")
    for name in sorted(SECTION_ALIASES.keys()):
        v = dicts.get(name)
        if isinstance(v, dict):
            print(f"  {name:35s} {len(v):4d} entries")
        elif isinstance(v, list):
            print(f"  {name:35s} {len(v):4d} items")
        elif v:
            print(f"  {name:35s} (scalar/text)")

    prompts = get_prompts(args.locale)
    print(f"\nPrompts loaded: translation={len(prompts['translation'])} chars, "
          f"review={len(prompts['review'])} chars")

    repl = build_replacement_dict(args.locale)
    labels = build_label_dict(args.locale)
    print(f"\nMerged: {len(repl)} replacement rules, {len(labels)} label translations")

    # Sanity assertions: a few invariants per locale
    if args.locale == "zh-CN":
        assert dicts["stock_ratings"].get("BUY") == "买入", "zh-CN BUY mismatch"
        assert dicts["scenarios"].get("Bull") == "乐观情景", "zh-CN Bull mismatch"
    elif args.locale == "zh-TW":
        assert dicts["stock_ratings"].get("BUY") == "買入", "zh-TW BUY mismatch"
        assert dicts["scenarios"].get("Bull") == "樂觀情境", "zh-TW Bull mismatch"
    print("\nInvariants OK.")


if __name__ == "__main__":
    _main()
