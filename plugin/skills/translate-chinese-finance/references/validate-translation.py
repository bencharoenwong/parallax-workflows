#!/usr/bin/env python3
"""
Post-translation quality validator for Chinese financial translations.
Supports both Simplified (zh-CN) and Traditional (zh-TW) output.
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


# Traditional-script characters that should not appear in zh-CN output
TRAD_CHARS = "與為國對發開關這進還過時會經業報場動價務淨證險負資產權潤據從個們來學體點種樣義變應隨處優寫讀強銷維認識計"
# Simplified-script equivalents that should not appear in zh-TW output
SIMP_CHARS = "与为国对发开关这进还过时会经业报场动价务净证险负资产权润据从个们来学体点种样义变应随处优写读强销维认识计"

DOUBLED_CHARS = ["的的", "了了", "是是", "和和", "在在", "有有", "为为", "為為",
                  "与与", "與與", "也也", "都都", "而而", "但但", "就就", "不不"]

# Wrong terms in zh-CN that should appear differently or stay English
WRONG_TERMS_CN = {
    "阿尔法系数": "Alpha",
    "贝塔系数": "Beta",
    "夏普值": "Sharpe Ratio",
    "夏普比率系数": "Sharpe Ratio",
    "牛市情景": "乐观情景",
    "熊市情景": "悲观情景",
    "基础情景": "基准情景",
    "苹果公司股票": "Apple",
    "辉达": "NVIDIA",
    "英伟达股票": "NVIDIA",
}

WRONG_TERMS_TW = {
    "阿爾法係數": "Alpha",
    "貝塔係數": "Beta",
    "夏普值": "Sharpe Ratio",
    "牛市情境": "樂觀情境",
    "熊市情境": "悲觀情境",
    "基礎情境": "基準情境",
    # Local Taiwan-firm rating variants — Parallax uses mainland-style ratings even in zh-TW
    "優於大盤": "跑贏大盤",
    "落後大盤": "跑輸大盤",
    "加碼": "超配",
    "減碼": "低配",
    # Note: 中立 is ambiguous (could mean "Neutral" rating, not Equal Weight) — context-dependent, skip
    # zh-TW finance ratio terms — Simplified versions should not appear in zh-TW
    "市盈率": "本益比",
    "市淨率": "股價淨值比",
    "股本回報率": "股東權益報酬率",
    "資產回報率": "資產報酬率",
    "投資回報率": "投資報酬率",
    "每股收益": "每股盈餘",
    "股息率": "股息殖利率",
}


WRONG_TERMS_HK = {k: v for k, v in WRONG_TERMS_TW.items()
                  if k not in ("市盈率", "市淨率", "股本回報率", "資產回報率",
                               "投資回報率", "每股收益", "股息率")}


def detect_locale(metadata: dict, sample_text: str) -> str:
    """Return 'zh-CN', 'zh-TW', or 'unknown' based on metadata or character heuristics."""
    explicit = metadata.get("translation_locale") or ""
    if not isinstance(explicit, str):
        return "unknown"
    explicit = explicit.lower()
    if explicit in ("zh-cn", "zh_cn"):
        return "zh-CN"
    if explicit in ("zh-tw", "zh_tw"):
        return "zh-TW"
    if explicit in ("zh-hk", "zh_hk"):
        return "zh-HK"
    # Fallback: count characters
    trad_count = sum(1 for c in sample_text if c in TRAD_CHARS)
    simp_count = sum(1 for c in sample_text if c in SIMP_CHARS)
    if trad_count > simp_count * 2:
        return "zh-TW"
    if simp_count > trad_count * 2:
        return "zh-CN"
    return "unknown"


def validate(filepath: str, source_path: str | None = None, locale: str | None = None):
    data, texts, errors, warnings = _common.validate_common(filepath, "zh", source_path)
    if data is None:
        return errors, warnings
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        return errors, warnings
    explicit = metadata.get("translation_locale")
    if locale and explicit and isinstance(explicit, str) and locale.lower().replace("_", "-") != explicit.lower().replace("_", "-"):
        errors.append("[INTEGRITY] Requested locale differs from translation metadata")
    locale = locale or detect_locale(metadata, "".join(texts.values()))
    if locale == "unknown":
        errors.append("[INTEGRITY] Specify translation_locale or --locale for Chinese output")
    wrong_terms = WRONG_TERMS_CN if locale == "zh-CN" else WRONG_TERMS_HK if locale == "zh-HK" else WRONG_TERMS_TW
    for key, text in texts.items():
        # --- ERRORS ---

        # Doubled characters / function words
        for token in DOUBLED_CHARS:
            if token in text:
                errors.append(f"[{key}] Doubled char: '{token}'")

        # Doubled English words (mixed-language content)
        for m in re.finditer(r"\b([A-Za-z]{2,})\b \1\b", text):
            errors.append(f"[{key}] Doubled English word: '{m.group()}'")

        # Mixed script
        if locale == "zh-CN":
            stragglers = [c for c in text if c in TRAD_CHARS]
            if stragglers:
                # report only the first 5 distinct characters
                uniq = list(dict.fromkeys(stragglers))[:5]
                errors.append(
                    f"[{key}] Traditional chars in zh-CN output: {''.join(uniq)}"
                )
        elif locale in ("zh-TW", "zh-HK"):
            stragglers = [c for c in text if c in SIMP_CHARS]
            if stragglers:
                uniq = list(dict.fromkeys(stragglers))[:5]
                errors.append(
                    f"[{key}] Simplified chars in zh-TW output: {''.join(uniq)}"
                )

        # Wrong terms / scenario-label normalization
        for wrong, correct in wrong_terms.items():
            if wrong in text:
                errors.append(f"[{key}] Wrong term '{wrong}' → should be '{correct}'")

        # --- WARNINGS ---

        # Missing space: Chinese→English (any Han char immediately followed by Latin word)
        for m in re.finditer(r"[一-鿿]([A-Za-z]{2,})", text):
            warnings.append(
                f"[{key}] Missing space before '{m.group(1)}' at pos {m.start()}"
            )

        # Missing space: English→Chinese
        for m in re.finditer(r"([A-Za-z]{2,})[一-鿿]", text):
            warnings.append(
                f"[{key}] Missing space after '{m.group(1)}' at pos {m.start()}"
            )

    return errors, warnings



def main():
    _common.run_cli(validate, ("zh-CN", "zh-TW", "zh-HK"))


if __name__ == "__main__":
    main()
