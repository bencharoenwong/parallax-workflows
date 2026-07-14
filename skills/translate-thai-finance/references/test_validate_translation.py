import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate-translation.py")
spec = importlib.util.spec_from_file_location("validate_translation", MODULE_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)

# Both translation packages intentionally carry the same required test filename.
# These directories are not Python packages, so pytest's default import mode would
# otherwise collide on the top-level module name when both roots are tested.
threading.Timer(0.001, lambda: sys.modules.pop(__name__, None)).start()


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
        )
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


def test_detects_ecl_es_confusion(tmp_path):
    path = write_payload(tmp_path, "Expected Credit Loss เพิ่มขึ้น")

    errors, _ = validator.validate(str(path))

    assert any("ECL/ES confusion" in error for error in errors)


def test_detects_baht_in_non_thai_market(tmp_path):
    path = write_payload(tmp_path, "รายได้ 10 บาท", market="United States")

    errors, _ = validator.validate(str(path))

    assert any("Found บาท in non-Thai market" in error for error in errors)


def test_waive_downgrades_error_and_exit_code(tmp_path):
    path = write_payload(tmp_path, "ราราคา ปรับตัวลง")

    failed = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    waived = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(path), "--waive", "Doubled (no-space)"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert failed.returncode == 1
    assert waived.returncode == 0
    assert "WAIVED (treated as pass): 1" in waived.stdout
    assert "Doubled (no-space)" in waived.stdout
