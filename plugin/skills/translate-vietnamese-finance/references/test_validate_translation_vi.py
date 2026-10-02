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
        "ReportText": {"vietnamese_translation": "ROE có thể tăng từ 12.5% lên 14.0%."}
    }}, ensure_ascii=False), encoding="utf-8")
    assert validator.validate(str(output), str(source))[0] == []
    result = subprocess.run([sys.executable, str(MODULE), str(output), "--source", str(source)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "semantic review still required" in result.stdout
    output.write_text(output.read_text().replace("14.0%", "40.0%"), encoding="utf-8")
    assert validator.validate(str(output), str(source))[0]


def test_cli_requires_source_or_explicit_style_only(tmp_path):
    output = tmp_path / "output.json"
    output.write_text('{}')
    result = subprocess.run([sys.executable, str(MODULE), str(output)], capture_output=True)
    assert result.returncode != 0
