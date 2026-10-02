#!/usr/bin/env python3
"""
Post-translation quality validator for Thai financial translations.
Usage: python3 validate-translation.py <output_file> --source <source_file>
Style only: python3 validate-translation.py <output_file> --style-only
"""
import re

import importlib.util
from pathlib import Path

# .skill packages vendor the helper here; repo/plugin installs use _parallax.
_candidates = (Path(__file__).with_name("translation_common.py"),
               Path(__file__).resolve().parents[2] / "_parallax" / "translation_validate.py")
_common_path = next((p for p in _candidates if p.is_file()), None)
if _common_path is None:
    raise ImportError("Translation validator helper is missing; rebuild the skill package")
_spec = importlib.util.spec_from_file_location("translation_common", _common_path)
_common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_common)
apply_waivers = _common.apply_waivers


# Known no-space intra-word doublings from SKILL.md §10 "Common AI Errors —
# Auto-Fix". The space-requiring regexes below only catch space-separated
# repeats, so these concatenated forms need an explicit literal-substring check.
_SECTION10_DOUBLINGS = ("ราราคา", "คาดว่าว่า", "ที่ที่", "จะจะ", "และและ", "การเสถียรภาพ")


def validate(filepath: str, source_path: str | None = None):
    data, texts, errors, warnings = _common.validate_common(filepath, "th", source_path)
    if data is None:
        return errors, warnings
    for key, text in texts.items():
        # --- ERRORS ---

        # Doubled consecutive Thai words (2+ chars).
        # Note: Python's \w does NOT match Thai vowel diacritic marks (sara u ุ, sara i ิ, etc.),
        # so \w-based patterns silently miss Thai text. Use the Thai Unicode block explicitly.
        for m in re.finditer(r"([\u0E00-\u0E7F]{2,}) \1", text):
            errors.append(f"[{key}] Doubled Thai word: '{m.group()}'")
        # Also catch doubled ASCII words (for mixed-language content)
        for m in re.finditer(r"\b([A-Za-z]{2,})\b \1\b", text):
            errors.append(f"[{key}] Doubled word: '{m.group()}'")
        # No-space intra-word doublings (§10) that the space-requiring regexes miss.
        for bad in _SECTION10_DOUBLINGS:
            if bad in text:
                errors.append(f"[{key}] Doubled (no-space) word: '{bad}'")

        # Wrong terms that should stay English
        wrong_terms = {
            "อัลฟา": "Alpha", "อัลฟ่า": "Alpha",
            "เบต้า": "Beta", "เบตา": "Beta",
            "อัตราส่วนชาร์ป": "Sharpe Ratio",
            "พอร์ตโฟลิโอ": "พอร์ต", "พอร์ตการลงทุน": "พอร์ต",
            "เกณฑ์อ้างอิง": "ดัชนีอ้างอิง",
            "เมตริก": "ตัวชี้วัด",
            "ไฮไลท์": "ประเด็นสำคัญ", "ไฮไลต์": "ประเด็นสำคัญ",
        }
        for wrong, correct in wrong_terms.items():
            if wrong in text:
                errors.append(f"[{key}] Wrong term '{wrong}' → should be '{correct}'")

        # --- WARNINGS ---

        # Awkward การ + English (excluding compound words like ผู้ว่าการ)
        for m in re.finditer(r"(?<!\S)การ ([A-Z][a-z]+)", text):
            eng_word = m.group(1)
            # Check it's not part of a Thai compound (look back for Thai chars)
            start = m.start()
            preceding = text[max(0, start - 5):start]
            if not re.search(r"[\u0E00-\u0E7F]$", preceding.rstrip()):
                warnings.append(f"[{key}] Awkward การ+English: 'การ {eng_word}'")

        # Missing space: Thai→English
        for m in re.finditer(r"[\u0E00-\u0E7F]([A-Za-z]{2,})", text):
            warnings.append(
                f"[{key}] Missing space before '{m.group(1)}' at pos {m.start()}"
            )

        # Missing space: English→Thai
        for m in re.finditer(r"([A-Za-z]{2,})[\u0E00-\u0E7F]", text):
            warnings.append(
                f"[{key}] Missing space after '{m.group(1)}' at pos {m.start()}"
            )

    return errors, warnings



def main():
    _common.run_cli(validate)


if __name__ == "__main__":
    main()
