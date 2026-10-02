"""Regression cases for the audited source-fidelity failures."""
import importlib.util
from collections import Counter
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("translation_common_test", ROOT / "translation_validate.py")
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)

TEXTS = {"th": "รายได้อาจเพิ่มขึ้น 5%", "zh": "收入可能增長 5%。",
         "ar-SA": "قد ترتفع الإيرادات 5%", "vi-VN": "Doanh thu có thể tăng 5%."}


def documents(tmp_path, lang, text=None, original="Revenue may rise 5%.", extra=None):
    source = {"ReportText": original, "market": "United States", "date": "2026-10-02"}
    source.update(extra or {})
    output = {"metadata": {"market": source["market"], "report_date": source["date"]},
              "sections": {"ReportText": {common.FIELDS[lang]: text or TEXTS[lang]}},
              "data": dict(extra or {})}
    a, b = tmp_path / "source.json", tmp_path / "output.json"
    a.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    b.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")
    return a, b


@pytest.mark.parametrize("lang", common.FIELDS)
def test_complete_translation_preserves_data(tmp_path, lang):
    source, output = documents(tmp_path, lang, extra={"charts": [{"x": 1}], "notes": None})
    _, _, errors, warnings = common.validate_common(str(output), lang, str(source))
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize("lang", common.FIELDS)
@pytest.mark.parametrize("payload", [{}, {"sections": {}}, {"sections": {"ReportText": {}}},
                                     {"sections": {"ReportText": None}}, {"sections": []}, []])
def test_empty_or_malformed_output_cannot_pass(tmp_path, lang, payload):
    path = tmp_path / "output.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert common.validate_common(str(path), lang)[2]


@pytest.mark.parametrize("lang", common.FIELDS)
def test_english_only_output_fails(tmp_path, lang):
    source, output = documents(tmp_path, lang, "Revenue may rise 5%.")
    assert common.validate_common(str(output), lang, str(source))[2]


@pytest.mark.parametrize("lang", common.FIELDS)
def test_changed_number_fails(tmp_path, lang):
    source, output = documents(tmp_path, lang, TEXTS[lang].replace("5%", "50%"))
    errors = common.validate_common(str(output), lang, str(source))[2]
    assert any("Numeric tokens" in e for e in errors)


@pytest.mark.parametrize("lang", common.FIELDS)
def test_omitted_sections_or_null_data_fails(tmp_path, lang):
    source, output = documents(tmp_path, lang, extra={"notes": None})
    payload = json.loads(output.read_text())
    payload["data"].pop("notes")
    output.write_text(json.dumps(payload))
    assert any("notes" in e for e in common.validate_common(str(output), lang, str(source))[2])
    payload["sections"]["ExtraText"] = {common.FIELDS[lang]: TEXTS[lang]}
    output.write_text(json.dumps(payload))
    assert any("coverage" in e for e in common.validate_common(str(output), lang, str(source))[2])


def test_currency_compares_source_not_listing_market(tmp_path):
    source, output = documents(tmp_path, "ar-SA", "الإيرادات SAR 5M", "Saudi revenues SAR 5M")
    assert common.validate_common(str(output), "ar-SA", str(source))[2] == []
    output.write_text(output.read_text().replace("SAR", "USD"))
    assert any("currency identifiers" in e for e in common.validate_common(str(output), "ar-SA", str(source))[2])


def test_billion_to_yi_is_rejected(tmp_path):
    source, output = documents(tmp_path, "zh", "收入 5亿 CNY。", "Revenue 5B CNY.")
    assert any("Magnitude units" in e for e in common.validate_common(str(output), "zh", str(source))[2])


