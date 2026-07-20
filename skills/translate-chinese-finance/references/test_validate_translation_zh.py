import importlib.util
import json
import subprocess
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate-translation.py")
spec = importlib.util.spec_from_file_location("validate_translation", MODULE_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


def write_payload(tmp_path, text, locale="zh-CN", market="China"):
    path = tmp_path / f"translated-{locale}.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"translation_locale": locale, "market": market},
                "sections": {
                    "MarketNewsDevText": {"chinese_translation": text},
                },
            },
            ensure_ascii=False,
        )
    )
    return path


def test_detects_doubled_char(tmp_path):
    path = write_payload(tmp_path, "市场的的估值稳定。")

    errors, warnings = validator.validate(str(path))

    assert any("Doubled char" in error for error in errors)
    assert warnings == []


def test_wrong_term_detection_per_locale(tmp_path):
    cn_path = write_payload(tmp_path, "这是牛市情景。", locale="zh-CN")
    tw_path = write_payload(tmp_path, "這是牛市情境。", locale="zh-TW")

    cn_errors, _ = validator.validate(str(cn_path))
    tw_errors, _ = validator.validate(str(tw_path))

    assert any("牛市情景" in error and "乐观情景" in error for error in cn_errors)
    assert any("牛市情境" in error and "樂觀情境" in error for error in tw_errors)


def test_detects_mixed_script(tmp_path):
    path = write_payload(tmp_path, "公司與市场表现稳定。", locale="zh-CN")

    errors, _ = validator.validate(str(path))

    assert any("Traditional chars in zh-CN output" in error for error in errors)


def test_waive_downgrades_error_and_exit_code(tmp_path):
    path = write_payload(tmp_path, "市场的的估值稳定。")

    failed = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    waived = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(path), "--waive", "Doubled char"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert failed.returncode == 1
    assert waived.returncode == 0
    assert "WAIVED (treated as pass): 1" in waived.stdout
    assert "Doubled char" in waived.stdout
