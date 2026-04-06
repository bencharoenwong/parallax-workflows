#!/usr/bin/env python3
"""
Post-translation quality validator for Thai financial translations.
Usage: python3 validate-translation.py <translated_json_file>
"""
import json
import re
import sys


def validate(filepath: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    with open(filepath) as f:
        data = json.load(f)

    sections = data.get("sections", data)

    for key, section in sections.items():
        if isinstance(section, dict) and "thai_translation" in section:
            text = section["thai_translation"]
        elif isinstance(section, str):
            text = section
        else:
            continue

        # --- ERRORS ---

        # Doubled consecutive Thai words (2+ chars)
        for m in re.finditer(r"(\b\w{2,}\b) \1", text):
            errors.append(f"[{key}] Doubled word: '{m.group()}'")

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


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate-translation.py <translated_json_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    errors, warnings = validate(filepath)

    print(f"{'=' * 50}")
    print(f"Validation: {filepath}")
    print(f"{'=' * 50}")
    print(f"ERRORS: {len(errors)}")
    for e in errors:
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