def test_intentional_entities_and_no_translate_blocks(tmp_path):
    source, output = documents(tmp_path, "zh", '<p>收入 5% &amp; 成本。</p><!-- DO NOT TRANSLATE -->A &lt; B<!-- END NO TRANSLATE -->',
                               '<p>Revenue 5% &amp; costs.</p><!-- DO NOT TRANSLATE -->A &lt; B<!-- END NO TRANSLATE -->')
    assert common.validate_common(str(output), "zh", str(source))[2] == []
    output.write_text(output.read_text().replace('A &lt; B', 'A &lt; C'))
    assert any("No-translate" in e for e in common.validate_common(str(output), "zh", str(source))[2])


def test_url_sentence_punctuation_is_not_part_of_url(tmp_path):
    source, output = documents(tmp_path, "zh", "收入 5%。見 https://example.com/report。本分析僅供參考。",
                               "Revenue 5%. See https://example.com/report. Informational only.")
    assert common.validate_common(str(output), "zh", str(source))[2] == []
    output.write_text(output.read_text().replace('example.com', 'changed.com'))
    assert any("Protected tokens" in e for e in common.validate_common(str(output), "zh", str(source))[2])


def test_credit_and_tail_risk_identities_are_separate(tmp_path):
    source, output = documents(tmp_path, "th", "Expected Shortfall เพิ่มขึ้น 5%", "Expected Credit Loss increased 5%")
    assert any("ECL identity" in e for e in common.validate_common(str(output), "th", str(source))[2])
    source, output = documents(tmp_path, "th", "Expected Credit Loss เพิ่มขึ้น 5%", "Expected Credit Loss increased 5%")
    assert common.validate_common(str(output), "th", str(source))[2] == []


def test_credit_abbreviation_can_be_introduced_as_a_gloss(tmp_path):
    source, output = documents(tmp_path, "vi-VN", "ECL (tổn thất tín dụng dự kiến) tăng 5%.", "Expected Credit Loss increased 5%.")
    assert common.validate_common(str(output), "vi-VN", str(source))[2] == []


def test_structural_and_integrity_errors_are_never_waived():
    errors = ["[FATAL] Invalid JSON", "[INTEGRITY] Changed number", "Wrong term"]
    remaining, waived = common.apply_waivers(errors, ["", "Invalid", "Changed", "Wrong term"])
    assert remaining == errors[:2]
    assert waived == errors[2:]


def test_style_only_cannot_claim_source_fidelity(tmp_path):
    _, output = documents(tmp_path, "vi-VN")
    warnings = common.validate_common(str(output), "vi-VN")[3]
    assert any("UNVERIFIED" in warning for warning in warnings)


def test_role_is_not_a_thai_currency_amount(tmp_path):
    source, output = documents(tmp_path, "th", "บทบาทของบริษัทอาจเพิ่มขึ้น 5%", "The company's role may increase 5%")
    assert common.validate_common(str(output), "th", str(source))[2] == []


def test_foreign_currency_and_json_type_change_fail(tmp_path):
    source, output = documents(tmp_path, "vi-VN", "Doanh thu CHF 5M", "Revenue CHF 5M", {"flag": True})
    assert common.validate_common(str(output), "vi-VN", str(source))[2] == []
    payload = json.loads(output.read_text())
    payload["data"]["flag"] = 1
    payload["sections"]["ReportText"][common.FIELDS["vi-VN"]] = "Doanh thu NOK 5M"
    output.write_text(json.dumps(payload))
    errors = common.validate_common(str(output), "vi-VN", str(source))[2]
    assert any("currency identifiers" in e for e in errors)
    assert any("flag" in e for e in errors)


def test_routed_source_accepts_body_and_rejects_header_leak(tmp_path):
    source, output = tmp_path / "source.md", tmp_path / "output.md"
    header = common.ROUTING_HEADER + "\n  target_variant: zh-HK\n---\n\n"
    source.write_text(header + "Revenue may rise 5%.\n\nInformational only.\n")
    output.write_text("收入可能增長 5%。\n\n僅供參考。\n")
    assert common.validate_common(str(output), "zh", str(source))[2] == []
    output.write_text(header + output.read_text())
    assert any("Routing directive leaked" in e for e in common.validate_common(str(output), "zh", str(source))[2])
    source.write_text(common.ROUTING_HEADER + "\nRevenue may rise 5%.")
    assert any("no separator" in e for e in common.validate_common(str(output), "zh", str(source))[2])


