#!/usr/bin/env python3
"""
Post-translation quality validator for Thai financial translations.
Usage: python3 validate-translation.py <translated_json_file> [--waive <error-substring> ...]
"""
import json
import re
import sys

# Known no-space intra-word doublings from SKILL.md §10 "Common AI Errors —
# Auto-Fix". The space-requiring regexes below only catch space-separated
# repeats, so these concatenated forms need an explicit literal-substring check.
_SECTION10_DOUBLINGS = ("ราราคา", "คาดว่าว่า", "ที่ที่", "จะจะ", "และและ", "การเสถียรภาพ")


def validate(filepath: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        with open(filepath) as f:
            data = json.load(f)
    except FileNotFoundError:
        errors.append(f"[FATAL] File not found: {filepath}")
        return errors, warnings
    except json.JSONDecodeError as exc:
        errors.append(f"[FATAL] Invalid JSON in {filepath}: {exc}")
        return errors, warnings

    sections = data.get("sections", data)

    for key, section in sections.items():
        if isinstance(section, dict) and "thai_translation" in section:
            text = section["thai_translation"]
        elif isinstance(section, str):
            text = section
        else:
            continue

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

        # ECL/ES confusion
        if "Expected Credit" in text or "ผลขาดทุนด้านเครดิต" in text:
            errors.append(f"[{key}] ECL/ES confusion detected!")

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

        # HTML entities not cleaned
        for ent in ["&lt;", "&gt;", "&amp;", "&quot;"]:
            if ent in text:
                errors.append(f"[{key}] HTML entity not cleaned: {ent}")

        # บาท in non-Thai market reports
        market = data.get("metadata", {}).get("market", "")
        if market and market != "Thailand" and "บาท" in text:
            errors.append(f"[{key}] Found บาท in non-Thai market report ({market})!")

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


def parse_args(argv: list[str]) -> tuple[str | None, list[str]]:
    filepath = None
    waivers: list[str] = []
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--waive":
            if i + 1 >= len(argv):
                print("Usage: python3 validate-translation.py <translated_json_file> [--waive <error-substring> ...]")
                sys.exit(1)
            waivers.append(argv[i + 1])
            i += 2
            continue
        if filepath is None:
            filepath = arg
            i += 1
            continue
        print("Usage: python3 validate-translation.py <translated_json_file> [--waive <error-substring> ...]")
        sys.exit(1)
    return filepath, waivers


def apply_waivers(errors: list[str], waivers: list[str]) -> tuple[list[str], list[str]]:
    unwaived: list[str] = []
    waived: list[str] = []
    for error in errors:
        if any(substring in error for substring in waivers):
            waived.append(error)
        else:
            unwaived.append(error)
    return unwaived, waived


def main():
    filepath, waivers = parse_args(sys.argv)
    if filepath is None:
        print("Usage: python3 validate-translation.py <translated_json_file> [--waive <error-substring> ...]")
        sys.exit(1)

    errors, warnings = validate(filepath)
    errors, waived = apply_waivers(errors, waivers)

    print(f"{'=' * 50}")
    print(f"Validation: {filepath}")
    print(f"{'=' * 50}")
    print(f"ERRORS: {len(errors)}")
    for e in errors:
        print(f"  {e}")
    print(f"\nWAIVED (treated as pass): {len(waived)}")
    for e in waived:
        print(f"  {e}")
    print(f"\nWARNINGS: {len(warnings)}")
    for w in warnings:
        print(f"  {w}")
    print(f"\n{'=' * 50}")

    if errors:
        print("FAILED — fix errors before finalizing")
        sys.exit(1)
    else:
        print("PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
