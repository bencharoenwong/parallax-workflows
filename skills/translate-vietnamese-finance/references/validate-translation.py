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
apply_waivers = _common.apply_waivers


def validate(filepath: str, source_path: str | None = None):
    data, texts, errors, warnings = _common.validate_common(filepath, "vi-VN", source_path)
    if data is None:
        return errors, warnings
    for key, text in texts.items():
        for match in re.finditer(r"\b([A-Za-zÀ-ỹ]{2,})\s+\1\b", text, re.I):
            warnings.append(f"[{key}] Possible repeated word: {match.group()}")
        if "P/FCF" in text and "dòng tiền hoạt động" in text and "dòng tiền tự do" not in text:
            warnings.append(f"[{key}] Review P/FCF denominator: free vs operating cash flow")
    return errors, warnings


def main():
    _common.run_cli(validate)


if __name__ == "__main__":
    main()