@pytest.mark.parametrize("payload", ['{"ReportText":"收入", "ReportText":"別的內容"}',
                                     '{"ReportText":"收入", "value":NaN}',
                                     '{"ReportText":"收入", "value":Infinity}',
                                     '{"ReportText":"收入", "value":1e999}'])
def test_invalid_or_ambiguous_json_is_rejected(tmp_path, payload):
    path = tmp_path / "output.json"
    path.write_text(payload)
    assert common.validate_common(str(path), "zh")[2][0].startswith("[FATAL]")


def test_nested_nontext_source_sections_must_survive(tmp_path):
    source, output = documents(tmp_path, "zh")
    original = {"sections": {"ReportText": "Revenue may rise 5%.", "chart": [1, 2], "note": None}}
    source.write_text(json.dumps(original))
    translated = json.loads(output.read_text())
    translated["data"] = {"sections": {"chart": [1, 2], "note": None}}
    output.write_text(json.dumps(translated))
    assert common.validate_common(str(output), "zh", str(source))[2] == []
    translated["data"]["sections"].pop("note")
    output.write_text(json.dumps(translated))
    assert any("non-text sections" in e for e in common.validate_common(str(output), "zh", str(source))[2])


@pytest.mark.parametrize("lang", ["th", "ar-SA", "vi-VN"])
def test_named_risk_and_factor_substitution_fails(tmp_path, lang):
    source, output = documents(tmp_path, lang, TEXTS[lang] + " Tracking Error; Momentum +0.40; SAP.DE.",
                               "Revenue may rise 5%. Tracking Error; Momentum +0.40; SAP.DE.")
    assert common.validate_common(str(output), lang, str(source))[2] == []
    output.write_text(output.read_text().replace("Tracking Error", "Sharpe Ratio").replace("Momentum", "Value").replace("SAP.DE", "SAP.PA"))
    errors = common.validate_common(str(output), lang, str(source))[2]
    assert any("Named factor or risk" in e for e in errors)
    assert any("Protected tokens" in e for e in errors)


def test_capitalized_ordinary_value_is_translatable(tmp_path):
    source, output = documents(tmp_path, "zh", "價值可能增長 5%。", "Value may rise 5%.")
    assert common.validate_common(str(output), "zh", str(source))[2] == []


# Vietnamese hybrid number policy: prose localizes separators (1.234,5) and
# translates magnitude words without rescaling; tables may keep source form.

def test_vietnamese_prose_may_localize_separators(tmp_path):
    source, output = documents(tmp_path, "vi-VN", "ROE tăng từ 12,5% lên 1.234,5 điểm.",
                               "ROE rose from 12.5% to 1,234.5 points.")
    assert common.validate_common(str(output), "vi-VN", str(source))[2] == []


def test_vietnamese_table_may_keep_source_separators(tmp_path):
    source, output = documents(tmp_path, "vi-VN", "| ROE | 12.5% |", "| ROE | 12.5% |")
    errors = common.validate_common(str(output), "vi-VN", str(source))[2]
    assert not any("Numeric tokens" in e for e in errors)


def test_vietnamese_changed_digits_still_fail_after_separator_swap(tmp_path):
    source, output = documents(tmp_path, "vi-VN", "ROE tăng lên 15,2%.", "ROE rose to 12.5%.")
    assert any("Numeric tokens" in e for e in common.validate_common(str(output), "vi-VN", str(source))[2])


def test_separator_swap_is_vietnamese_only(tmp_path):
    source, output = documents(tmp_path, "zh", "收入可能增長 12,5%。", "Revenue may rise 12.5%.")
    assert any("Numeric tokens" in e for e in common.validate_common(str(output), "zh", str(source))[2])


