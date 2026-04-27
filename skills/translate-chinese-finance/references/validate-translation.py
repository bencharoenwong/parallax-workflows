#!/usr/bin/env python3
"""
Post-translation quality validator for Chinese financial translations.
Supports both Simplified (zh-CN) and Traditional (zh-TW) output.
Usage: python3 validate-translation.py <translated_json_file>
"""
import json
import re
import sys

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


def detect_locale(metadata: dict, sample_text: str) -> str:
    """Return 'zh-CN', 'zh-TW', or 'unknown' based on metadata or character heuristics."""
    explicit = (metadata.get("translation_locale") or "").lower()
    if explicit in ("zh-cn", "zh_cn"):
        return "zh-CN"
    if explicit in ("zh-tw", "zh_tw", "zh-hk", "zh_hk"):
        return "zh-TW"
    # Fallback: count characters
    trad_count = sum(1 for c in sample_text if c in TRAD_CHARS)
    simp_count = sum(1 for c in sample_text if c in SIMP_CHARS)
    if trad_count > simp_count * 2:
        return "zh-TW"
    if simp_count > trad_count * 2:
        return "zh-CN"
    return "unknown"


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
    metadata = data.get("metadata", {})

    # Concatenate text for locale detection
    sample = ""
    for section in sections.values():
        if isinstance(section, dict):
            sample += section.get("chinese_translation", "")
        elif isinstance(section, str):
            sample += section
        if len(sample) > 2000:
            break

    locale = detect_locale(metadata, sample)
    wrong_terms = WRONG_TERMS_CN if locale == "zh-CN" else WRONG_TERMS_TW

    for key, section in sections.items():
        if isinstance(section, dict) and "chinese_translation" in section:
            text = section["chinese_translation"]
        elif isinstance(section, str):
            text = section
        else:
            continue

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
        elif locale == "zh-TW":
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

        # HTML entity corruption
        for ent in ["&lt;", "&gt;", "&amp;", "&quot;"]:
            if ent in text:
                # only error if NOT inside a code block (heuristic)
                errors.append(f"[{key}] HTML entity not cleaned: {ent}")

        # Currency mismatch with market
        market = metadata.get("market", "")
        if market and market not in ("China", "Mainland China") and (
            "人民币" in text or "人民幣" in text or "RMB" in text
        ):
            warnings.append(
                f"[{key}] Found 人民币/RMB in non-mainland market report ({market})"
            )
        if market and market != "Hong Kong" and "港元" in text:
            warnings.append(
                f"[{key}] Found 港元 in non-HK market report ({market})"
            )

        # Magnitude check: did "B" or "billion" stay as "亿" without the ×10 conversion?
        # Heuristic: number followed by 亿 where the original (English) used B/billion would
        # require multiplication. We can't audit fully without source, but flag suspicious
        # patterns where the same number appears with both "B" and "亿" inconsistently.
        b_matches = re.findall(r"(\d+(?:\.\d+)?)\s*B\b", text)
        yi_matches = re.findall(r"(\d+(?:\.\d+)?)\s*亿", text)
        for b_num in b_matches:
            if b_num in yi_matches:
                warnings.append(
                    f"[{key}] Possible magnitude bug: '{b_num}B' and '{b_num}亿' both present "
                    f"(should be '{b_num}B' = '{float(b_num)*10}亿')"
                )

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
    if len(sys.argv) < 2:
        print("Usage: python3 validate-translation.py <translated_json_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    errors, warnings = validate(filepath)

    print("=" * 50)
    print(f"Validation: {filepath}")
    print("=" * 50)
    print(f"ERRORS: {len(errors)}")
    for e in errors:
        print(f"  {e}")
    print(f"\nWARNINGS: {len(warnings)}")
    for w in warnings:
        print(f"  {w}")
    print("\n" + "=" * 50)

    if errors:
        print("FAILED — fix errors before finalizing")
        sys.exit(1)
    else:
        print("PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
