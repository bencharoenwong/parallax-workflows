"""Executable white-label contracts for RM-facing markdown consumers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
import re
import sys
from types import ModuleType
from typing import Any
import unicodedata

import pytest

_WHITE_LABEL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WHITE_LABEL_DIR))

from rm_consumer import (  # noqa: E402
    DEFAULT_AUDIENCE,
    RMBrandingContext,
    load_rm_branding_context,
    render_rm_markdown,
    resolve_audience,
)


#: integration-pattern.md §7 unconditional currency line, hardcoded on purpose:
#: importing rm_consumer's constant here would make the wording assertion
#: tautological. This literal is the byte-for-byte contract.
_CURRENCY_LINE_LITERAL = (
    "Currency: figures as reported by source data; "
    "no base-currency conversion applied."
)


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
        _CURRENCY_LINE_LITERAL,
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


@pytest.mark.parametrize(
    "logo_url",
    [
        "https://cdn.example.test/a)![x](https://evil.test/y.png",
        "https://cdn.example.test/<img src=x onerror=alert(1)>.png",
        "https://cdn.example.test/a b.png",
    ],
)
def test_logo_url_cannot_break_out_of_the_image_destination(logo_url: str) -> None:
    """A logo URL is a link destination, so it is refused rather than flattened.

    Every other interpolated string takes the markdown pass, but rewriting a URL
    would point the image somewhere the operator never configured. The URL
    checks covered credentials, query and fragment only, so a path holding ")"
    closed the templated image early and appended a second, attacker-chosen
    remote image to the deliverable.
    """
    branding = _branding("https://assets.example.test/brand.pdf")
    branding._values["logos"] = {"primary": logo_url}

    output = render_rm_markdown(
        "# Synthetic RM analysis",
        "portfolio review",
        branding_loader=lambda: branding,
    )

    assert "evil.test" not in output
    assert output.count("](") == 0
    assert "<" not in output and ">" not in output
    assert "# Synthetic RM analysis" in output


def test_ordinary_logo_url_still_renders() -> None:
    """The refusal must not drop logos whose filenames are merely punctuated.

    "_", "!", "*" and "|" cannot end a link destination, so refusing them would
    silently drop a legitimate logo instead of a hostile one.
    """
    branding = _branding("https://assets.example.test/brand.pdf")
    branding._values["logos"] = {"primary": "https://cdn.example.test/brand_logo!.png"}

    output = render_rm_markdown(
        "# Synthetic RM analysis",
        "portfolio review",
        branding_loader=lambda: branding,
    )

    assert (
        "![Example Advisory](https://cdn.example.test/brand_logo!.png)"
        in output
    )


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


# --- Regressions from the 2026-08-29 live RM brand-ingest exercise ----------


def _name_region(output: str) -> str:
    """The header lines into which client_name is interpolated."""
    return "\n".join(
        line for line in output.splitlines() if line.startswith(("!", "**"))
    )


def _rm_branding(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "client_name": "Meridian",
        "error": None,
        "colors": {"primary": {"hex": "#14213D"}},
        "fonts": {},
        "logos": {},
        "source": {"type": "folder", "reference": "/tmp/deck.pptx"},
        "render": {},
    }
    base.update(overrides)
    return base


def test_rm_module_loads_without_sys_modules_registration() -> None:
    """rm_consumer must survive the package's own importlib idiom.

    persistence.py::_load_sibling execs a module without registering it in
    sys.modules. Combined with ``from __future__ import annotations``, a
    ``@dataclass`` in the loaded module resolves its string annotations through
    ``sys.modules[__module__]`` and raises AttributeError on Python 3.11.
    """
    import importlib.util

    path = _WHITE_LABEL_DIR / "rm_consumer.py"
    spec = importlib.util.spec_from_file_location("wl_rm_unregistered", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("wl_rm_unregistered", None)
    spec.loader.exec_module(module)  # deliberately left unregistered

    ctx = module.RMBrandingContext(header_lines=("a",), about_lines=("b",))
    assert ctx.header_lines == ("a",)
    assert ctx.about_lines == ("b",)


@pytest.mark.parametrize(
    "hostile_name",
    [
        "Acme](javascript:alert(1))",
        "Acme <img src=x onerror=alert(1)>",
        "Acme\n\n## Injected Heading",
        "Acme `backtick` Co",
        "Acme | Bogus | Row",
        "Acme\\](x)",
        "Acme<script>fetch('//evil')</script>",
    ],
)
def test_client_name_cannot_inject_markdown_or_html(hostile_name: str) -> None:
    """client_name originates in client-supplied collateral and is untrusted."""
    branding = _rm_branding(
        client_name=hostile_name,
        logos={"primary": "https://cdn.example.com/logo.png"},
    )
    output = render_rm_markdown(
        "Body.", "portfolio review", branding_loader=lambda: branding
    )

    region = _name_region(output)
    # The header must still be exactly the two templated lines, with the name
    # occupying the label slot and carrying no markdown/HTML metacharacters.
    image = re.fullmatch(
        r"!\[(?P<name>[^\[\]()<>*_`#!|\\\n]*)\]\(https://cdn\.example\.com/logo\.png\)",
        region.splitlines()[0],
    )
    assert image is not None, f"header broke out of the image template: {region!r}"
    bold = re.fullmatch(
        r"\*\*(?P<name>[^\[\]()<>*_`#!|\\\n]*)\*\* portfolio review",
        region.splitlines()[1],
    )
    assert bold is not None, f"header broke out of the bold template: {region!r}"
    assert image.group("name") == bold.group("name")

    # A hostile name is neutralised by flattening it to inert label text, not by
    # word blacklisting: "onerror" may survive as literal prose, but it can no
    # longer sit inside an HTML tag or a link destination. Assert the construct
    # is dead rather than that the substring is absent.
    assert "<" not in output and ">" not in output
    assert "## Injected Heading" not in output
    assert not re.search(r"\]\(\s*javascript:", output)
    assert output.count("](") == 1  # only the one templated image destination

    # The report body and footer must survive intact.
    assert "Body." in output
    assert "## About This Report" in output


@pytest.mark.parametrize(
    "overrides",
    [
        {"client_name": "Acme\x1b[2K\x1b[1;1HFAKE HEADER\x07 Advisory"},
        {"client_name": "Acme‮gnitekraM‬ Co"},
        {"source": {"type": "folder", "reference": "/tmp/deck\x1b[31m.pptx"}},
        {"logos": {"primary": "/tmp/logo\x07​.png"}},
    ],
)
def test_untrusted_branding_cannot_inject_terminal_control_sequences(
    overrides: dict[str, Any],
) -> None:
    """RM markdown is opened in terminals; invisible characters must not survive.

    str.split collapses whitespace only, so ESC, BEL and bidi overrides used to
    reach the rendered deliverable verbatim from every untrusted field.
    """
    output = render_rm_markdown(
        "Body.",
        "portfolio review",
        branding_loader=lambda: _rm_branding(**overrides),
    )

    invisible = [
        ch for ch in output if unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Co"}
    ]
    assert invisible == ["\n"] * len(invisible), f"invisible characters survived: {output!r}"
    assert "Body." in output
    assert "## About This Report" in output


def test_client_name_is_length_bounded() -> None:
    output = render_rm_markdown(
        "Body.",
        "portfolio review",
        branding_loader=lambda: _rm_branding(client_name="A" * 5000),
    )
    assert len(_name_region(output)) < 400


def test_relative_source_path_is_redacted_to_basename() -> None:
    """Only absolute paths were redacted; relative ones leaked their directory."""
    branding = _rm_branding(
        source={
            "type": "folder",
            "reference": "client-collateral/acme-confidential-deck.pptx",
        }
    )
    output = render_rm_markdown(
        "Body.", "portfolio review", branding_loader=lambda: branding
    )

    assert "client-collateral/" not in output
    assert "acme-confidential-deck.pptx" in output


def test_contentless_branding_does_not_claim_white_label() -> None:
    """Active state with nothing to render must not assert white-label provenance."""
    for branding in ({}, {"error": None}, {"client_name": None, "error": None}):
        ctx = load_rm_branding_context(
            "portfolio review", branding_loader=lambda b=branding: b
        )
        joined = " ".join(ctx.about_lines)
        assert "white-label" not in joined
        assert "default Parallax" in joined
        assert ctx.header_lines == ()


def test_non_mapping_branding_degrades() -> None:
    for junk in (None, "config.yaml", 42, ["a"]):
        ctx = load_rm_branding_context(
            "portfolio review", branding_loader=lambda j=junk: j
        )
        assert ctx.header_lines == ()
        assert "default Parallax" in " ".join(ctx.about_lines)


# --- §13 audience render mode (resolve_audience) ----------------------------


def _CLIENT_SAFE_LINE() -> str:
    return "Audience mode: client-safe"


def test_resolve_audience_defaults_when_flag_and_config_absent() -> None:
    mode, notice = resolve_audience({}, None)
    assert mode == DEFAULT_AUDIENCE == "internal_analyst"
    assert notice is None


def test_resolve_audience_config_client_safe_sets_mode() -> None:
    branding = _rm_branding(render={"audience_default": "client_safe"})
    mode, notice = resolve_audience(branding, None)
    assert mode == "client_safe"
    assert notice is None


@pytest.mark.parametrize(
    ("config_value", "flag_value", "expected"),
    [
        ("client_safe", "internal_analyst", "internal_analyst"),
        ("internal_analyst", "client_safe", "client_safe"),
    ],
)
def test_invocation_flag_overrides_config_in_both_directions(
    config_value: str, flag_value: str, expected: str
) -> None:
    branding = _rm_branding(render={"audience_default": config_value})
    mode, notice = resolve_audience(branding, flag_value)
    assert mode == expected
    assert notice is None


def test_unrecognized_invocation_flag_falls_back_with_notice() -> None:
    branding = _rm_branding(render={"audience_default": "client_safe"})
    mode, notice = resolve_audience(branding, "retail_and_shareable")
    assert mode == DEFAULT_AUDIENCE
    assert notice == "Audience mode: unrecognized value; rendered as internal_analyst"


def test_unrecognized_config_value_falls_back_with_notice() -> None:
    branding = _rm_branding(render={"audience_default": "retail_and_shareable"})
    mode, notice = resolve_audience(branding, None)
    assert mode == DEFAULT_AUDIENCE
    assert notice == "Audience mode: unrecognized value; rendered as internal_analyst"


@pytest.mark.parametrize(
    "overrides",
    [
        {"render": ["client_safe"]},
        {"render": "client_safe"},
        {"render": {"audience_default": 3}},
        {"render": {"audience_default": ["client_safe"]}},
    ],
)
def test_malformed_render_shape_falls_back_with_malformed_notice(
    overrides: dict[str, Any],
) -> None:
    """R6: a present-but-wrong-shaped `render` or `audience_default` is a distinct,
    non-silent failure mode from an absent one — both degrade to the default, but
    only the malformed shape gets a notice."""
    branding = _rm_branding(**overrides)
    mode, notice = resolve_audience(branding, None)
    assert mode == DEFAULT_AUDIENCE
    assert notice == "Audience mode: malformed configuration; rendered as internal_analyst"


@pytest.mark.parametrize(
    "branding",
    [
        {},
        {"render": None},
        {"render": {}},
        {"render": {"audience_default": None}},
    ],
)
def test_absent_render_or_audience_default_falls_back_silently(
    branding: dict[str, Any],
) -> None:
    mode, notice = resolve_audience(branding, None)
    assert mode == DEFAULT_AUDIENCE
    assert notice is None


def test_resolve_audience_non_mapping_branding_degrades_to_flag_or_default() -> None:
    for junk in (None, "config.yaml", 42, ["a"]):
        mode, notice = resolve_audience(junk, None)
        assert mode == DEFAULT_AUDIENCE
        assert notice is None
        mode, notice = resolve_audience(junk, "client_safe")
        assert mode == "client_safe"
        assert notice is None


@pytest.mark.parametrize(
    "hostile",
    [
        "client_safe\x1b[2K\x1b[1;1HFAKE HEADER\x07",
        "DROP TABLE clients; --",
        "](javascript:alert(1))",
    ],
)
def test_audience_notice_never_echoes_the_untrusted_value(hostile: str) -> None:
    """The notice is a fixed, value-free string regardless of what triggered it —
    it must never interpolate the raw flag or config value into client-visible
    text."""
    mode, notice = resolve_audience({}, hostile)
    assert mode == DEFAULT_AUDIENCE
    assert notice == "Audience mode: unrecognized value; rendered as internal_analyst"
    assert hostile not in notice

    branding = _rm_branding(render={"audience_default": hostile})
    mode, notice = resolve_audience(branding, None)
    assert mode == DEFAULT_AUDIENCE
    assert notice == "Audience mode: unrecognized value; rendered as internal_analyst"
    assert hostile not in notice


def test_contentless_branding_still_resolves_audience_from_flag() -> None:
    """Active-but-empty branding must not short-circuit audience resolution."""
    ctx = load_rm_branding_context(
        "portfolio review",
        branding_loader=lambda: {},
        audience="client_safe",
    )
    assert ctx.resolved_audience == "client_safe"
    assert _CLIENT_SAFE_LINE() in ctx.about_lines


def test_loader_failure_still_resolves_audience_from_flag() -> None:
    def fail_loader() -> Mapping[str, Any]:
        raise OSError("/private/operator/config.yaml")

    ctx = load_rm_branding_context(
        "portfolio review", branding_loader=fail_loader, audience="client_safe"
    )
    assert ctx.resolved_audience == "client_safe"
    assert _CLIENT_SAFE_LINE() in ctx.about_lines
    assert "/private/operator" not in " ".join(ctx.about_lines)


def test_non_mapping_branding_resolves_audience_from_flag() -> None:
    ctx = load_rm_branding_context(
        "portfolio review", branding_loader=lambda: ["a"], audience="client_safe"
    )
    assert ctx.resolved_audience == "client_safe"
    assert _CLIENT_SAFE_LINE() in ctx.about_lines
    assert ctx.header_lines == ()


def test_client_safe_mode_line_placed_after_branding_and_logo_lines() -> None:
    """§13.4 ordering: Branding line, any Logo on file: line, notice, mode line —
    the render-gate anchor keys on titles + Branding Header only, so the mode
    line must never precede or displace those lines."""
    branding = _rm_branding(
        logos={"primary": "/private/operator/logo.png"},
        render={"audience_default": "client_safe"},
    )
    ctx = load_rm_branding_context("portfolio review", branding_loader=lambda: branding)

    assert ctx.about_lines[0].startswith("Branding:")
    assert ctx.about_lines[1] == _CURRENCY_LINE_LITERAL
    assert ctx.about_lines[2] == "Logo on file: logo.png"
    assert ctx.about_lines[-1] == _CLIENT_SAFE_LINE()
    # Header lines (the render-gate's Branding Header anchor) are unaffected by
    # audience mode.
    assert ctx.header_lines == ("**Meridian** portfolio review",)


def test_render_rm_markdown_carries_audience_flag_through() -> None:
    branding = _rm_branding()
    output = render_rm_markdown(
        "Body.", "portfolio review", branding_loader=lambda: branding, audience="client_safe"
    )
    assert _CLIENT_SAFE_LINE() in output
    assert output.count(_CLIENT_SAFE_LINE()) == 1


def test_audience_default_mode_renders_no_mode_line() -> None:
    branding = _rm_branding()
    ctx = load_rm_branding_context("portfolio review", branding_loader=lambda: branding)
    assert ctx.resolved_audience == DEFAULT_AUDIENCE
    assert _CLIENT_SAFE_LINE() not in ctx.about_lines


# --- §7 unconditional currency line ------------------------------------------


def test_currency_line_present_on_clean_active_load() -> None:
    ctx = load_rm_branding_context(
        "portfolio review", branding_loader=lambda: _rm_branding()
    )
    assert ctx.about_lines[0].startswith("Branding: white-label")
    assert ctx.about_lines[1] == _CURRENCY_LINE_LITERAL


@pytest.mark.parametrize(
    "branding_loader",
    [
        pytest.param(lambda: {}, id="contentless-active"),
        pytest.param(lambda: ["a"], id="non-mapping"),
        pytest.param(
            lambda: _rm_branding(client_name="", colors={}, error="config_not_found"),
            id="config-not-found",
        ),
        pytest.param(
            lambda: _rm_branding(
                client_name="", colors={}, error="yaml_parse_error: synthetic"
            ),
            id="config-error",
        ),
    ],
)
def test_currency_line_present_on_every_degraded_path(
    branding_loader: Any,
) -> None:
    """§7: the currency line is independent of `white_label_active` and of the
    Branding-line condition — every path renders it, second, after Branding."""
    ctx = load_rm_branding_context("desk call list", branding_loader=branding_loader)
    assert ctx.about_lines[0].startswith("Branding:")
    assert ctx.about_lines[1] == _CURRENCY_LINE_LITERAL
    assert ctx.about_lines.count(_CURRENCY_LINE_LITERAL) == 1


def test_currency_line_present_when_loader_raises() -> None:
    def fail_loader() -> Mapping[str, Any]:
        raise OSError("/private/operator/config.yaml")

    ctx = load_rm_branding_context("portfolio review", branding_loader=fail_loader)
    assert ctx.about_lines == (
        "Branding: default Parallax (config error)",
        _CURRENCY_LINE_LITERAL,
    )


def test_currency_line_full_order_with_logo_and_mode_line() -> None:
    """Full §7 + §13.4 order: Branding, currency, Logo on file, mode line —
    the currency line sits second, before the logo line. A recognized
    invocation flag wins silently, so no notice line can co-occur with the
    mode line (a recognized flag returns before the config is read)."""
    branding = _rm_branding(
        logos={"primary": "/private/operator/logo.png"},
        render={"audience_default": "retail_and_shareable"},
    )
    ctx = load_rm_branding_context(
        "portfolio review",
        branding_loader=lambda: branding,
        audience="client_safe",
    )
    assert ctx.about_lines == (
        "Branding: white-label (source: deck.pptx)",
        _CURRENCY_LINE_LITERAL,
        "Logo on file: logo.png",
        "Audience mode: client-safe",
    )


def test_currency_line_full_order_with_logo_and_audience_notice() -> None:
    """§7 order on the notice branch: Branding, currency, Logo on file,
    resolve_audience notice — active branding with an abs-local logo plus an
    unrecognized config `audience_default` and no invocation flag. The
    currency line still sits second, before the logo line and the notice."""
    branding = _rm_branding(
        logos={"primary": "/private/operator/logo.png"},
        render={"audience_default": "retail_and_shareable"},
    )
    ctx = load_rm_branding_context(
        "portfolio review", branding_loader=lambda: branding
    )
    assert ctx.about_lines == (
        "Branding: white-label (source: deck.pptx)",
        _CURRENCY_LINE_LITERAL,
        "Logo on file: logo.png",
        "Audience mode: unrecognized value; rendered as internal_analyst",
    )


def test_render_rm_markdown_carries_currency_line_once() -> None:
    output = render_rm_markdown(
        "Body.", "portfolio review", branding_loader=lambda: _rm_branding()
    )
    assert output.count(_CURRENCY_LINE_LITERAL) == 1
    assert output.index("Branding:") < output.index(_CURRENCY_LINE_LITERAL)


def test_rm_branding_context_positional_two_field_construction_still_works() -> None:
    """Backward compat: resolved_audience is appended LAST with a default, so
    every caller written before §13 wiring keeps constructing with two
    positional args."""
    ctx = RMBrandingContext(("a",), ("b",))
    assert ctx.header_lines == ("a",)
    assert ctx.about_lines == ("b",)
    assert ctx.resolved_audience == DEFAULT_AUDIENCE
