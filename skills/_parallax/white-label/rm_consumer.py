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
import unicodedata
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


#: Unicode general categories with no printable width. Cc and Cf carry the
#: terminal escapes (ESC, BEL) and bidi overrides that ``str.split`` leaves
#: alone, because they are not whitespace; Cs and Co have no defined rendering.
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co"})


def _safe_markdown_text(value: Any) -> str:
    """Flatten untrusted config text into inert single-line markdown content.

    Every string this module interpolates into a report — the client name, the
    redacted source reference, the logo filename — reaches it from
    client-supplied collateral, so all three take the same pass. Control and
    format characters are replaced before the markdown pass: ``str.split``
    collapses whitespace only, so ESC and BEL used to survive into a rendered
    deliverable and rewrite what an RM sees in a terminal.
    """
    if not isinstance(value, str):
        return ""
    printable = "".join(
        " " if unicodedata.category(ch) in _INVISIBLE_CATEGORIES else ch
        for ch in value
    )
    inert = "".join(" " if ch in _MARKDOWN_META else ch for ch in printable)
    return " ".join(inert.split())


def _safe_display_name(value: Any) -> str:
    """Flatten an extracted client name into inert markdown link/label text.

    The name originates in client-supplied collateral, so it is untrusted.
    Interpolating it raw into ``![{name}]({url})`` and ``**{name}**`` let a
    crafted name close the image, inject HTML, and open new report sections.
    """
    collapsed = _safe_markdown_text(value)
    if len(collapsed) > _MAX_CLIENT_NAME_CHARS:
        collapsed = collapsed[:_MAX_CLIENT_NAME_CHARS].rstrip() + "…"
    return collapsed


#: Characters that end, reopen, or escape a markdown link destination. A URL is
#: a destination rather than label text, so it is validated and refused instead
#: of being flattened: rewriting these would silently point the image somewhere
#: the operator never configured. Narrower than _MARKDOWN_META on purpose —
#: "_", "!", "*" and "|" are inert inside a destination and common in real logo
#: filenames, so refusing them would drop legitimate logos.
_URL_UNSAFE = "()<>[]`\\"


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
    for char in value:
        if (
            char.isspace()
            or char in _URL_UNSAFE
            or unicodedata.category(char) in _INVISIBLE_CATEGORIES
        ):
            return ""
    return value

BrandingLoader = Callable[[], Mapping[str, Any]]


#: Audience render modes per `parallax-conventions.md` §13.1. `internal_analyst`
#: is today's rendering, unchanged; `client_safe` is the forward-to-client
#: deliverable.
DEFAULT_AUDIENCE = "internal_analyst"
_AUDIENCE_MODES = frozenset({"internal_analyst", "client_safe"})

#: Notice lines appended to About This Report when resolution falls back to
#: the default. Neither echoes the raw config or flag value that triggered
#: the fallback — untrusted config must not reach the client-visible footer.
_UNRECOGNIZED_AUDIENCE_NOTICE = (
    "Audience mode: unrecognized value; rendered as internal_analyst"
)
_MALFORMED_AUDIENCE_NOTICE = (
    "Audience mode: malformed configuration; rendered as internal_analyst"
)


def resolve_audience(
    branding: Any, audience: str | None = None
) -> tuple[str, str | None]:
    """Resolve the §13.1 audience precedence. Returns ``(mode, notice)``.

    Pure function, no I/O — importable and callable without side effects, so
    both the RM seam (client-review, via `load_rm_branding_context`) and a
    direct Bash `python3 -c` call (rebalance, which does not use the RM seam)
    share exactly one implementation of the precedence order:

    1. A recognized per-invocation ``audience`` flag wins silently.
    2. An unrecognized non-empty flag falls back to `DEFAULT_AUDIENCE` with a
       notice.
    3. A flag of ``None`` (or empty) reads ``branding["render"]["audience_default"]``
       defensively. `branding` may not be a ``Mapping``, `render` may be
       missing, ``None``, or not itself a ``Mapping``, and `audience_default`
       may be missing, ``None``, or not a ``str`` — every one of those degrades
       to `DEFAULT_AUDIENCE`.
    4. A recognized config value wins silently.
    5. An unrecognized non-empty config value falls back with a notice.
    6. `render` or `audience_default` genuinely ABSENT (missing or explicit
       ``None``, including a non-Mapping `branding`) falls back to
       `DEFAULT_AUDIENCE` **silently** — absence is not a config error.
    7. `render` present but not a ``Mapping``, or `audience_default` present
       but not a ``str``, is MALFORMED — distinct from absent — and falls
       back with a notice.
    """
    if audience:
        if audience in _AUDIENCE_MODES:
            return audience, None
        return DEFAULT_AUDIENCE, _UNRECOGNIZED_AUDIENCE_NOTICE

    render = branding.get("render") if isinstance(branding, Mapping) else None
    if render is None:
        return DEFAULT_AUDIENCE, None  # absent config: silent
    if not isinstance(render, Mapping):
        return DEFAULT_AUDIENCE, _MALFORMED_AUDIENCE_NOTICE  # malformed shape

    config_value = render.get("audience_default")
    if config_value is None:
        return DEFAULT_AUDIENCE, None  # absent config: silent
    if not isinstance(config_value, str):
        return DEFAULT_AUDIENCE, _MALFORMED_AUDIENCE_NOTICE  # malformed shape

    if config_value in _AUDIENCE_MODES:
        return config_value, None
    return DEFAULT_AUDIENCE, _UNRECOGNIZED_AUDIENCE_NOTICE


