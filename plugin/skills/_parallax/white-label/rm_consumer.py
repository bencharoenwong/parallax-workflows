"""Pure white-label rendering seam for RM-facing markdown workflows.

The workflow skill owns the analytical body. This module owns the small,
security-sensitive branding overlay so every RM consumer applies the same
source redaction, voice isolation, and degraded-branding behavior.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import importlib.util
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def _load_loader():
    """Load the hyphenated sibling without relying on the caller's CWD."""
    path = Path(__file__).resolve().with_name("loader.py")
    spec = importlib.util.spec_from_file_location(
        "parallax_white_label_rm_loader", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load white-label loader: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_loader = _load_loader()
is_white_label_active = _loader.is_white_label_active
load_visual_branding = _loader.load_visual_branding
safe_source_reference = _loader.safe_source_reference


def _safe_logo_url(value: str) -> str:
    """Return a public-looking logo URL without credentials or URL values."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return ""
    return value

BrandingLoader = Callable[[], Mapping[str, Any]]


@dataclass(frozen=True)
class RMBrandingContext:
    """Rendered white-label fragments for an RM markdown report."""

    header_lines: tuple[str, ...]
    about_lines: tuple[str, ...]


def load_rm_branding_context(
    deliverable_label: str,
    *,
    branding_loader: BrandingLoader = load_visual_branding,
) -> RMBrandingContext:
    """Load and render the visual-only branding overlay for one RM report.

    Loader failures degrade to default branding. Raw errors and source
    references never enter returned text.
    """
    try:
        branding = branding_loader()
    except Exception:
        return RMBrandingContext(
            header_lines=(),
            about_lines=("Branding: default Parallax (config error)",),
        )

    error = str(branding.get("error") or "")
    active = is_white_label_active(branding)  # type: ignore[arg-type]
    header_lines: list[str] = []
    about_lines: list[str] = []

    if active:
        client_name = str(branding.get("client_name") or "").strip()
        logos = branding.get("logos")
        primary_logo = ""
        if isinstance(logos, Mapping):
            primary_logo = str(logos.get("primary") or "").strip()
        safe_logo = _safe_logo_url(primary_logo)
        if safe_logo:
            header_lines.append(f"![{client_name}]({safe_logo})")
        if client_name:
            header_lines.append(f"**{client_name}** {deliverable_label}")

        if "schema_unavailable" in error:
            about_lines.append(
                "Branding: white-label (best-effort, schema unavailable)"
            )
        else:
            safe_reference = safe_source_reference(branding)  # type: ignore[arg-type]
            line = f"Branding: white-label (source: {safe_reference})"
            if "logo_missing" in error:
                line += " (logo unavailable, omitted)"
            about_lines.append(line)

        if primary_logo.startswith(("/", "~")):
            about_lines.append(f"Logo on file: {Path(primary_logo).name}")
    elif error == "config_not_found":
        about_lines.append("Branding: default Parallax")
    else:
        about_lines.append("Branding: default Parallax (config error)")

    return RMBrandingContext(tuple(header_lines), tuple(about_lines))


def render_rm_markdown(
    body: str,
    deliverable_label: str,
    *,
    branding_loader: BrandingLoader = load_visual_branding,
) -> str:
    """Compose a complete minimal RM markdown report around a valid body.

    Complex workflow renderers can place the returned context fragments
    themselves. This function provides an executable end-to-end contract for
    consumers that only need a header, body, and About This Report footer.
    """
    context = load_rm_branding_context(
        deliverable_label,
        branding_loader=branding_loader,
    )
    blocks = [*context.header_lines, body, "## About This Report", *context.about_lines]
    return "\n\n".join(block for block in blocks if block)
