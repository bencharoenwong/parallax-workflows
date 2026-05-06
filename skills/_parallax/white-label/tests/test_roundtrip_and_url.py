"""Save → reload roundtrip + urllib URL-fallback regression tests.

Closes the integration gaps identified by the council audit:
  - Test 1: end-to-end draft → build_config_from_draft → yaml dump → load_client_branding
  - Test 3: urllib fallback path for URL extraction (mocked HTTP, no live network)
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

# Test files use sys.path manipulation; conftest.py loads loader as a module
sys.path.insert(0, str(Path(__file__).parent.parent))

from extract import (  # noqa: E402
    extract_from_pptx,
    extract_from_url,
)


# Load loader.py via conftest's existing pattern
HERE = Path(__file__).parent
LOADER_PATH = HERE.parent / "loader.py"
spec = importlib.util.spec_from_file_location("loader", LOADER_PATH)
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


@pytest.fixture
def sample_pptx(tmp_path):
    from pptx import Presentation

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Test Asset Manager"
    body_shape = slide.shapes.add_textbox(0, 1000000, 5000000, 2000000)
    tf = body_shape.text_frame
    tf.text = "We invest with discipline. We avoid speculation."
    tf.add_paragraph().text = "Quarterly review covers global equities."

    path = tmp_path / "sample.pptx"
    prs.save(str(path))
    return str(path)


# ---------------------------------------------------------------------------
# Test 1: Save → reload roundtrip
# ---------------------------------------------------------------------------


class TestSaveReloadRoundtrip:
    def test_pptx_draft_roundtrips_through_yaml(self, tmp_path, sample_pptx, monkeypatch):
        """Extract → build_config → yaml.dump → load_client_branding preserves data."""
        # 1. Extract
        draft = extract_from_pptx(sample_pptx)

        # 2. Build config
        config = loader.build_config_from_draft(
            draft,
            client_name="Test Asset Manager",
            extracted_by="test@example.com",
        )

        # Required structure present
        assert "metadata" in config
        assert "branding" in config
        assert "confidence_scores" in config
        assert config["voice"] == {"enabled": False}  # voice not extracted in this test

        # 3. Write to tempfile
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))

        # 4. Load via loader (monkeypatch the path)
        monkeypatch.setattr(loader, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(loader, "_SCHEMA", loader._JSONSCHEMA)
        result = loader.load_client_branding()

        # 5. Assert roundtrip integrity
        # Schema validation passed (no schema_invalid error)
        assert result["error"] is None or "logo_missing" in (result["error"] or ""), \
            f"Unexpected error: {result['error']}"

        # Colors round-tripped (PPTX default Office theme has accent1 = #4F81BD)
        assert result["colors"]["primary"] == "#4F81BD"
        assert result["colors"]["background"] == "#FFFFFF"

        # Source type preserved
        assert result["source"]["type"] == "pptx"

        # Voice section preserved (disabled, not extracted)
        assert result["voice"] == {"enabled": False}

        # Multi-source absent (single-source extraction)
        assert result["multi_source"] == {}

    def test_voice_enabled_roundtrips(self, tmp_path, sample_pptx, monkeypatch):
        """Draft with voice section round-trips through yaml without losing fields."""
        draft = extract_from_pptx(sample_pptx)

        # Inject a voice section as Step 1.5 would
        draft["voice"] = {
            "enabled": True,
            "positioning": "Disciplined institutional asset manager.",
            "tone": {
                "register": "formal-institutional",
                "primary_attributes": ["measured", "evidence-led", "client-first"],
                "avoid_attributes": ["hyperbolic"],
            },
            "core_rules": ["Never speculate", "Always cite evidence"],
            "anti_filler": ["leverage", "synergy", "best-in-class"],
            "audience_adaptation": [],
            "channel_notes": [],
            "drafted_vs_sent": [],
            "company_context": "We are a long-only credit and equity manager.",
            "disclaimers": [
                {"jurisdiction": "MAS", "text": "Regulated by MAS.", "placement": "footer"}
            ],
            "source_corpus": {
                "documents": [sample_pptx],
                "word_count": 2500,
                "confidence": 0.85,
                "notes": "",
            },
        }

        config = loader.build_config_from_draft(draft, client_name="Test Co")
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))

        monkeypatch.setattr(loader, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(loader, "_SCHEMA", loader._JSONSCHEMA)
        result = loader.load_client_branding()

        assert result["voice"]["enabled"] is True
        assert result["voice"]["positioning"] == "Disciplined institutional asset manager."
        assert result["voice"]["tone"]["register"] == "formal-institutional"
        assert "measured" in result["voice"]["tone"]["primary_attributes"]
        assert len(result["voice"]["core_rules"]) == 2
        assert len(result["voice"]["anti_filler"]) == 3
        assert result["voice"]["disclaimers"][0]["jurisdiction"] == "MAS"
        assert result["voice"]["source_corpus"]["word_count"] == 2500

    def test_multi_source_roundtrips(self, tmp_path, sample_pptx, monkeypatch):
        """Multi-source draft preserves mismatches/agreements through save+load."""
        draft = extract_from_pptx(sample_pptx)
        draft["multi_source"] = {
            "sources": [
                {"type": "url", "reference": "https://example.com"},
                {"type": "pptx", "reference": sample_pptx},
            ],
            "mismatches": [
                {
                    "field": "fonts.body",
                    "values": [
                        {"source": "https://example.com", "value": "calibri"},
                        {"source": sample_pptx, "value": "cambria"},
                    ],
                }
            ],
            "agreements": [{"field": "colors.primary", "value": "#4F81BD"}],
        }

        config = loader.build_config_from_draft(draft, client_name="Test")
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))

        monkeypatch.setattr(loader, "_CONFIG_PATH", config_path)
        monkeypatch.setattr(loader, "_SCHEMA", loader._JSONSCHEMA)
        result = loader.load_client_branding()

        assert result["multi_source"]["sources"]
        assert len(result["multi_source"]["mismatches"]) == 1
        assert result["multi_source"]["mismatches"][0]["field"] == "fonts.body"
        assert len(result["multi_source"]["agreements"]) == 1


# ---------------------------------------------------------------------------
# Test 3: urllib fallback regression
# ---------------------------------------------------------------------------


# A trimmed but realistic First Plus homepage HTML stub. Pins the expected
# extraction outputs. If the URL extraction logic changes shape, this fixture
# catches the regression.
_FIRST_PLUS_STUB_HTML = b"""
<!DOCTYPE html>
<html>
<head>
<style>
body { background: #FFFFFF; color: #333333; font-family: 'Calibri', sans-serif; }
.brand { color: #5A597A; }
.brand-secondary { color: #5A597A; }
.brand-accent { color: #676C85; }
.heading { color: #5A597A; }
.section { border-color: #5A597A; }
</style>
</head>
<body>
<header>
<img src="https://www.firstplus.com/resources/front/template/first-plus/images/logo.png" alt="First Plus logo">
</header>
<main>
<h1>Unlocking Opportunities With Trust and Expertise In Asia</h1>
<p>We partner with our clients to navigate uncertainty, protect capital, and create lasting value.</p>
<p>Our strategies span credit, equity, and quantitative investments.</p>
<p>We put people first - clients, colleagues, and communities.</p>
</main>
</body>
</html>
"""


class _StubResponse:
    """Minimal stand-in for urllib's HTTPResponse."""
    def __init__(self, body: bytes):
        self._body = body
        self.headers = mock.MagicMock()
        self.headers.get_content_charset = lambda: "utf-8"

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestUrlFallbackRegression:
    def test_urllib_fallback_extracts_first_plus_signature(self, monkeypatch):
        """When defuddle and scrapling both fail, urllib pulls raw HTML and
        the regex extractors find First Plus's brand signature."""
        # Force defuddle to "fail" — replace subprocess.run with a stub that
        # returns non-zero
        from subprocess import CompletedProcess

        def fake_run(*args, **kwargs):
            return CompletedProcess(args, returncode=1, stdout="", stderr="not found")

        # Force scrapling import to fail (it's not installed in this venv anyway)
        # by intercepting urllib instead — that's the path we're testing
        def fake_urlopen(req, timeout=None):
            return _StubResponse(_FIRST_PLUS_STUB_HTML)

        with mock.patch("subprocess.run", fake_run), \
             mock.patch("urllib.request.urlopen", fake_urlopen):
            draft = extract_from_url("https://www.firstplus.com/")

        # Logo extracted (the brand logo, not a strategy image)
        assert "primary" in draft["logos"]
        assert "logo.png" in draft["logos"]["primary"]["url"]

        # Background detected via frequency-based role assignment
        assert draft["colors"].get("background", {}).get("hex") == "#FFFFFF"

        # Text detected as a dark color
        text_color = draft["colors"].get("text", {}).get("hex", "")
        assert text_color.startswith("#"), "text color should be assigned"

        # The dominant brand color (#5A597A appears 5+ times in the stub) is primary
        assert draft["colors"]["primary"]["hex"] == "#5A597A"

        # No error
        assert draft.get("error") is None

    def test_polaris_voice_artifact_validates(self):
        """Test 2: The voice extraction artifact produced from a real 2642-word
        Polaris letter should pass VoiceValidator (corpus size + section
        completeness). Validates that the Step 1.5 prompt produces output the
        downstream consumers will accept."""
        from validator import VoiceValidator

        artifact_path = Path(__file__).parent / "fixtures" / "voice_extraction_polaris_2026-01.yaml"
        assert artifact_path.exists(), "voice extraction artifact missing"

        voice = yaml.safe_load(artifact_path.read_text())

        # The artifact should be a valid populated voice section
        result = VoiceValidator.validate_voice(voice)
        assert result["status"] == "pass", \
            f"Polaris voice artifact failed VoiceValidator: {result}"

        # And the corpus size check should specifically pass (>= 2000 words)
        assert result["checks"]["corpus"]["status"] == "pass"
        assert result["checks"]["corpus"]["word_count"] >= 2000

        # Section completeness should pass (positioning, tone, ≥2 core rules,
        # ≥3 anti-filler, ≥3 primary attributes)
        assert result["checks"]["completeness"]["status"] == "pass"

        # Spot-check a few specific markers that distinguish "specific extraction"
        # from "generic boilerplate":
        assert any("Polaris" in r or "scarcity" in r or "thesis" in r
                   for r in voice["core_rules"]), \
            "core_rules should reference specific Polaris/thesis vocabulary"

        # anti_filler should include institutional-finance buzzwords
        anti_filler_text = " ".join(voice["anti_filler"]).lower()
        assert "best-in-class" in anti_filler_text or "world-class" in anti_filler_text
        assert "leverage" in anti_filler_text

    def test_urllib_fallback_handles_total_network_failure(self, monkeypatch):
        """If everything fails, returns graceful empty draft (no exceptions)."""
        from subprocess import CompletedProcess

        def fake_run(*args, **kwargs):
            return CompletedProcess(args, returncode=1, stdout="")

        def fake_urlopen_fail(req, timeout=None):
            raise OSError("Network unreachable")

        with mock.patch("subprocess.run", fake_run), \
             mock.patch("urllib.request.urlopen", fake_urlopen_fail):
            draft = extract_from_url("https://0.0.0.0/")

        # Graceful degradation: empty colors/logos/fonts but valid structure
        assert "voice_corpus" in draft
        assert draft["voice_corpus"]["word_count"] == 0
        assert draft["source"]["type"] == "url"