#: Unconditional second About This Report line per integration-pattern.md §7
#: ("Currency basis"). Independent of `white_label_active` and of which
#: Branding-line row rendered — every path emits it, immediately after the
#: Branding line.
_CURRENCY_LINE = (
    "Currency: figures as reported by source data; "
    "no base-currency conversion applied."
)


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

    ``resolved_audience`` is appended LAST, with a default, so existing
    2-arg positional construction (``RMBrandingContext(header, about)``)
    keeps working for every caller written before §13 wiring.
    """

    header_lines: tuple[str, ...]
    about_lines: tuple[str, ...]
    resolved_audience: str = DEFAULT_AUDIENCE


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


def _context(
    header_lines: tuple[str, ...],
    about_lines: tuple[str, ...],
    resolved_audience: str,
    notice: str | None,
) -> RMBrandingContext:
    """Tail helper: insert the §7 currency line, then append the
    resolve_audience notice and the §13.4 mode line.

    Every return point in `load_rm_branding_context` funnels through here so
    the lines land in the same relative order no matter which branch produced
    `about_lines`, matching integration-pattern.md §7 row order: Branding
    line, unconditional currency line, any `Logo on file:` line, any notice,
    then the client-safe mode line. Every branch passes a Branding-first
    tuple, so inserting at index 1 places the currency line second.
    """
    lines = list(about_lines)
    lines.insert(1, _CURRENCY_LINE)
    if notice:
        lines.append(notice)
    if resolved_audience == "client_safe":
        lines.append("Audience mode: client-safe")
    return RMBrandingContext(tuple(header_lines), tuple(lines), resolved_audience)


def load_rm_branding_context(
    deliverable_label: str,
    *,
    branding_loader: BrandingLoader = load_visual_branding,
    audience: str | None = None,
) -> RMBrandingContext:
    """Load and render the visual-only branding overlay for one RM report.

    Loader failures degrade to default branding. Raw errors and source
    references never enter returned text. `about_lines` always carries the
    unconditional §7 currency line immediately after the Branding line — on
    every path, including default-Parallax and error fallbacks. Also resolves
    the §13.1 audience mode via `resolve_audience` and folds its notice plus
    the §13.4 mode line into `about_lines` — the caller never assembles any
    of those lines itself.
    """
    try:
        branding = branding_loader()
    except Exception:
        resolved, notice = resolve_audience(None, audience)
        return _context(
            (), ("Branding: default Parallax (config error)",), resolved, notice
        )

    if not isinstance(branding, Mapping):
        resolved, notice = resolve_audience(None, audience)
        return _context(
            (), ("Branding: default Parallax (config error)",), resolved, notice
        )

    error = str(branding.get("error") or "")
    active = is_white_label_active(branding)  # type: ignore[arg-type]
    if active and not _has_renderable_branding(branding):
        # Active state with nothing to render: fall back rather than print an
        # unsupported white-label claim over a default-Parallax report.
        resolved, notice = resolve_audience(branding, audience)
        return _context(
            (), ("Branding: default Parallax (branding empty)",), resolved, notice
        )

    resolved, notice = resolve_audience(branding, audience)
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
            safe_reference = _safe_markdown_text(
                safe_source_reference(branding)  # type: ignore[arg-type]
            )
            line = f"Branding: white-label (source: {safe_reference})"
            if "logo_missing" in error:
                line += " (logo unavailable, omitted)"
            about_lines.append(line)

        if primary_logo.startswith(("/", "~")):
            logo_name = _safe_markdown_text(Path(primary_logo).name)
            if logo_name:
                about_lines.append(f"Logo on file: {logo_name}")
    elif error == "config_not_found":
        about_lines.append("Branding: default Parallax")
    else:
        about_lines.append("Branding: default Parallax (config error)")

    return _context(tuple(header_lines), tuple(about_lines), resolved, notice)


def render_rm_markdown(
    body: str,
    deliverable_label: str,
    *,
    branding_loader: BrandingLoader = load_visual_branding,
    audience: str | None = None,
) -> str:
    """Compose a complete minimal RM markdown report around a valid body.

    Complex workflow renderers can place the returned context fragments
    themselves. This function provides an executable end-to-end contract for
    consumers that only need a header, body, and About This Report footer.
    """
    context = load_rm_branding_context(
        deliverable_label,
        branding_loader=branding_loader,
        audience=audience,
    )
    blocks = [*context.header_lines, body, "## About This Report", *context.about_lines]
    return "\n\n".join(block for block in blocks if block)
