"""Pure white-label rendering seam for RM-facing markdown workflows.

The workflow skill owns the analytical body. This module owns the small,
security-sensitive branding overlay so every RM consumer applies the same
source redaction, voice isolation, and degraded-branding behavior.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit


_LOADER_LOCK = threading.Lock()
_LOADED: dict[str, Any] = {}


def _load_loader():
    """Load the hyphenated sibling without relying on the caller's CWD.

    The module is registered in sys.modules DURING execution so a sibling that
    defines a dataclass can resolve its own __module__, but it is published to
    callers only after exec_module returns. Reading sys.modules directly would
    hand a concurrent caller a half-executed module.
    """
    name = "parallax_white_label_rm_loader"
    module = _LOADED.get(name)
    if module is not None:
        return module
    with _LOADER_LOCK:
        module = _LOADED.get(name)
        if module is not None:
            return module
        path = Path(__file__).resolve().with_name("loader.py")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load white-label loader: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        _LOADED[name] = module
        return module


_loader = _load_loader()
is_white_label_active = _loader.is_white_label_active
load_visual_branding = _loader.load_visual_branding
safe_source_reference = _loader.safe_source_reference


_MAX_CLIENT_NAME_CHARS = 120

# Characters that let an extracted client name break out of the markdown
# constructs it is interpolated into: "]" and "(" escape the image label and
# destination, "<" and ">" open raw HTML, "*" "_" "`" "#" "!" "[" ")" carry
# markdown meaning, "|" breaks table cells, and "\" escapes the next character.
_MARKDOWN_META = "[]()<>*_`#!|\\"


def _safe_display_name(value: Any) -> str:
    """Flatten an extracted client name into inert markdown link/label text.

    The name originates in client-supplied collateral, so it is untrusted.
    Interpolating it raw into ``![{name}]({url})`` and ``**{name}**`` let a
    crafted name close the image, inject HTML, and open new report sections.
    """
    if not isinstance(value, str):
        return ""
    # Collapse every control character and line break first; a newline alone is
    # enough to start a new markdown block inside the header.
    flattened = " ".join(value.split())
    stripped = "".join(" " if ch in _MARKDOWN_META else ch for ch in flattened)
    collapsed = " ".join(stripped.split())
    if len(collapsed) > _MAX_CLIENT_NAME_CHARS:
        collapsed = collapsed[:_MAX_CLIENT_NAME_CHARS].rstrip() + "…"
    return collapsed


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


class RMBrandingContext(NamedTuple):
    """Rendered white-label fragments for an RM markdown report.

    Deliberately a ``NamedTuple`` and not a frozen dataclass. This module is
    documented as the RM seam that consumer skills load from an absolute path,
    and the package's own importlib idiom (``persistence.py::_load_sibling``)
    execs a module without registering it in ``sys.modules``. Combined with
    ``from __future__ import annotations``, ``@dataclass`` resolves its string
    annotations through ``sys.modules[cls.__module__]`` during class creation
    and raises ``AttributeError: 'NoneType' object has no attribute '__dict__'``
    on Python 3.11. ``NamedTuple`` has the same frozen, field-named semantics
    and loads cleanly either way.
    """

    header_lines: tuple[str, ...]
    about_lines: tuple[str, ...]


def _has_renderable_branding(branding: Mapping[str, Any]) -> bool:
    """True when the mapping carries branding an RM report can actually show.

    ``is_white_label_active`` answers "is the config in an active state", which
    is not the same question as "is there anything to render". A config that
    loads cleanly but carries an empty branding block satisfies the first and
    fails the second, and the About This Report footer must not claim
    white-label provenance for a report rendered in default Parallax.
    """
    if _safe_display_name(branding.get("client_name")):
        return True
    for key in ("colors", "fonts", "logos"):
        value = branding.get(key)
        if isinstance(value, Mapping) and value:
            return True
    return False


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

    if not isinstance(branding, Mapping):
        return RMBrandingContext(
            header_lines=(),
            about_lines=("Branding: default Parallax (config error)",),
        )

    error = str(branding.get("error") or "")
    active = is_white_label_active(branding)  # type: ignore[arg-type]
    if active and not _has_renderable_branding(branding):
        # Active state with nothing to render: fall back rather than print an
        # unsupported white-label claim over a default-Parallax report.
        return RMBrandingContext(
            header_lines=(),
            about_lines=("Branding: default Parallax (branding empty)",),
        )
    header_lines: list[str] = []
    about_lines: list[str] = []

    if active:
        client_name = _safe_display_name(branding.get("client_name"))
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
