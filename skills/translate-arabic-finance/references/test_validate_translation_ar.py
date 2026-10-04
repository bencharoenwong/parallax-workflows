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


def write_payload(tmp_path, text, market="Saudi Arabia"):
    path = tmp_path / "translated.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"market": market},
                "sections": {
                    "MarketNewsDevText": {"arabic_translation": text},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_detects_doubled_arabic_word(tmp_path):
    path = write_payload(tmp_path, "السوق السوق يرتفع")

    errors, _ = validator.validate(str(path))

    assert any("Doubled Arabic word" in error for error in errors)


def test_no_false_positive_on_adjacent_word_boundary(tmp_path):
    # "خلال الجلسة" ("during the session") — "خلال" ends in "ال" and
    # "الجلسة" starts with "ال" (the definite article). No word is actually
    # repeated; a boundary-blind regex mistakes the shared substring for a
    # doubled word.
    path = write_payload(tmp_path, "تراجع السهم خلال الجلسة بنسبة 1.2%")

    errors, _ = validator.validate(str(path))

    assert not any("Doubled Arabic word" in error for error in errors)


def test_detects_doubled_ascii_word(tmp_path):
    path = write_payload(tmp_path, "ارتفع ROE ROE هذا الربع")

    errors, _ = validator.validate(str(path))

    assert any("Doubled word" in error for error in errors)


def test_detects_wrong_term(tmp_path):
    path = write_payload(tmp_path, "انخفض خطأ التتبع هذا الشهر")

    errors, _ = validator.validate(str(path))

    assert any("Wrong term" in error for error in errors)


def test_detects_mixed_digit_script(tmp_path):
    path = write_payload(tmp_path, "ارتفع السهم 12 نقطة ثم ١٥ نقطة")

    errors, warnings = validator.validate(str(path))

    assert any("Mixed digit script" in warning for warning in warnings)
    assert not any("Mixed digit script" in error for error in errors)


def test_reviewed_arabic_gloss_with_english_identifier_is_allowed(tmp_path):
    path = write_payload(tmp_path, "ارتفعت Sharpe Ratio (نسبة شارب)")
    assert validator.validate(str(path))[0] == []


def test_waive_downgrades_error_and_exit_code(tmp_path):
    path = write_payload(tmp_path, "السوق السوق يرتفع")

    failed = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(path), "--style-only"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    waived = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(path), "--style-only", "--waive", "Doubled Arabic word"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert failed.returncode == 1
    assert waived.returncode == 0
    assert "WAIVED (treated as pass): 1" in waived.stdout
    assert "Doubled Arabic word" in waived.stdout


def test_long_latin_run_scan_is_linear_time(tmp_path):
    import time
    path = write_payload(tmp_path, "a" * 20000 + " عربي")
    start = time.process_time()
    validator.validate(str(path))
    assert time.process_time() - start < 1.0


def test_latin_run_before_script_still_warns(tmp_path):
    path = write_payload(tmp_path, "abcعربي")
    _, warnings = validator.validate(str(path))
    assert any("abc" in w for w in warnings)
