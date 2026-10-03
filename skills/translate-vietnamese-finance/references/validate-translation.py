#!/usr/bin/env python3
"""Vietnamese finance translation source-fidelity and style validator."""
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


# Hybrid number policy (SKILL.md): prose uses Vietnamese separators and
# magnitude words; table rows ("| ... |") may keep the source form. A single
# "1,234" is not flagged: in Vietnamese it is a valid decimal.
_EN_GROUPED_DECIMAL = re.compile(r"\b\d{1,3}(?:,\d{3})+\.\d+\b")
_EN_MULTI_GROUP = re.compile(r"\b\d{1,3}(?:,\d{3}){2,}\b")
_EN_PERCENT = re.compile(r"\b\d+\.\d{1,2}%")
_EN_MAGNITUDE = re.compile(r"\b(billion|trillion|million)s?\b", re.I)
# "room" (foreign-ownership or credit headroom) is a fixed loanword.
_WRONG_TERMS = {"phòng ngoại": "room ngoại", "phòng tín dụng": "room tín dụng"}
# Local broker tiers with no Parallax equivalent (references/sources.md).
_BROKER_TIERS = re.compile(r"\b(KÉM KHẢ QUAN|KHẢ QUAN)\b")


def _prose(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("|"))


def validate(filepath: str, source_path: str | None = None):
    data, texts, errors, warnings = _common.validate_common(filepath, "vi-VN", source_path)
    if data is None:
        return errors, warnings
    for key, text in texts.items():
        prose = _prose(text)
        for pattern in (_EN_GROUPED_DECIMAL, _EN_MULTI_GROUP):
            for m in pattern.finditer(prose):
                errors.append(f"[{key}] English number format in prose: '{m.group()}' — write 1.234,5")
        for m in _EN_PERCENT.finditer(prose):
            errors.append(f"[{key}] English decimal in prose percent: '{m.group()}' — write 15,2%")
        # A comma straight before a digit with no digit before it (",5%") is a
        # Vietnamese decimal: in vi-VN it reads as 0,5%. Keep the source form.
        for m in re.finditer(r"(?<!\w),\d+", prose):
            errors.append(f"[{key}] Leading comma before a number: '{m.group()}' — write 0,5 or keep the source form exactly")
        for m in _EN_MAGNITUDE.finditer(prose):
            errors.append(f"[{key}] Untranslated magnitude in prose: '{m.group()}' — billion = tỷ, trillion = nghìn tỷ, million = triệu")
        for wrong, right in _WRONG_TERMS.items():
            if wrong in text:
                errors.append(f"[{key}] Wrong term '{wrong}' → '{right}'")
        for m in _BROKER_TIERS.finditer(text):
            warnings.append(f"[{key}] Broker-only rating tier '{m.group()}' — never use for a Parallax rating")
        if "nghìn" in text and "ngàn" in text:
            warnings.append(f"[{key}] Both 'nghìn' and 'ngàn' used — pick one (default nghìn)")
        for m in re.finditer(r"\d %", text):
            warnings.append(f"[{key}] Space before % at pos {m.start()} — write 15,2%")
        for match in re.finditer(r"\b([A-Za-zÀ-ỹ]{2,})\s+\1\b", text, re.I):
            warnings.append(f"[{key}] Possible repeated word: {match.group()}")
        if "P/FCF" in text and "dòng tiền hoạt động" in text and "dòng tiền tự do" not in text:
            warnings.append(f"[{key}] Review P/FCF denominator: free vs operating cash flow")
    return errors, warnings


def main():
    _common.run_cli(validate)


if __name__ == "__main__":
    main()
