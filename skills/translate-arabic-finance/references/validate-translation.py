#!/usr/bin/env python3
"""
Post-translation quality validator for Arabic (ar-SA) financial translations.
Usage: python3 validate-translation.py <translated_json_file> [--waive <error-substring> ...]

STATUS: the wrong-terms dictionary below is a seed placeholder, not built from
reviewed real-output corrections (see SKILL.md "Open decisions", item 7 and
references/terminology-corrections.md). Populate it once native-reviewed
sample corrections exist.
"""
import json
import re
import sys

# Arabic core block. Covers Arabic letters, Arabic-Indic digits, and Arabic
# punctuation used in financial prose. Does not cover Arabic Supplement or
# Presentation Forms blocks — extend if a real sample needs a character
# outside U+0600-U+06FF. Used only for spacing warnings, where over-matching
# punctuation is harmless.
_ARABIC_BLOCK = r"؀-ۿ"

# Letters only (U+0621 hamza through U+064A ya), excluding punctuation,
# diacritics, and digits. Used for word-boundary checks (doubled-word
# detection) because the definite article "ال" is a common word-ending AND
# word-starting sequence — e.g. "خلال الجلسة" ("during the session") is two
# distinct words that share the substring "ال" across the space. Without a
# real word-boundary assertion, a doubling regex over the full Arabic block
# flags that as a false "doubled word". See test_validate_translation_ar.py
# test_no_false_positive_on_adjacent_word_boundary.
_ARABIC_WORD = r"ء-ي"

# Placeholder — no real observed model errors on file yet for this language
# (contrast with the Thai/Chinese validators, whose lists were built from
# reviewed corrected output). See terminology-corrections.md.
_SEED_DOUBLINGS: tuple[str, ...] = ()

# Eastern Arabic-Indic digits, for the digit-script-consistency check.
_EASTERN_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def validate(filepath: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        errors.append(f"[FATAL] File not found: {filepath}")
        return errors, warnings
    except json.JSONDecodeError as exc:
        errors.append(f"[FATAL] Invalid JSON in {filepath}: {exc}")
        return errors, warnings

    sections = data.get("sections", data)

    for key, section in sections.items():
        if isinstance(section, dict) and "arabic_translation" in section:
            text = section["arabic_translation"]
        elif isinstance(section, str):
            text = section
        else:
            continue

        # --- ERRORS ---

        # Doubled consecutive Arabic words (2+ chars). Word-boundary lookaround
        # required — see _ARABIC_WORD comment above for why.
        for m in re.finditer(rf"(?<![{_ARABIC_WORD}])([{_ARABIC_WORD}]{{2,}}) \1(?![{_ARABIC_WORD}])", text):
            errors.append(f"[{key}] Doubled Arabic word: '{m.group()}'")
        # Doubled consecutive ASCII words (mixed-language content, tickers, terms).
        for m in re.finditer(r"\b([A-Za-z]{2,})\b \1\b", text):
            errors.append(f"[{key}] Doubled word: '{m.group()}'")
        # No-space intra-word doublings, once a real corpus populates the seed list.
        for bad in _SEED_DOUBLINGS:
            if bad in text:
                errors.append(f"[{key}] Doubled (no-space) word: '{bad}'")

        # ECL/ES confusion — same class of error as the Thai validator's guard.
        if "Expected Credit" in text:
            errors.append(f"[{key}] ECL/ES confusion detected — 'Expected Credit' found where Expected Shortfall context is expected!")

        # Wrong terms that should stay English (seed list — see file header).
        wrong_terms = {
            "خطأ التتبع": "Tracking Error",
            "نسبة شارب": "Sharpe Ratio",
            "الحصة النشطة": "Active Share",
            "نسبة الإصابة": "Hit Ratio",
        }
        for wrong, correct in wrong_terms.items():
            if wrong in text:
                errors.append(f"[{key}] Wrong term '{wrong}' → should be '{correct}'")

        # HTML entities not cleaned
        for ent in ["&lt;", "&gt;", "&amp;", "&quot;"]:
            if ent in text:
                errors.append(f"[{key}] HTML entity not cleaned: {ent}")

        # SAR in a non-Saudi market report
        market = data.get("metadata", {}).get("market", "")
        if market and market not in ("Saudi Arabia", "KSA") and "SAR" in text:
            errors.append(f"[{key}] Found SAR in non-Saudi market report ({market})!")

        # Mixed digit script: Western and Eastern Arabic-Indic digits in the same section.
        has_western_digit = bool(re.search(r"[0-9]", text))
        has_eastern_digit = any(ch in text for ch in _EASTERN_DIGITS)
        if has_western_digit and has_eastern_digit:
            errors.append(f"[{key}] Mixed digit script: both Western (0-9) and Eastern Arabic-Indic digits found in the same section")

        # --- WARNINGS ---

        # Missing space: Arabic -> English/number run (bidi-isolation candidate, see structural-preservation.md §10)
        for m in re.finditer(rf"[{_ARABIC_BLOCK}]([A-Za-z]{{2,}})", text):
            warnings.append(
                f"[{key}] Missing space before '{m.group(1)}' at pos {m.start()} — check bidi isolation too"
            )

        # Missing space: English/number run -> Arabic
        for m in re.finditer(rf"([A-Za-z]{{2,}})[{_ARABIC_BLOCK}]", text):
            warnings.append(
                f"[{key}] Missing space after '{m.group(1)}' at pos {m.start()} — check bidi isolation too"
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
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

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
