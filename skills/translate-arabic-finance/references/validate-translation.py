#!/usr/bin/env python3
"""
Post-translation quality validator for Arabic (ar-SA) financial translations.
Usage: python3 validate-translation.py <output_file> --source <source_file>
Style only: python3 validate-translation.py <output_file> --style-only

STATUS: the wrong-terms dictionary below is a seed placeholder, not built from
reviewed real-output corrections (see SKILL.md "Open decisions", item 7 and
references/terminology-corrections.md). Populate it once native-reviewed
sample corrections exist.
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


def validate(filepath: str, source_path: str | None = None):
    data, texts, errors, warnings = _common.validate_common(filepath, "ar-SA", source_path)
    if data is None:
        return errors, warnings
    for key, text in texts.items():
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

        # Wrong terms that should stay English (seed list — see file header).
        wrong_terms = {
            "خطأ التتبع": "Tracking Error",
            "نسبة شارب": "Sharpe Ratio",
            "الحصة النشطة": "Active Share",
            "نسبة الإصابة": "Hit Ratio",
        }
        for wrong, correct in wrong_terms.items():
            if wrong in text and correct not in text:
                errors.append(f"[{key}] Wrong term '{wrong}' → should be '{correct}'")

        # Mixed digit script: Western and Eastern Arabic-Indic digits in the same section.
        has_western_digit = bool(re.search(r"[0-9]", text))
        has_eastern_digit = any(ch in text for ch in _EASTERN_DIGITS)
        if has_western_digit and has_eastern_digit:
            warnings.append(f"[{key}] Mixed digit script: review against the source; preserve source numerals")

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



def main():
    _common.run_cli(validate)


if __name__ == "__main__":
    main()
