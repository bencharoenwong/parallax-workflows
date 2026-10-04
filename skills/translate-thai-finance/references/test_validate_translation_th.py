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


def write_payload(tmp_path, text, market="Thailand"):
    path = tmp_path / "translated.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"market": market},
                "sections": {
                    "MarketNewsDevText": {"thai_translation": text},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_detects_doubled_thai_word(tmp_path):
    path = write_payload(tmp_path, "ราคา ราคา ปรับขึ้น")

    errors, _ = validator.validate(str(path))

    assert any("Doubled Thai word" in error for error in errors)


def test_detects_no_space_doubling_literal(tmp_path):
    path = write_payload(tmp_path, "ราราคา ปรับตัวลง")

    errors, _ = validator.validate(str(path))

    assert any("Doubled (no-space) word" in error for error in errors)


def test_preserves_genuine_ecl_without_source_blind_rejection(tmp_path):
    path = write_payload(tmp_path, "Expected Credit Loss เพิ่มขึ้น")

    errors, _ = validator.validate(str(path))

    assert not any("ECL/ES confusion" in error for error in errors)


def test_allows_baht_in_non_thai_market_analysis(tmp_path):
    path = write_payload(tmp_path, "รายได้ 10 บาท", market="United States")

    errors, _ = validator.validate(str(path))

    assert not any("Found บาท in non-Thai market" in error for error in errors)


def test_waive_downgrades_error_and_exit_code(tmp_path):
    path = write_payload(tmp_path, "ราราคา ปรับตัวลง")

    failed = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(path), "--style-only"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    waived = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(path), "--style-only", "--waive", "Doubled (no-space)"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert failed.returncode == 1
    assert waived.returncode == 0
    assert "WAIVED (treated as pass): 1" in waived.stdout
    assert "Doubled (no-space)" in waived.stdout


def test_long_latin_run_scan_is_linear_time(tmp_path):
    import time
    path = write_payload(tmp_path, "a" * 20000 + " ไทย")
    start = time.perf_counter()
    validator.validate(str(path))
    assert time.perf_counter() - start < 1.0


def test_latin_run_before_script_still_warns(tmp_path):
    path = write_payload(tmp_path, "abcไทย")
    _, warnings = validator.validate(str(path))
    assert any("abc" in w for w in warnings)
