"""Executable white-label contracts for RM-facing markdown consumers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

_WHITE_LABEL_DIR = Path(__file__).resolve().parent.parent
_SKILLS_ROOT = _WHITE_LABEL_DIR.parents[1]
sys.path.insert(0, str(_WHITE_LABEL_DIR))

from rm_consumer import load_rm_branding_context, render_rm_markdown  # noqa: E402


class _VoiceTrap(Mapping[str, Any]):
    """Mapping that fails if an RM visual consumer requests voice data."""

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> Any:
        if key == "voice":
            raise AssertionError("RM visual consumer accessed voice")
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "voice":
            raise AssertionError("RM visual consumer accessed voice")
        return self._values.get(key, default)


def _branding(reference: str) -> _VoiceTrap:
    return _VoiceTrap(
        {
            "client_name": "Example Advisory",
            "colors": {},
            "logos": {"primary": ""},
            "fonts": {},
            "source": {"reference": reference},
            "error": None,
            "render": {},
        }
    )


@pytest.mark.parametrize("label", ["portfolio review", "desk call list"])
@pytest.mark.parametrize(
    ("reference", "safe_reference", "secret"),
    [
        (
            "https://assets.example.test/brand/deck.pdf?token=do-not-render",
            "https://assets.example.test",
            "do-not-render",
        ),
        ("/private/operator/clients/example/brand.pdf", "brand.pdf", "/private/operator"),
    ],
)
def test_rm_output_uses_only_safe_source_reference(
    label: str,
    reference: str,
    safe_reference: str,
    secret: str,
) -> None:
    output = render_rm_markdown(
        "# Valid RM analysis\n\nSynthetic client result.",
        label,
        branding_loader=lambda: _branding(reference),
    )

    assert safe_reference in output
    assert secret not in output
    assert reference not in output


@pytest.mark.parametrize("label", ["portfolio review", "desk call list"])
def test_rm_visual_consumers_never_access_voice(label: str) -> None:
    context = load_rm_branding_context(
        label,
        branding_loader=lambda: _branding("https://assets.example.test/brand.pdf"),
    )

    assert context.header_lines == ("**Example Advisory** " + label,)
    assert context.about_lines == (
        "Branding: white-label (source: https://assets.example.test)",
    )


@pytest.mark.parametrize(
    ("error", "expected_branding_line"),
    [
        ("yaml_parse_error: synthetic malformed mapping", "Branding: default Parallax (config error)"),
        ("schema_invalid: synthetic missing colors", "Branding: default Parallax (config error)"),
    ],
)
def test_corrupt_branding_preserves_valid_rm_output(
    error: str,
    expected_branding_line: str,
) -> None:
    body = "# Desk Call List\n\nSynthetic ranked client result remains available."

    output = render_rm_markdown(
        body,
        "desk call list",
        branding_loader=lambda: _VoiceTrap(
            {
                "client_name": "",
                "colors": {},
                "logos": {},
                "fonts": {},
                "source": {},
                "error": error,
                "render": {},
            }
        ),
    )

    assert body in output
    assert expected_branding_line in output
    assert "synthetic malformed mapping" not in output
    assert "synthetic missing colors" not in output


def test_unexpected_brand_loader_failure_preserves_valid_rm_output() -> None:
    body = "# Portfolio Review\n\nSynthetic portfolio analysis remains available."

    def fail_loader() -> Mapping[str, Any]:
        raise OSError("/private/operator/config.yaml")

    output = render_rm_markdown(
        body,
        "portfolio review",
        branding_loader=fail_loader,
    )

    assert body in output
    assert "Branding: default Parallax (config error)" in output
    assert "/private/operator" not in output


@pytest.mark.parametrize(
    "logo_url",
    [
        "https://assets.example.test/logo.svg?token=secret",
        "https://user:password@assets.example.test/logo.svg",
        "https://assets.example.test/logo.svg#secret",
    ],
)
def test_rm_header_omits_logo_urls_with_secrets(logo_url: str) -> None:
    branding = _branding("https://assets.example.test/brand.pdf")
    branding._values["logos"] = {"primary": logo_url}

    output = render_rm_markdown(
        "# Synthetic RM analysis",
        "portfolio review",
        branding_loader=lambda: branding,
    )

    assert logo_url not in output
    assert "![Example Advisory]" not in output


def test_actual_corrupt_yaml_loader_preserves_valid_rm_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_module: ModuleType,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("branding: [unterminated", encoding="utf-8")
    monkeypatch.setattr(loader_module, "_CONFIG_PATH", config_path)
    body = "# Portfolio Review\n\nSynthetic portfolio analysis remains available."

    output = render_rm_markdown(
        body,
        "portfolio review",
        branding_loader=loader_module.load_visual_branding,
    )

    assert body in output
    assert "Branding: default Parallax (config error)" in output
    assert "unterminated" not in output


@pytest.mark.parametrize(
    ("skill_name", "label"),
    [
        ("parallax-client-review", "portfolio review"),
        ("parallax-desk-call-list", "desk call list"),
    ],
)
def test_rm_skill_uses_executable_branding_seam(skill_name: str, label: str) -> None:
    skill_text = (_SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")

    assert "load_rm_branding_context" in skill_text
    assert f'load_rm_branding_context("{label}")' in skill_text