def test_vietnamese_magnitude_translated_not_rescaled(tmp_path):
    source, output = documents(tmp_path, "vi-VN", "Doanh thu đạt 1,86 nghìn tỷ đồng.",
                               "Revenue reached VND 1.86 trillion.")
    assert common.validate_common(str(output), "vi-VN", str(source))[2] == []
    output.write_text(output.read_text(encoding="utf-8").replace("1,86 nghìn tỷ", "1.860 tỷ"), encoding="utf-8")
    assert common.validate_common(str(output), "vi-VN", str(source))[2]


def test_dong_meaning_consensus_is_not_a_currency(tmp_path):
    source, output = documents(tmp_path, "vi-VN", "Ước tính đồng thuận có thể tăng 5%.",
                               "Consensus estimates may rise 5%.")
    assert common.validate_common(str(output), "vi-VN", str(source))[2] == []


@pytest.mark.parametrize("phrase", ["Cả 5 đồng thuận rằng doanh thu có thể tăng 5%.",
                                    "Năm 2025 đồng thời doanh thu có thể tăng 5%."])
def test_number_before_dong_compound_is_not_a_currency(tmp_path, phrase):
    english = ("All 5 agree revenue may rise 5%." if "thuận" in phrase
               else "In 2025, revenue may also rise 5%.")
    source, output = documents(tmp_path, "vi-VN", phrase, english)
    assert not any("currency identifiers" in e for e in common.validate_common(str(output), "vi-VN", str(source))[2])


def test_vietnamese_four_digit_comma_ambiguity_is_an_accepted_gap(tmp_path):
    """Accepted gap, not a feature: "1,234" is English one thousand or a
    Vietnamese decimal (1.234). The validator cannot tell them apart and
    accepts it as written; a human reviewer checks these in prose."""
    source, output = documents(tmp_path, "vi-VN", "Doanh số có thể tăng 1,234 đơn vị.",
                               "Sales may grow 1,234 units.")
    assert common.validate_common(str(output), "vi-VN", str(source))[2] == []


@pytest.mark.parametrize("text", ["chiếm 15% tỷ trọng", "với 20% tỷ lệ sở hữu", "5 tỷ phú",
                                  "10 triệu chứng", "ถือ 3 พันธบัตร", "5千瓦", "3千克"])
def test_compound_words_are_not_magnitude_units(text):
    assert common._units(text) == Counter()


@pytest.mark.parametrize("text,unit", [("đạt 5 tỷ đồng", "billion"), ("2 nghìn tỷ", "trillion"),
                                       ("3 triệu cổ phiếu", "million"), ("รายได้ 3 พันล้าน", "billion"),
                                       ("收入 5千", "thousand")])
def test_magnitude_units_still_count(text, unit):
    assert common._units(text) == Counter({unit: 1})


@pytest.mark.parametrize("text", ["5 đồng hồ Rolex", "3 đồng đội"])
def test_more_dong_compounds_are_not_currency(text):
    assert common._counts(text, common.CURRENCIES) == Counter()


@pytest.mark.parametrize("lang, text, original", [
    ("th", "เงินบาทอ่อนค่าลง", "The baht weakened."),
    ("zh", "人民币走弱。", "The renminbi weakened."),
    ("th", "เงินยูโรอ่อนค่าลง", "The euro weakened."),
    ("zh", "欧元走弱。", "The euro weakened."),
    ("zh", "营收可能达5十亿元。", "Revenue may reach 5 billion yuan."),
    ("vi-VN", "Đô la Mỹ suy yếu.", "The dollar weakened."),
    ("vi-VN", "Doanh thu 5M đô la Mỹ", "Revenue USD 5M"),
])
def test_translation_may_name_source_currency(tmp_path, lang, text, original):
    source, output = documents(tmp_path, lang, text, original)
    assert common.validate_common(str(output), lang, str(source))[2] == []


