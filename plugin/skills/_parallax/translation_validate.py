"""Shared source-fidelity checks for standalone finance translation skills.

Distribution: plugin includes this module under _parallax; .skill packages
vendor the same file beside their validator. No model context is needed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys


FIELDS = {"th": "thai_translation", "zh": "chinese_translation",
          "ar-SA": "arabic_translation", "vi-VN": "vietnamese_translation"}
SCRIPTS = {"th": r"[\u0e01-\u0e5b]", "zh": r"[\u3400-\u9fff]",
           "ar-SA": r"[\u0621-\u064a]",
           "vi-VN": r"[ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúýĂăĐđĨĩŨũƠơƯư\u1ea0-\u1ef9]|(?i:\b(?:doanh thu|kinh doanh)\b)"}
NUMBER = r"(?<![\d.])[-+−]?(?:\d+(?:[.,]\d+)*|\.\d+)(?:%|x)?"
PROTECTED = re.compile(
    r"https?://[^\s<>\"\)。，；！？：「」『』（）]+|\b[\w.+-]{1,64}@[\w.-]{1,253}\.[A-Za-z]{2,24}\b|"
    r"\b[A-Z0-9-]{1,24}\.(?:O|N|HK|TW|SS|SZ|KS|AX|TO|L|PA|DE|SI|BK|T|BO|NS|SA|MX|JK|KL|PS|MI|MC|AS|SW|ST|OL|CO|HE)\b|"
    r"\{\{[^{}\n]+\}\}|\$\{[^{}\n]+\}|\{[A-Za-z_0-9]+\}|%[sdf]|"
    r"\[\d+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰†‡]"
)
# Two adjacent Latin words. The lookbehind tries only word starts, so a long
# letter run is scanned once instead of once per position.
COPIED_PROSE = re.compile(r"(?<![A-Za-z])[A-Za-z]{3,}\s+[A-Za-z]{3}")
METRICS = re.compile(r"(?<![A-Za-z])(?:P/FCF|EV/EBITDA|EV/Revenue|P/E|P/B|P/S|"
                     r"ROE|ROA|ROIC|EPS|EBITDA|ECL|CVaR|VaR|ES)(?![A-Za-z])")
NAMED_FACTORS = re.compile(r"\b(?:Momentum|Quality|Value|Growth|Size|Volatility)\b")
RISK_NAMES = re.compile(r"\b(?:Tracking Error|Sharpe Ratio|Sortino Ratio|Information Ratio|Maximum Drawdown)\b")
ROUTING_HEADER = "ROUTING DIRECTIVE — DO NOT TRANSLATE OR ECHO THIS BLOCK:"
CURRENCIES = {
    "USD": ("USD", "US$", "美元", "ดอลลาร์สหรัฐ", "دولار أمريكي", "đô la Mỹ", "Đô la Mỹ"),
    "HKD": ("HKD", "HK$", "港元", "港币", "港幣"),
    "CNY": ("CNY", "RMB", "人民币", "人民幣"),
    "TWD": ("TWD", "新台币", "新臺幣", "新台幣"),
    "JPY": ("JPY", "日元", "日圓"), "KRW": ("KRW", "韩元", "韓元"),
    "THB": ("THB", "บาท"), "SAR": ("SAR", "ريال سعودي", "ريالات سعودية"),
    "VND": ("VND", "VNĐ", "đồng Việt Nam", "đồng"),
    "CAD": ("CAD", "C$"), "AUD": ("AUD", "A$"),
    "EUR": ("EUR", "€"), "GBP": ("GBP", "£"),
    "SGD": ("SGD", "S$"), "AED": ("AED",), "KWD": ("KWD",),
    "UNSPECIFIED_DOLLAR": ("$",), "YEN_OR_YUAN": ("¥", "￥"),
}
# Spelled-out currency names are too ambiguous to match; they only warn.
CURRENCY_WORDS = re.compile(
    r"\b(?:dollars?|euros?|pounds?|yen|yuan|renminbi|baht|riyals?|dirhams?|dinars?|"
    r"rupees?|ringgit|rupiah|pesos?|francs?|krona|krone)\b", re.I)
CURRENCY_WORDS_WARNING = ("Source names a currency in words; currency fidelity for spelled-out "
                          "currencies is not checked automatically — compare it manually")
for _code in ("CHF", "NOK", "SEK", "DKK", "INR", "IDR", "MYR", "PHP", "BRL",
              "ZAR", "MXN", "TRY", "PLN", "ILS", "CLP", "NZD", "QAR", "BHD",
              "OMR", "EGP", "COP", "PEN", "ARS", "ISK", "HUF", "CZK", "RON",
              "UAH", "RUB"):
    CURRENCIES[_code] = (_code,)
UNITS = {
    "billion": ("billion", "billions", "B", "十亿", "十億", "พันล้าน", "مليار", "tỷ"),
    "million": ("million", "millions", "M", "百万", "百萬", "ล้าน", "مليون", "ملايين", "الملايين", "triệu"),
    "thousand": ("thousand", "thousands", "K", "千", "พัน", "ألف", "آلاف", "الآلاف", "ألوف", "nghìn"),
    "trillion": ("trillion", "trillions", "T", "万亿", "萬億", "兆", "ล้านล้าน", "تريليون", "nghìn tỷ"),
    "hundred_million": ("亿", "億"),
}


# A magnitude word that also starts an ordinary compound: "15% tỷ trọng" is a
# 15% share, "3 พันธบัตร" is 3 bonds, "5千瓦" is 5 kilowatts.
_UNIT_COMPOUNDS = {
    "tỷ": r"(?!\s*(?:lệ|trọng|suất|phú|giá|số)\b)",
    "triệu": r"(?!\s*chứng\b)",
    "พัน": r"(?!ธ)",
    "千": r"(?![瓦克米])",
}


def _literal_pattern(value: str) -> str:
    """ASCII identifiers need boundaries; Han/Thai suffixes attach to numbers."""
    escaped = re.escape(value)
    if value in _UNIT_COMPOUNDS:
        return escaped + _UNIT_COMPOUNDS[value]
    if value == "บาท":
        return r"(?<!บท)บาท"  # บทบาท means "role", not a baht amount.
    if value == "đồng":
        # A VND amount only after a number or magnitude word ("36.400 đồng",
        # "1,86 nghìn tỷ đồng"); "đồng thuận" means consensus, not currency.
        # Common "đồng" compounds ("đồng thuận" = agree, "đồng thời" = at the
        # same time) are excluded even after a number ("cả 5 đồng thuận").
        return (r"(?:(?<=\d )|(?<=\d)|(?<=tỷ )|(?<=triệu )|(?<=nghìn ))đồng"
                r"(?!\s+(?:thuận|thời|ý|loạt|bộ|nghĩa|hành|đều|minh|nhất|tình|lòng|nghiệp|dạng|tâm|chí|hồ|đội|phục|bằng|cảm)\b)")
    if value.isascii() and value.replace("$", "").isalpha():
        return rf"(?<![A-Za-z]){escaped}(?![A-Za-z])"
    return escaped


def _counts(text: str, aliases: dict) -> Counter:
    pairs = sorted(((v, k) for k, vs in aliases.items() for v in vs),
                   key=lambda pair: len(pair[0]), reverse=True)
    pattern = re.compile("|".join(f"({_literal_pattern(v)})" for v, _ in pairs))
    return Counter(pairs[m.lastindex - 1][1] for m in pattern.finditer(text))


def _protected(text: str) -> Counter:
    # Sentence punctuation is not part of a bare URL; CJK punctuation ends its run.
    return Counter(token.rstrip(".,;!?") if token.startswith(("http://", "https://")) else token
                   for token in PROTECTED.findall(text))


def _units(text: str) -> Counter:
    pairs = sorted(((v, k) for k, vs in UNITS.items() for v in vs),
                   key=lambda pair: len(pair[0]), reverse=True)
    units = "|".join(f"({_literal_pattern(v)})" for v, _ in pairs)
    # Optional currency between a number and its magnitude unit. Each number
    # is found once and the unit is tested where it ends; a single combined
    # regex backtracks through every digit group on long digit runs
    # (quadratic time on input such as "1,1,1,...").
    unit_after = re.compile(rf"\s*(?:(?:[A-Z]{{3}})\s*)?(?:{units})")
    found = Counter()
    for number in re.finditer(NUMBER, text):
        m = unit_after.match(text, number.end())
        if m:
            found[pairs[m.lastindex - 1][1]] += 1
    return found


class _Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.structure = []

    def handle_starttag(self, tag, attrs):
        self.structure.append(("start", tag, tuple((k, v) for k, v in attrs if k not in ("alt", "title"))))

    def handle_startendtag(self, tag, attrs):
        self.structure.append(("empty", tag, tuple((k, v) for k, v in attrs if k not in ("alt", "title"))))

    def handle_endtag(self, tag):
        self.structure.append(("end", tag))

    def handle_comment(self, data):
        self.structure.append(("comment", data))


def _markup(text: str) -> list:
    parser = _Markup()
    parser.feed(text)
    return parser.structure


def _same_data(left, right) -> bool:
    # Python equality conflates True with 1 and 1 with 1.0; JSON types matter.
    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(right, sort_keys=True, ensure_ascii=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite JSON number: {value}")
    return number


def read_document(filepath: str, *, source=False) -> tuple[dict | None, list[str]]:
    try:
        path = Path(filepath)
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            data = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant,
                              parse_float=_finite_float)
        else:
            if source and text.startswith(ROUTING_HEADER):
                match = re.match(re.escape(ROUTING_HEADER) + r"[^\r\n]*\r?\n.*?^---[ \t]*\r?\n", text, re.S | re.M)
                if not match:
                    raise ValueError("Routing directive has no separator")
                text = text[match.end():].lstrip("\r\n")
            data = {"ReportText": text}
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        return None, [f"[FATAL] Cannot read {filepath}: {exc}"]
    if not isinstance(data, dict):
        return None, ["[FATAL] Document must be an object"]
    return data, []


def translated_sections(data: dict, lang: str) -> tuple[dict[str, str], list[str]]:
    errors, out = [], {}
    sections = data.get("sections", data)
    if not isinstance(sections, dict):
        return {}, ["[FATAL] sections must be an object"]
    for key, value in sections.items():
        if key == "metadata" or key == "data":
            continue
        if isinstance(value, dict) and FIELDS[lang] in value:
            if value.get("original_key", key) != key:
                errors.append(f"[INTEGRITY] [{key}] original_key does not match section key")
            value = value[FIELDS[lang]]
        elif not isinstance(value, str):
            if "sections" in data or key.endswith("Text"):
                errors.append(f"[INTEGRITY] [{key}] Missing translation field {FIELDS[lang]}")
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(f"[INTEGRITY] [{key}] Translation must be a nonempty string")
            continue
        out[key] = value
        if ROUTING_HEADER in value:
            errors.append(f"[INTEGRITY] [{key}] Routing directive leaked into translation")
        if not re.search(SCRIPTS[lang], value):
            errors.append(f"[INTEGRITY] [{key}] No target-language text")
    if not out:
        errors.append("[FATAL] No translated sections")
    return out, errors


def source_sections(data: dict) -> dict[str, str]:
    sections = data.get("sections", data)
    if not isinstance(sections, dict):
        return {}
    return {k: v for k, v in sections.items()
            if isinstance(v, str) and ("sections" in data or k.endswith("Text"))}


_SEPARATOR_SWAP = str.maketrans(".,", ",.")


def _numbers_differ(before: str, after: str, lang: str) -> bool:
    """Compare numeric tokens. Vietnamese prose may localize separators
    (12.5% -> 12,5%; 1,234.5 -> 1.234,5) while tables keep the source form, so
    for vi-VN a translated token matches its source as written or swapped.
    Digits, signs, and order of magnitude must still match."""
    left = Counter(re.findall(NUMBER, before))
    right = re.findall(NUMBER, after)
    if lang != "vi-VN":
        return left != Counter(right)
    for token in right:
        for candidate in (token, token.translate(_SEPARATOR_SWAP)):
            if left[candidate] > 0:
                left[candidate] -= 1
                break
        else:
            return True
    return +left != Counter()


_NT_START, _NT_END = "<!-- DO NOT TRANSLATE -->", "<!-- END NO TRANSLATE -->"


def _no_translate_blocks(text: str) -> list[str]:
    """Each start marker through the next end marker, found with str.find so
    many unclosed start markers stay linear (a non-greedy regex rescans)."""
    blocks, pos = [], 0
    while (start := text.find(_NT_START, pos)) != -1:
        end = text.find(_NT_END, start + len(_NT_START))
        if end == -1:
            break
        end += len(_NT_END)
        blocks.append(text[start:end])
        pos = end
    return blocks


def fidelity(source: dict, output: dict, translations: dict[str, str], lang: str = "zh") -> list[str]:
    errors = []
    originals = source_sections(source)
    if not originals:
        return ["[FATAL] Source has no text sections"]
    if originals.keys() != translations.keys():
        errors.append("[INTEGRITY] Section coverage differs from source: "
                      f"missing={sorted(originals.keys() - translations.keys())}, "
                      f"extra={sorted(translations.keys() - originals.keys())}")
    for key in originals.keys() & translations.keys():
        before, after = originals[key], translations[key]
        if before.strip() == after.strip() and COPIED_PROSE.search(before):
            errors.append(f"[INTEGRITY] [{key}] Source prose was copied without translation")
        if _numbers_differ(before, after, lang):
            errors.append(f"[INTEGRITY] [{key}] Numeric tokens differ from source")
        if _counts(before, CURRENCIES) - _counts(after, CURRENCIES):
            errors.append(f"[INTEGRITY] [{key}] Source currency identifiers missing or changed in translation")
        for label, left, right in (
            ("Magnitude units", _units(before), _units(after)),
            ("Protected tokens", _protected(before), _protected(after)),
            ("HTML structure", _markup(before), _markup(after)),
            ("HTML entities", Counter(re.findall(r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z]+);", before)),
             Counter(re.findall(r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z]+);", after))),
            ("Paragraph boundaries", before.count("\n\n"), after.count("\n\n")),
        ):
            if left != right:
                errors.append(f"[INTEGRITY] [{key}] {label} differ from source")
        if Counter(METRICS.findall(before)) - Counter(METRICS.findall(after)):
            errors.append(f"[INTEGRITY] [{key}] Source financial identifiers missing from translation")
        # Capitalized ordinary prose (e.g. "Value rose") need not be a factor label.
        identifiers = Counter(m.group() for m in NAMED_FACTORS.finditer(before)
                              if re.match(r"\s*(?:factor\b|[-+−]?\d)", before[m.end():]))
        retained = Counter(NAMED_FACTORS.findall(after))
        if lang != "zh":
            identifiers.update(RISK_NAMES.findall(before))
            retained.update(RISK_NAMES.findall(after))
        if identifiers - retained:
            errors.append(f"[INTEGRITY] [{key}] Named factor or risk identifiers missing from translation")
        # Literal no-translate blocks are protected as a whole, not merely their comments.
        blocks = _no_translate_blocks(before)
        if any(block not in after for block in blocks):
            errors.append(f"[INTEGRITY] [{key}] No-translate block changed")
        for concept, pattern in (
            ("ECL", r"\bECL\b|Expected Credit Loss(?:es)?|ผลขาดทุนด้านเครดิต|خسائر ائتمانية متوقعة|الخسائر الائتمانية المتوقعة|tổn thất tín dụng dự kiến"),
            ("ES", r"\bES\b|\bCVaR\b|Expected Shortfall"),
        ):
            if re.search(pattern, before, re.I) and not re.search(pattern, after, re.I):
                errors.append(f"[INTEGRITY] [{key}] {concept} identity missing or changed")
    metadata = output.get("metadata", {})
    if not isinstance(metadata, dict):
        return errors + ["[FATAL] metadata must be an object"]
    for key, value in source.get("metadata", {}).items():
        if key not in metadata or not _same_data(metadata[key], value):
            errors.append(f"[INTEGRITY] Source metadata {key} changed or missing")
    passthrough = output.get("data", {})
    if not isinstance(passthrough, dict):
        return errors + ["[FATAL] data must be an object"]
    nested_data = {k: v for k, v in source.get("sections", {}).items() if not isinstance(v, str)} if isinstance(source.get("sections"), dict) else {}
    if nested_data:
        retained = passthrough.get("sections", {})
        if not isinstance(retained, dict) or any(k not in retained or not _same_data(v, retained[k]) for k, v in nested_data.items()):
            errors.append("[INTEGRITY] Source non-text sections changed or missing from data.sections")
    for key, value in source.items():
        if key in originals or key in ("sections", "metadata"):
            continue
        dest = "report_date" if key == "date" else key
        container = metadata if key in ("market", "date") else passthrough if key in passthrough else output
        if dest not in container or not _same_data(container[dest], value):
            errors.append(f"[INTEGRITY] Source data {key} changed or missing")
    return errors


def validate_common(filepath: str, lang: str, source_path: str | None = None):
    data, errors = read_document(filepath)
    if data is None:
        return None, {}, errors, []
    if not isinstance(data.get("metadata", {}), dict):
        return data, {}, ["[FATAL] metadata must be an object"], []
    locale = data.get("metadata", {}).get("translation_locale")
    supported = {"th": ("th", "th-TH"), "zh": ("zh-CN", "zh-TW", "zh-HK"),
                 "ar-SA": ("ar-SA",), "vi-VN": ("vi-VN",)}
    if locale is not None and (not isinstance(locale, str) or
                              locale.lower().replace("_", "-") not in [x.lower() for x in supported[lang]]):
        errors.append(f"[INTEGRITY] Unsupported translation_locale: {locale!r}")
    texts, issues = translated_sections(data, lang)
    errors.extend(issues)
    warnings = []
    if source_path:
        source, issues = read_document(source_path, source=True)
        errors.extend(issues)
        if source is not None:
            if not isinstance(source.get("metadata", {}), dict):
                errors.append("[FATAL] Source metadata must be an object")
            else:
                errors.extend(fidelity(source, data, texts, lang))
                if any(CURRENCY_WORDS.search(text) for text in source_sections(source).values()):
                    warnings.append(CURRENCY_WORDS_WARNING)
    else:
        warnings.append("Source fidelity UNVERIFIED; style checks only")
    return data, texts, errors, warnings


def apply_waivers(errors: list[str], waivers: list[str]):
    waived, remaining = [], []
    for error in errors:
        if not error.startswith(("[FATAL]", "[INTEGRITY]")) and any(w.strip() and w in error for w in waivers):
            waived.append(error)
        else:
            remaining.append(error)
    return remaining, waived


def run_cli(validate, locales=()):
    parser = argparse.ArgumentParser(description="Finance translation source-fidelity and style gate")
    parser.add_argument("output")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", help="Original JSON or plain text/markdown/HTML")
    mode.add_argument("--style-only", action="store_true", help="Not a delivery approval")
    parser.add_argument("--waive", action="append", default=[])
    if locales:
        parser.add_argument("--locale", choices=locales)
    args = parser.parse_args()
    kwargs = {"source_path": args.source}
    if locales:
        kwargs["locale"] = args.locale
    errors, warnings = validate(args.output, **kwargs)
    errors, waived = apply_waivers(errors, args.waive)
    print(f"ERRORS: {len(errors)}")
    for item in errors:
        print(item)
    print(f"WAIVED (treated as pass): {len(waived)}")
    for item in waived:
        print(item)
    for item in warnings:
        print(f"WARNING: {item}")
    print("FAILED" if errors else "STYLE CHECK PASSED — source fidelity UNVERIFIED" if args.style_only else "FIDELITY AND STYLE CHECKS PASSED — semantic review still required")
    sys.exit(1 if errors else 0)
