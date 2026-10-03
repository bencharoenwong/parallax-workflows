import importlib.util
import json
from pathlib import Path
import subprocess
import sys


MODULE = Path(__file__).with_name("validate-translation.py")
SPEC = importlib.util.spec_from_file_location("vietnamese_validator", MODULE)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def test_vietnamese_source_gate(tmp_path):
    source, output = tmp_path / "source.json", tmp_path / "output.json"
    source.write_text(json.dumps({"ReportText": "ROE may rise from 12.5% to 14.0%."}))
    output.write_text(json.dumps({"metadata": {"translation_locale": "vi-VN"}, "sections": {
        "ReportText": {"vietnamese_translation": "ROE có thể tăng từ 12,5% lên 14,0%."}
    }}, ensure_ascii=False), encoding="utf-8")
    assert validator.validate(str(output), str(source))[0] == []
    result = subprocess.run([sys.executable, str(MODULE), str(output), "--source", str(source)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "semantic review still required" in result.stdout
    output.write_text(output.read_text().replace("14,0%", "40,0%"), encoding="utf-8")
    assert validator.validate(str(output), str(source))[0]


def test_cli_requires_source_or_explicit_style_only(tmp_path):
    output = tmp_path / "output.json"
    output.write_text('{}')
    result = subprocess.run([sys.executable, str(MODULE), str(output)], capture_output=True)
    assert result.returncode != 0


def _style(tmp_path, text):
    output = tmp_path / "output.json"
    output.write_text(json.dumps({"metadata": {"translation_locale": "vi-VN"}, "sections": {
        "ReportText": {"vietnamese_translation": text}}}, ensure_ascii=False), encoding="utf-8")
    return validator.validate(str(output))


def test_english_number_format_in_prose_is_flagged(tmp_path):
    errors, _ = _style(tmp_path, "Doanh thu đạt 1,234.5 tỷ đồng.")
    assert any("English number format" in e for e in errors)


def test_english_decimal_percent_in_prose_is_flagged(tmp_path):
    errors, _ = _style(tmp_path, "Biên lợi nhuận gộp đạt 15.2%.")
    assert any("English decimal" in e for e in errors)


def test_table_rows_may_keep_source_number_format(tmp_path):
    errors, _ = _style(tmp_path, "| Biên lợi nhuận gộp | 15.2% | 1,234.5 |")
    assert not any("English" in e for e in errors)


def test_untranslated_magnitude_word_in_prose_is_flagged(tmp_path):
    errors, _ = _style(tmp_path, "Lợi nhuận đạt 2,1 trillion đồng.")
    assert any("Untranslated magnitude" in e for e in errors)


def test_literal_room_translation_is_flagged(tmp_path):
    errors, _ = _style(tmp_path, "Cổ phiếu đã hết phòng ngoại.")
    assert any("phòng ngoại" in e for e in errors)


def test_broker_only_rating_tier_warns(tmp_path):
    _, warnings = _style(tmp_path, "Parallax xếp hạng KHẢ QUAN cho cổ phiếu này.")
    assert any("KHẢ QUAN" in w for w in warnings)


def test_mixed_nghin_ngan_and_space_before_percent_warn(tmp_path):
    _, warnings = _style(tmp_path, "CASA đạt 186,4 nghìn tỷ đồng; thanh khoản 11,3 ngàn tỷ đồng, tăng 17 %.")
    assert any("nghìn" in w and "ngàn" in w for w in warnings)
    assert any("Space before %" in w for w in warnings)


def test_stray_leading_comma_before_number_is_flagged(tmp_path):
    errors, _ = _style(tmp_path, "Biên lợi nhuận ròng tăng ,5% so với cùng kỳ.")
    assert any("Leading comma" in e for e in errors)


def test_ordinary_list_comma_is_not_flagged(tmp_path):
    errors, _ = _style(tmp_path, "Doanh thu tăng 5%, lợi nhuận tăng 7%, biên lợi nhuận 12,5%.")
    assert not any("Leading comma" in e for e in errors)