def test_currency_substitution_still_fails(tmp_path):
    source, output = documents(tmp_path, "zh", "营收 HKD 5M。", "Revenue USD 5M")
    errors = common.validate_common(str(output), "zh", str(source))[2]
    assert any("currency identifiers" in e for e in errors)


# Currencies the English source names in words are tracked too, so a
# substitution cannot pass just because the source spelled the currency out.
@pytest.mark.parametrize("lang, text, original", [
    ("th", "รายได้ 5 ล้านบาท", "Revenue of 5 million euros"),
    ("zh", "营收5百万港元", "Revenue of 5 million Chinese yuan"),
    ("vi-VN", "Doanh thu 5 triệu đô la Mỹ", "Revenue of 5 million pounds sterling"),
    ("ar-SA", "الإيرادات 5 مليون دولار أمريكي", "Revenue of 5 million Saudi riyals"),
])
def test_named_source_currency_substitution_fails(tmp_path, lang, text, original):
    source, output = documents(tmp_path, lang, text, original)
    errors = common.validate_common(str(output), lang, str(source))[2]
    assert any("currency" in e.lower() for e in errors)


@pytest.mark.parametrize("lang, text, original", [
    ("th", "รายได้ 5 ล้านยูโร", "Revenue of 5 million euros"),
    ("zh", "营收5百万欧元", "Revenue of 5 million euros"),
    ("ar-SA", "الإيرادات 5 مليون يورو", "Revenue of 5 million euros"),
    ("vi-VN", "Doanh thu 5 triệu euro", "Revenue of 5 million euros"),
    ("zh", "营收5百万英镑", "Revenue of 5 million pounds sterling"),
    ("th", "รายได้ 5 ล้านปอนด์", "Revenue of 5 million British pounds"),
    ("vi-VN", "Doanh thu 5 triệu bảng Anh", "Revenue of 5 million pounds sterling"),
    ("zh", "营收5百万日元", "Revenue of 5 million yen"),
    ("th", "รายได้ 5 ล้านเยน", "Revenue of 5 million yen"),
    ("vi-VN", "Doanh thu 5 triệu yên Nhật", "Revenue of 5 million Japanese yen"),
    ("th", "รายได้ 5 ล้านหยวน", "Revenue of 5 million renminbi"),
    ("vi-VN", "Doanh thu 5 triệu nhân dân tệ", "Revenue of 5 million Chinese yuan"),
    ("zh", "营收5百万泰铢", "Revenue of 5 million baht"),
    ("ar-SA", "الإيرادات 5 مليون ريال سعودي", "Revenue of 5 million Saudi riyals"),
    ("zh", "营收5百万港元", "Revenue of 5 million Hong Kong dollars"),
    ("vi-VN", "Doanh thu 5 triệu đô la Mỹ", "Revenue of 5 million US dollars"),
    ("zh", "营收5百万新加坡元", "Revenue of 5 million Singapore dollars"),
    ("th", "รายได้ 5 ล้านวอนเกาหลี", "Revenue of 5 million Korean won"),
    ("vi-VN", "Doanh thu 5 triệu won", "Revenue of 5 million Korean won"),
    ("ar-SA", "الإيرادات 5 مليون دولار", "Revenue of 5 million US dollars"),
    ("zh", "营收5百万里亚尔", "Revenue of 5 million Saudi riyals"),
    ("ar-SA", "الإيرادات 5 مليون يوان صيني", "Revenue of 5 million renminbi"),
    ("zh", "营收5百万卡塔尔里亚尔", "Revenue of 5 million Qatari riyals"),
    ("ar-SA", "الإيرادات 5 مليون جنيه مصري", "Revenue of 5 million Egyptian pounds"),
    ("zh", "欧元区营收增长", "Euro area revenue grew"),
    ("vi-VN", "Doanh thu 5 triệu đồng", "Revenue of 5 million Vietnamese dong"),
])
def test_named_source_currency_rendered_natively_passes(tmp_path, lang, text, original):
    source, output = documents(tmp_path, lang, text, original)
    assert common.validate_common(str(output), lang, str(source))[2] == []


