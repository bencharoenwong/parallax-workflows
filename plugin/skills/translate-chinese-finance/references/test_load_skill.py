import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("chinese_loader_test", ROOT / "load_skill.py")
loader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loader)
NORM_SPEC = importlib.util.spec_from_file_location("chinese_normalizer_test", ROOT / "normalize_runtime.py")
normalizer = importlib.util.module_from_spec(NORM_SPEC)
NORM_SPEC.loader.exec_module(normalizer)


@pytest.mark.parametrize("locale", loader.VALID_LOCALES)
def test_complete_short_prompt_and_safe_replacements(locale, monkeypatch):
    monkeypatch.setenv("CHINESE_SKILL_DIR", str(ROOT.parent))
    prompt = loader.get_prompts(locale)["condensed"]
    assert "Preserve every claim" in prompt
    assert "magnitude unit" in prompt
    assert prompt.endswith("before delivery.")
    d = loader.get_dictionaries(locale)
    assert d["number_units"]["B"] == "B"
    labels = loader.build_label_dict(locale)
    assert labels["ROE"] == "ROE"
    assert labels["Value"] == "Value"
    assert d["hallucination_cell_keywords"] == []


def test_hong_kong_locale_uses_its_own_vocabulary(monkeypatch):
    monkeypatch.setenv("CHINESE_SKILL_DIR", str(ROOT.parent))
    hk, tw = loader.get_dictionaries("zh-HK"), loader.get_dictionaries("zh-TW")
    assert hk["language_code"] == "zh-HK"
    assert hk["financial_metrics"]["P/E"] == "市盈率"
    assert tw["financial_metrics"]["P/E"] == "本益比"


@pytest.mark.parametrize("filename,traditional", [("skill_simplified.md", False), ("skill_traditional.md", True)])
def test_runtime_normalization_is_idempotent(filename, traditional):
    content = (ROOT.parent / filename).read_text()
    assert normalizer.normalize(content, traditional) == content