def test_named_currency_aliases_respect_word_boundaries():
    assert common._counts("Hongkong dongle and wonderful euroclear", common.CURRENCIES) == Counter()


# Each case swaps the source currency for another while the output still
# contains a word that shares letters with the source currency's name.
@pytest.mark.parametrize("lang, text, original", [
    ("zh", "营收5百万美元，投资组合多元化", "Revenue CNY 5M"),
    ("zh", "5百万美元，欧元区", "EUR 5M"),
    ("th", "5 ล้านดอลลาร์สหรัฐ ยูโรโซน", "EUR 5M"),
    ("ar-SA", "5 مليون دولار أمريكي في منطقة اليورو", "EUR 5M"),
    ("zh", "营收5百万卡塔尔里亚尔", "Revenue of 5 million Saudi riyals"),
    ("ar-SA", "الإيرادات 5 مليون دولار كندي", "Revenue of 5 million US dollars"),
    ("ar-SA", "الإيرادات 5 مليون دولار، الديوان", "Revenue CNY 5M"),
    ("th", "รายได้ 5 ล้านบาท อ้อนวอน", "Revenue KRW 5M"),
])
def test_ordinary_word_does_not_stand_in_for_source_currency(tmp_path, lang, text, original):
    source, output = documents(tmp_path, lang, text, original)
    errors = common.validate_common(str(output), lang, str(source))[2]
    assert any("currency" in e.lower() for e in errors)


@pytest.mark.parametrize("text", ["The company won the contract.", "We won't cut guidance.",
                                  "5 million riyals", "5 million pounds", "5 million yuan",
                                  "Rủi ro yên tâm"])
def test_ambiguous_names_are_not_currency(text):
    assert common._counts(text, common.CURRENCIES) == Counter()


def test_long_unbroken_token_is_linear_time(tmp_path):
    import time
    token = "a." * 16000  # dotted run with no "@": the slow case
    start = time.perf_counter()
    common._protected(token)
    assert time.perf_counter() - start < 1.0


def test_emails_still_protected():
    assert common._protected("Contact ir@example.com today") == Counter({"ir@example.com": 1})


def test_deeply_nested_json_fails_with_a_fatal_message(tmp_path):
    path = tmp_path / "output.json"
    path.write_text("[" * 1_000_000 + "]" * 1_000_000, encoding="utf-8")
    data, errors = common.read_document(str(path))
    assert data is None
    assert any(e.startswith("[FATAL]") for e in errors)


@pytest.mark.parametrize("token", ["1," * 16000, "1.1 " * 8000, "5x" * 16000], ids=["commas", "spaced", "x-suffix"])
def test_magnitude_scan_is_linear_time(token):
    import time
    start = time.perf_counter()
    common._units(token)
    assert time.perf_counter() - start < 1.0


def test_ticker_scan_is_linear_time():
    import time
    start = time.perf_counter()
    common._protected("A-" * 16000)
    assert time.perf_counter() - start < 1.0


@pytest.mark.parametrize("text,expected", [
    ("Revenue USD 5.2B and 3M", {"billion": 1, "million": 1}),
    ("5x billion", {"billion": 1}), ("1,5 tỷ", {"billion": 1}),
    ("营收50亿元", {"hundred_million": 1}), ("12% tỷ trọng", {}),
])
def test_units_semantics_unchanged(text, expected):
    assert common._units(text) == Counter(expected)


def test_tickers_still_protected():
    assert common._protected("Buy 0700.HK and BRK-B.N") == Counter({"0700.HK": 1, "BRK-B.N": 1})
