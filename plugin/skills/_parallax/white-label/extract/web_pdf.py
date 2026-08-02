"""URL and PDF extraction.

URL path: a destination-validated, size-capped urllib fetch for raw HTML and
page text. The merged corpus drives the regex extractors.

PDF path: pypdf or pdfplumber for text extraction; regex extractors run
against the resulting text. Confidence is reduced to reflect the fragility
of PDF text extraction vs canonical OOXML theme XML.
"""

import re
import ipaddress
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit, urlunsplit

from .colors import ColorExtractor, _assign_color_roles_by_frequency
from .voice import _voice_corpus_from_text


_EMPTY_VOICE_CORPUS = {"text": "", "word_count": 0, "truncated": False}

# Caps for external-stylesheet following: total link follows + per-fetch size +
# overall budget. URL extraction is best-effort; runaway fetching against a
# fanned-out site is the wrong trade.
_MAX_STYLESHEET_LINKS = 5
_STYLESHEET_READ_CAP = 1 * 1024 * 1024  # 1 MB per stylesheet
_STYLESHEET_TOTAL_TIMEOUT_SECONDS = 8

# Blocks whose CONTENT is markup machinery, not prose. Stripping tags alone
# leaves their bodies behind, and on a modern page the head is dominated by
# minified JS/CSS/JSON-LD — enough to fill the voice corpus's leading-token
# window with script noise while word_count still looks healthy.
_NON_PROSE_TAGS = ("script", "style", "template", "noscript")
_COMMENT_KEY = "<!--"
_NON_PROSE_OPENER_RE = re.compile(
    r"<(" + "|".join(_NON_PROSE_TAGS) + r")\b[^>]*>|<!--", re.IGNORECASE)
_NON_PROSE_CLOSER_RE = re.compile(
    r"</(" + "|".join(_NON_PROSE_TAGS) + r")\s*>|-->", re.IGNORECASE)


class UrlNotPublicError(ValueError):
    """A URL destination failed the public-address policy.

    Subclasses ``ValueError`` so existing ``except ValueError`` callers keep
    working, while letting the extractor distinguish a real destination
    rejection from an unrelated ValueError raised further down the pipeline.
    """


def _match_key(match: "re.Match[str]") -> str:
    return (match.group(1) or "").lower() or _COMMENT_KEY


def _strip_non_prose_blocks(raw_html: str) -> str:
    """Drop script/style/template/noscript bodies and HTML comments.

    Positions come from ``re.finditer`` spans over the ORIGINAL string, never a
    case-folded copy: ``str.lower()`` applies full Unicode case mapping and
    U+0130 expands to two code points, so offsets taken on a lowered copy drift
    against the source and slice mid-character.

    One finditer pass per delimiter plus a forward merge keeps the scan O(len).
    Both patterns are non-backtracking, unlike a lazy DOTALL body, which
    re-scans to end-of-document for every *unterminated* opener — O(openers x
    length), which a hostile page hits deliberately and which the 5 MB fetch cap
    is far too generous to contain. An opener with no closer consumes the rest
    of the document, since that content is markup either way.
    """
    openers = [
        (m.start(), m.end(), _match_key(m))
        for m in _NON_PROSE_OPENER_RE.finditer(raw_html)
    ]
    if not openers:
        return raw_html

    closers: dict[str, list[tuple[int, int]]] = {}
    for match in _NON_PROSE_CLOSER_RE.finditer(raw_html):
        closers.setdefault(_match_key(match), []).append(
            (match.start(), match.end()))
    next_closer = dict.fromkeys(closers, 0)

    parts: list[str] = []
    cursor = 0
    for start, opener_end, key in openers:
        if start < cursor:
            continue
        parts.append(raw_html[cursor:start])
        candidates = closers.get(key, ())
        index = next_closer.get(key, 0)
        while index < len(candidates) and candidates[index][0] < opener_end:
            index += 1
        if key in next_closer:
            next_closer[key] = index
        if index >= len(candidates):
            cursor = len(raw_html)
            break
        cursor = candidates[index][1]
    parts.append(raw_html[cursor:])
    return " ".join(parts)


def _html_to_page_text(raw_html: str) -> str:
    """Strip markup to a prose corpus, dropping non-prose block bodies first."""
    return re.sub(r"<[^>]+>", " ", _strip_non_prose_blocks(raw_html))


def _sanitized_url(url: str) -> str:
    """Return a log-safe URL without credentials, query parameters, or fragment."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except (TypeError, ValueError):
        return "(invalid URL)"


def _public_ip(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def _resolve_public_url(url: str) -> tuple[str, int, str]:
    """Reject URL destinations that do not resolve exclusively to public IPs.

    This intentionally rejects mixed public/private DNS answers: allowing the
    public member would leave a DNS-rebinding window between validation and
    connection. Legacy IPv4 integer/hex/octal forms are normalized with
    ``inet_aton`` before DNS lookup.
    """
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        if "%" in parsed.hostname:  # IPv6 zone identifiers are local-scope syntax.
            raise ValueError
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (TypeError, ValueError):
        raise UrlNotPublicError("URL destination is not public") from None

    host = parsed.hostname
    addresses: list[str] = []
    try:
        addresses.append(str(ipaddress.ip_address(host)))
    except ValueError:
        # inet_aton recognizes historical forms such as 2130706433 and
        # 0x7f000001 that URL parsers otherwise treat as DNS names.
        try:
            packed = socket.inet_aton(host)
            addresses.append(str(ipaddress.ip_address(packed)))
        except OSError:
            try:
                answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            except (OSError, UnicodeError):
                raise UrlNotPublicError("URL destination is not public") from None
            for answer in answers:
                address = answer[4][0].split("%", 1)[0]
                if address not in addresses:
                    addresses.append(address)

    if not addresses or any(not _public_ip(address) for address in addresses):
        raise UrlNotPublicError("URL destination is not public")
    return host, port, addresses[0]


def _validate_public_url(url: str) -> None:
    _resolve_public_url(url)


def _make_pinned_connection(connection_class, host: str, pinned_ip: str, **kwargs):
    """Build an HTTP(S) connection whose TCP dial uses an already-checked IP.

    The connection's ``host`` remains the URL hostname, so HTTP Host headers
    and HTTPS certificate/SNI verification retain their normal semantics. Only
    the address passed to the socket connector is replaced.
    """
    connection = connection_class(host, **kwargs)
    create_connection = connection._create_connection

    def create_pinned(address, *args, **connect_kwargs):
        return create_connection((pinned_ip, address[1]), *args, **connect_kwargs)

    connection._create_connection = create_pinned
    return connection


def _network_open(request, *, timeout: int):
    """Open with redirect validation performed before following Location."""
    from http.client import HTTPConnection, HTTPSConnection
    from urllib.request import (
        HTTPHandler,
        HTTPSHandler,
        HTTPRedirectHandler,
        ProxyHandler,
        build_opener,
    )

    def pin_request(req, url):
        _host, _port, pinned_ip = _resolve_public_url(url)
        req._parallax_pinned_ip = pinned_ip
        return req

    class PublicRedirectHandler(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
            return pin_request(redirected, newurl)

    class PinnedHTTPHandler(HTTPHandler):
        def http_open(self, req):
            pinned_ip = req._parallax_pinned_ip
            return self.do_open(
                lambda host, **kwargs: _make_pinned_connection(
                    HTTPConnection, host, pinned_ip, **kwargs
                ),
                req,
            )

    class PinnedHTTPSHandler(HTTPSHandler):
        def https_open(self, req):
            pinned_ip = req._parallax_pinned_ip
            return self.do_open(
                lambda host, **kwargs: _make_pinned_connection(
                    HTTPSConnection, host, pinned_ip, **kwargs
                ),
                req,
            )

    if not hasattr(request, "_parallax_pinned_ip"):
        pin_request(request, request.full_url)
    # Disable environment proxies: otherwise the validated destination and the
    # socket endpoint intentionally differ, defeating destination pinning.
    return build_opener(
        ProxyHandler({}), PublicRedirectHandler(), PinnedHTTPHandler(), PinnedHTTPSHandler()
    ).open(request, timeout=timeout)


def _open_public_url(request, *, timeout: int):
    """Open a validated URL and validate its final redirect before body read."""
    requested_url = request.full_url if hasattr(request, "full_url") else str(request)
    _host, _port, pinned_ip = _resolve_public_url(requested_url)
    request._parallax_pinned_ip = pinned_ip
    response = _network_open(request, timeout=timeout)
    final_url = response.geturl() if hasattr(response, "geturl") else requested_url
    try:
        _validate_public_url(final_url)
    except Exception:
        try:
            response.close()
        finally:
            raise
    return response


def _fetch_external_stylesheets(raw_html: str, base_url: str) -> str:
    """Best-effort extraction of font information from external CSS.

    Many sites declare fonts in external stylesheet files (linked via
    `<link rel="stylesheet" href="...">`) or via Google Fonts
    (`<link href="https://fonts.googleapis.com/css2?family=...">`). The raw HTML
    body alone has no `font-family` declaration to feed the regex extractor, so
    URL-based font extraction comes back empty.

    Strategy:
      1. Regex-find up to _MAX_STYLESHEET_LINKS stylesheet hrefs in the HTML.
      2. For Google Fonts URLs, extract `family=` parameters directly — they
         carry the font name without needing the file fetched.
      3. For other CSS URLs, fetch (size-capped, total-time-capped) and append
         the bytes to the returned string. The downstream regex extractor will
         find `font-family:` declarations inside the fetched content.

    All errors are swallowed silently — this is best-effort enrichment, not a
    correctness path. Returns the concatenated CSS-equivalent text.

    Security note (SSRF surface):
        Stylesheet URLs are untrusted page content. Each non-Google fetch goes
        through `_open_public_url`, which rejects non-public answers and pins the
        TCP connection to the validated numeric address across redirects.
    """
    import re
    import time
    from urllib.parse import urljoin, parse_qs, urlparse

    # Stylesheet href regex (HTML attribute order varies)
    link_pattern = re.compile(
        r'<link\b[^>]*\brel\s*=\s*["\']?stylesheet["\']?[^>]*\bhref\s*=\s*["\']([^"\']+)["\']'
        r'|'
        r'<link\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\'][^>]*\brel\s*=\s*["\']?stylesheet["\']?',
        re.IGNORECASE,
    )

    hrefs: list[str] = []
    for m in link_pattern.finditer(raw_html):
        href = m.group(1) or m.group(2)
        if href:
            hrefs.append(href)
        if len(hrefs) >= _MAX_STYLESHEET_LINKS:
            break

    if not hrefs:
        return ""

    parts: list[str] = []
    deadline = time.monotonic() + _STYLESHEET_TOTAL_TIMEOUT_SECONDS

    for href in hrefs:
        if time.monotonic() >= deadline:
            break

        absolute = urljoin(base_url, href)

        # Google Fonts: family parameter contains the font name(s); no fetch needed
        try:
            parsed = urlparse(absolute)
        except Exception:
            continue
        if "fonts.googleapis.com" in (parsed.netloc or "") or "fonts.gstatic.com" in (parsed.netloc or ""):
            qs = parse_qs(parsed.query)
            for fam in qs.get("family", []):
                # "Roboto:wght@400" or "Roboto+Slab" -> normalise to a font-family declaration
                name = fam.split(":", 1)[0].replace("+", " ")
                if name:
                    parts.append(f"font-family: {name};")
            continue

        # Non-Google CSS: fetch the file directly and append
        try:
            from urllib.request import Request
            req = Request(absolute, headers={"User-Agent": "Mozilla/5.0"})
            remaining = max(1, int(deadline - time.monotonic()))
            with _open_public_url(req, timeout=remaining) as resp:
                ctype = resp.headers.get_content_type() if hasattr(resp.headers, "get_content_type") else (resp.headers.get("Content-Type") or "")
                # Only treat text/css as readable; HTML / images / binary blobs are noise
                if ctype and "css" not in ctype.lower() and "text" not in ctype.lower():
                    continue
                raw = resp.read(_STYLESHEET_READ_CAP)
                encoding = resp.headers.get_content_charset() or "utf-8"
                parts.append(raw.decode(encoding, errors="replace"))
        except Exception:
            continue

    return "\n\n".join(parts)


class LogoExtractor:
    """Extract logo URLs and paths from text and HTML."""

    @staticmethod
    def extract_logo_urls(text: str, base_url: str = "") -> List[Dict[str, Any]]:
        """Find logo image URLs in text or HTML.

        Returns: [{"url": str, "alt_text": str, "confidence": float}, ...]
        """
        logos = []
        seen_urls = set()

        for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', text):
            alt_text = match.group(1)
            url = match.group(2)

            if url in seen_urls:
                continue
            seen_urls.add(url)

            confidence = 0.6
            if any(kw in url.lower() for kw in ["logo", "brand", "icon"]):
                confidence = 0.9
            elif any(ext in url.lower() for ext in [".png", ".svg", ".jpg", ".jpeg", ".gif"]):
                confidence = 0.75

            logos.append({
                "url": url,
                "alt_text": alt_text,
                "confidence": confidence,
            })

        for match in re.finditer(r'https?://[^\s]+(?:logo|brand|icon)[^\s]*\.(?:png|svg|jpg|jpeg|gif)', text, re.IGNORECASE):
            url = match.group(0)
            if url not in seen_urls:
                seen_urls.add(url)
                logos.append({
                    "url": url,
                    "alt_text": "logo",
                    "confidence": 0.9,
                })

        for match in re.finditer(r'https?://[^\s]+\.(?:png|svg|jpg|jpeg|gif)', text, re.IGNORECASE):
            url = match.group(0)
            if url not in seen_urls:
                seen_urls.add(url)
                logos.append({
                    "url": url,
                    "alt_text": "image",
                    "confidence": 0.6,
                })

        return logos

    @staticmethod
    def extract_logo_paths(text: str) -> List[Dict[str, Any]]:
        """Find local logo file paths in text.

        Returns: [{"path": str, "confidence": float}, ...]
        """
        paths = []
        seen_paths = set()

        for match in re.finditer(r'/[^\s]*(?:logo|brand|icon|assets)[^\s]*\.(?:png|svg|jpg|jpeg|gif)', text, re.IGNORECASE):
            path = match.group(0)
            if path not in seen_paths:
                seen_paths.add(path)
                paths.append({
                    "path": path,
                    "confidence": 0.8,
                })

        for match in re.finditer(r'(?:^|\s)(/[^\s]+\.(?:png|svg|jpg|jpeg|gif))(?:\s|$)', text, re.IGNORECASE):
            path = match.group(1)
            if path not in seen_paths:
                seen_paths.add(path)
                paths.append({
                    "path": path,
                    "confidence": 0.7,
                })

        return paths


class FontExtractor:
    """Extract font names from CSS, PDFs, and HTML."""

    @staticmethod
    def extract_fonts_from_css(text: str) -> List[Dict[str, Any]]:
        """Parse font-family declarations from CSS.

        Returns: [{"font_name": str, "usage": "header|body|monospace", "confidence": float}, ...]
        """
        fonts = []

        for match in re.finditer(r'font-family\s*:\s*([^;,\n}]+)', text):
            font_decl = match.group(1).strip()
            font_name = font_decl.split(',')[0].strip(' "\'')

            usage = "body"

            brace_pos = text.rfind('{', 0, match.start())
            if brace_pos == -1:
                start_pos = 0
            else:
                start_pos = max(0, brace_pos - 100)
            selector_text = text[start_pos:brace_pos if brace_pos != -1 else match.start()].lower()

            # Restrict selector inspection to the LAST line before the brace.
            # CSS selectors are conventionally on one line; widening past the
            # preceding newline lets concatenated HTML body content (e.g.,
            # `<h1>Title</h1>` from the page when CSS+HTML are merged) bleed
            # into the heuristic and mis-tag body fonts as headers.
            selector_text = selector_text.rsplit('\n', 1)[-1]

            # Word-boundary checks so substrings inside HTML tags or other
            # selectors don't accidentally trigger usage classification.
            if re.search(r'\b(h[1-6]|header)\b', selector_text):
                usage = "header"
            elif re.search(r'\b(mono|code|pre)\b', selector_text):
                usage = "monospace"
            elif re.search(r'\bbody\b', selector_text):
                usage = "body"

            fonts.append({
                "font_name": font_name,
                "usage": usage,
                "confidence": 0.85,
            })

        return fonts

    @staticmethod
    def extract_fonts_from_pdf_text(text: str) -> List[Dict[str, Any]]:
        """Guess fonts from OCR'd PDF text or explicit font mentions."""
        fonts = []

        font_patterns = [
            r'(?:font|family|typeface):\s*([A-Z][A-Za-z\s]+?)(?:\s*(?:,|for|in|as)|$)',
            r'(?:headers?|body|text)\s+(?:uses?|in)\s+([A-Z][A-Za-z\s]+?)(?:\s*(?:,|;)|$)',
        ]

        for pattern in font_patterns:
            for match in re.finditer(pattern, text):
                font_name = match.group(1).strip()

                usage = "body"
                if any(h in match.group(0).lower() for h in ['header', 'heading', 'title']):
                    usage = "header"
                elif any(m in match.group(0).lower() for m in ['mono', 'code']):
                    usage = "monospace"

                fonts.append({
                    "font_name": font_name,
                    "usage": usage,
                    "confidence": 0.7,
                })

        return fonts



def _flatten_at_rules(css_text: str) -> str:
    """Unwrap @media / @supports / @keyframes / @container blocks so their
    inner rules appear at top level. The downstream rule-finder regex doesn't
    handle nested braces, so without this pre-pass every rule inside an
    @media block is silently dropped — on a real Tailwind/Bootstrap stylesheet
    that's most of the responsive typography.

    Brace-counting is used because a regex can't reliably match balanced
    braces. Calls itself recursively so a `@supports { @media { ... } }`
    onion gets fully unwrapped. Comments are assumed already stripped by
    the caller.
    """
    out = []
    i = 0
    n = len(css_text)
    while i < n:
        ch = css_text[i]
        if ch == '@':
            # Find the opening brace of the at-rule's body, or the terminating
            # semicolon for prelude-only rules like @import / @charset.
            brace_start = -1
            semi = -1
            for j in range(i, n):
                if css_text[j] == '{':
                    brace_start = j
                    break
                if css_text[j] == ';':
                    semi = j
                    break
            if brace_start == -1:
                # No body — skip up to the semicolon (or end) and discard.
                i = (semi + 1) if semi != -1 else n
                continue
            # Walk to find the matching closing brace.
            depth = 1
            j = brace_start + 1
            while j < n and depth > 0:
                c = css_text[j]
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                j += 1
            if depth != 0:
                # Unbalanced; stop processing this branch.
                break
            inner = css_text[brace_start + 1:j - 1]
            out.append(_flatten_at_rules(inner))
            i = j
        else:
            # Non-at character: copy through to the next @-rule (or end).
            next_at = css_text.find('@', i)
            if next_at == -1:
                out.append(css_text[i:])
                break
            out.append(css_text[i:next_at])
            i = next_at
    return ''.join(out)


def _normalize_css_dimension(value: str, *, zero_unit: str = "em") -> str:
    """Normalize a CSS dimension to a DESIGN.md-spec-compliant unit.

    The DESIGN.md linter rejects `pt` outright and accepts only px / rem / em.
    Many real-world stylesheets (especially for print or PDF brand guides
    served as HTML) use pt. Convert pt → px at 96dpi (1pt = 4/3 px) and
    normalize the unit casing.

    Unitless zero (`0`, `0.0`) is interpreted as a dimension with the unit
    `zero_unit` (default `em`). The linter requires letterSpacing carry a
    unit, so bare `"0"` from CSS would be rejected. The caller can pass
    `zero_unit="px"` if `px` is more semantically appropriate for the field.

    Other bare numbers (line-height multipliers like `1.5`) are returned
    unchanged — those are valid CSS unitless values. Unknown units (`%`,
    `vw`, CSS keywords) pass through verbatim; the linter will surface them.
    """
    import re
    s = value.strip()
    m = re.match(r'^(-?[\d.]+)\s*([a-zA-Z%]+)?\s*$', s)
    if not m:
        return s
    num_str, unit = m.group(1), (m.group(2) or "").lower()
    if not unit:
        # Unitless zero gets a unit; non-zero unitless stays as-is (it's a
        # line-height multiplier or similar valid unitless value).
        try:
            if float(num_str) == 0:
                return f"0{zero_unit}"
        except (ValueError, TypeError):
            pass
        return num_str
    if unit == "pt":
        try:
            px = round(float(num_str) * 4 / 3)
            return f"{px}px"
        except (ValueError, TypeError):
            return s
    if unit in ("px", "rem", "em"):
        return f"{num_str}{unit}"
    return s


class TypographyExtractor:
    @staticmethod
    def extract_type_scale_from_css(css_text: str) -> Dict[str, Dict[str, Any]]:
        import re
        css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
        # Unwrap @media / @supports / @keyframes / @container blocks so their
        # inner rules become visible to the rule-finder regex (which assumes
        # no nested braces). On real Tailwind/Bootstrap stylesheets the bulk
        # of typography lives inside @media — without this, it's silently lost.
        css_text = _flatten_at_rules(css_text)
        scale = {}

        sel_map = {
            "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h5",
            "body": "body-md", "p": "body-md", "body-md": "body-md",
            "code": "code", "pre": "code",
        }

        # Find every rule (selectors-list { declarations }) and check whether
        # any selector-list token EXACTLY matches one of our canonical names.
        # Anchored on token boundaries — '.h1-banner', '.code-block', '.p-4'
        # are utility classes that look prefix-similar but must NOT pollute
        # the canonical typography scale (this would happen on any real
        # Tailwind/Bootstrap site otherwise).
        rule_pattern = re.compile(r'([^{}]+)\{([^}]+)\}', re.DOTALL)
        for rule_match in rule_pattern.finditer(css_text):
            selectors_blob = rule_match.group(1)
            # Split on comma to handle "h1, .heading { ... }", then strip
            # whitespace and pseudo-classes/combinators to isolate the
            # outermost token (e.g. "article > h1:first-child" → "h1").
            level = None
            for sel_raw in selectors_blob.split(','):
                sel = sel_raw.strip()
                # Take the LAST CSS token of a descendant selector — it's the
                # element being styled. Strip pseudo-classes / pseudo-elements.
                tokens = re.split(r'\s+', sel)
                if not tokens:
                    continue
                last = tokens[-1]
                last = re.sub(r'[:].*$', '', last)         # strip pseudo
                last = re.sub(r'\[.*?\]', '', last)        # strip attribute selectors
                # IDs are never canonical typography names — skip.
                if last.startswith('#'):
                    continue
                # For class selectors, only match when the class name EQUALS a
                # canonical token (e.g. `.body-md` → "body-md"). Reject names
                # that merely have the canonical as prefix (`.h1-banner`,
                # `.code-block`) — those are utility classes, not semantic
                # typography surfaces.
                if last.startswith('.'):
                    candidate = last[1:].lower()
                else:
                    candidate = last.lower()
                if candidate in sel_map:
                    level = sel_map[candidate]
                    break
            if level is None or level in scale:
                continue

            match = rule_match  # alias for backward compatibility with original block
            sel = level         # retained for tracing; not used downstream
            
            block = match.group(2)
            style = {
                "fontWeight": 400,
                "lineHeight": "1.5",
                "letterSpacing": "0em",
            }

            fs_m = re.search(r'font-size\s*:\s*([^;]+)', block, re.IGNORECASE)
            fw_m = re.search(r'font-weight\s*:\s*([^;]+)', block, re.IGNORECASE)
            lh_m = re.search(r'line-height\s*:\s*([^;]+)', block, re.IGNORECASE)
            ls_m = re.search(r'letter-spacing\s*:\s*([^;]+)', block, re.IGNORECASE)
            ff_m = re.search(r'font-family\s*:\s*([^;]+)', block, re.IGNORECASE)

            if not any([fs_m, fw_m, lh_m, ls_m, ff_m]):
                continue

            if fs_m:
                style["fontSize"] = _normalize_css_dimension(fs_m.group(1).strip())
            if fw_m:
                val = fw_m.group(1).strip()
                if val.isdigit():
                    style["fontWeight"] = int(val)
                elif val.lower() == "bold":
                    style["fontWeight"] = 700
            if lh_m:
                # line-height accepts a unitless multiplier or a dimension.
                # Pass unitless through; normalize pt for dimension form.
                lh_val = lh_m.group(1).strip()
                style["lineHeight"] = _normalize_css_dimension(lh_val) if any(u in lh_val.lower() for u in ("pt", "px", "rem", "em")) else lh_val
            if ls_m:
                style["letterSpacing"] = _normalize_css_dimension(
                    ls_m.group(1).strip()
                )
            if ff_m:
                style["fontFamily"] = (
                    ff_m.group(1).strip().split(',')[0].strip(' "\'')
                )
            
            scale[level] = style
            
        return scale

class ShapeExtractor:
    @staticmethod
    def extract_border_radii(css_text: str) -> Dict[str, str]:
        import re
        # Any radius above this threshold (px) is treated as "full" (pill shape).
        # Values like 999px, 1000px etc. are clearly pill intent even if they
        # don't reach the 9999 sentinel; without this clamp they'd skew the
        # sm/md/lg percentile sort.
        FULL_RADIUS_PX_THRESHOLD = 64
        radii = []
        has_full = False
        for match in re.finditer(r'border-radius\s*:\s*([^;]+)', css_text, re.IGNORECASE):
            val = match.group(1).strip()
            if "50%" in val:
                has_full = True
                continue
            if "%" in val:
                continue
            m = re.match(r'^([\d.]+)(px|rem)$', val, re.IGNORECASE)
            if m:
                num = float(m.group(1))
                unit = m.group(2).lower()
                if unit == "rem":
                    num *= 16
                if num >= FULL_RADIUS_PX_THRESHOLD:
                    has_full = True
                else:
                    radii.append((num, val))

        res = {}
        if has_full:
            res["full"] = "9999px"

        unique = {}
        for num, text in radii:
            if num not in unique:
                unique[num] = text
        nums = sorted(list(unique.keys()))
        if len(nums) >= 2:
            sm_idx = max(0, int(len(nums) * 0.25))
            md_idx = int(len(nums) * 0.5)
            lg_idx = min(len(nums) - 1, int(len(nums) * 0.75))
            
            res["sm"] = unique[nums[sm_idx]]
            res["md"] = unique[nums[md_idx]]
            res["lg"] = unique[nums[lg_idx]]
            
            if nums[sm_idx] < 4:
                res["sm"] = "4px"
                
        elif has_full:
            pass 
        else:
            return {}
            
        return res

class SpacingExtractor:
    @staticmethod
    def extract_spacing_scale(css_text: str) -> Dict[str, str]:
        import re
        vals = []
        for match in re.finditer(r'(?:padding|margin|gap)(?:-[a-z]+)?\s*:\s*([^;]+)', css_text, re.IGNORECASE):
            parts = match.group(1).split()
            for p in parts:
                m = re.match(r'^([\d.]+)(px|rem)$', p, re.IGNORECASE)
                if m:
                    num = float(m.group(1))
                    if num == 0:
                        continue
                    unit = m.group(2).lower()
                    if unit == "rem":
                        num *= 16
                    vals.append((num, p))
        unique = {}
        for num, text in vals:
            if num not in unique:
                unique[num] = text
        nums = sorted(list(unique.keys()))
        if len(nums) >= 4:
            sm_idx = max(0, int(len(nums) * 0.25))
            md_idx = int(len(nums) * 0.5)
            lg_idx = min(len(nums) - 1, int(len(nums) * 0.75))
            
            return {
                "xs": unique[nums[0]],
                "sm": unique[nums[sm_idx]],
                "md": unique[nums[md_idx]],
                "lg": unique[nums[lg_idx]],
                "xl": unique[nums[-1]]
            }
        return {}

def _extract_brand_guide_prose(pdf_text: str, *, filename: str) -> Dict[str, str]:
    import re
    if not re.search(r'(brand|guide|identity|style)', filename, re.IGNORECASE):
        return {}
        
    found = []
    # The apostrophe class [\'’] matches both ASCII (') and the curly
    # right-single-quotation-mark (U+2019, ’) that PDF brand guides commonly
    # render via smart-quote substitution. Without the alternation, real
    # brand guides with "Do’s and Don’ts" headings are missed entirely.
    APOS = r"[\'’]"
    patterns = {
        "overview": r'^(?:\d+\.\s*)?Overview\b',
        "colors": r'^(?:\d+\.\s*)?Colors\b',
        "typography": r'^(?:\d+\.\s*)?Typography\b',
        "dos_and_donts": rf'^(?:\d+\.\s*)?Do{APOS}s and Don{APOS}ts\b',
    }
    
    # Heuristic for detecting TOC lines: heavy dot-leader pattern
    # ("Overview .................. 5") or trailing page numbers. When a
    # heading-matching line is structured like a TOC entry, treat it as
    # decorative rather than a real section boundary. This prevents TOC
    # entries from stealing the "first non-empty" slot from the real body.
    toc_pattern = re.compile(r'\.{4,}|\s\d+\s*$')

    positions = []
    lines = pdf_text.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        for key, pat in patterns.items():
            if re.match(pat, stripped, re.IGNORECASE):
                if toc_pattern.search(stripped):
                    # TOC entry — skip, don't record a position.
                    continue
                if key not in found:
                    found.append(key)
                positions.append((i, key))
                
    if len(found) < 3:
        return {}
        
    res = {}
    positions.sort(key=lambda x: x[0])
    for idx, (line_idx, key) in enumerate(positions):
        start = line_idx + 1
        end = positions[idx+1][0] if idx + 1 < len(positions) else len(lines)
        prose = "\n".join(lines[start:end]).strip()
        if not prose:
            continue
        # Some PDFs put a Table of Contents up top — the TOC entry matches the
        # heading regex but its slice ends at the next TOC entry, producing
        # empty or stub prose. KEEP the first non-empty slice (i.e. the one
        # that actually contains body text). Subsequent matches for the same
        # key are usually the real body following a TOC; allow them to
        # overwrite ONLY when the previously-stored prose was empty.
        if key not in res or not res[key]:
            res[key] = prose

    return res

def extract_from_url(url: str) -> Dict[str, Any]:
    """Extract branding from a website.

    Fetches only validated public HTTP(S) destinations. Raw HTML supplies CSS
    color/font extraction and a stripped text corpus for voice extraction.
    """
    safe_reference = _sanitized_url(url)
    try:
        # Validate before invoking any network-capable dependency. URL fetching
        # is kept in one auditable urllib path so redirects receive the same
        # destination policy before their body is consumed.
        _validate_public_url(url)
        page_text = ""

        raw_html = ""
        # Cap raw_html size to prevent regex-quadratic blowup on multi-MB pages.
        # Note: the cap is measured in CHARACTERS (Python str length), not raw
        # bytes — for multi-byte UTF-8 the true byte count can be 2-4× higher.
        # This is intentional: the downstream regex extractors operate on the
        # decoded string, so the relevant cost is character count. The urllib
        # branch caps at 5MB of raw bytes BEFORE decode (different surface).
        MAX_RAW_HTML_CHARS = 5 * 1024 * 1024
        try:
            from urllib.request import Request
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with _open_public_url(req, timeout=15) as resp:
                # Cap the read at 5 MB. Brand-asset extraction works on the
                # head of the page (style block, logo links, page text); a
                # multi-megabyte response is almost certainly the wrong
                # asset (large PDF, video) and would consume memory before
                # the extractors run.
                raw_bytes = resp.read(5 * 1024 * 1024)
                encoding = resp.headers.get_content_charset() or "utf-8"
                raw_html = raw_bytes.decode(encoding, errors="replace")
                if len(raw_html) > MAX_RAW_HTML_CHARS:
                    raw_html = raw_html[:MAX_RAW_HTML_CHARS]
                page_text = _html_to_page_text(raw_html)
        except UrlNotPublicError:
            raise
        except Exception:
            pass

        # Best-effort: follow up to N <link rel="stylesheet"> hrefs to recover
        # font declarations that live in external CSS (a common pattern that
        # leaves URL-only extraction with empty fonts).
        external_css = _fetch_external_stylesheets(raw_html, base_url=url) if raw_html else ""

        combined_text = "\n\n".join(t for t in (page_text, raw_html, external_css) if t).strip()
        if not combined_text:
            combined_text = f"(Unable to fetch {url})"

        colors_list = ColorExtractor.extract_hex_colors(combined_text)
        logo_urls = LogoExtractor.extract_logo_urls(combined_text, base_url=url)
        fonts_list = FontExtractor.extract_fonts_from_css(combined_text)

        top_logo = sorted(logo_urls, key=lambda x: x["confidence"], reverse=True)[0] if logo_urls else None
        top_fonts = sorted(fonts_list, key=lambda x: x["confidence"], reverse=True)[:3]

        colors = _assign_color_roles_by_frequency(colors_list)

        logos = {}
        if top_logo:
            logos["primary"] = {
                "url": top_logo["url"],
                "confidence": top_logo["confidence"],
            }

        fonts = {}
        for font in top_fonts:
            if font["usage"] not in fonts:
                fonts[font["usage"]] = {
                    "name": font["font_name"],
                    "confidence": font["confidence"],
                }

        confidence_scores = {}
        for role, data in colors.items():
            confidence_scores[f"color_{role}"] = data["confidence"]
        if "primary" in logos:
            confidence_scores["logo_primary"] = logos["primary"]["confidence"]
        for usage, data in fonts.items():
            confidence_scores[f"font_{usage}"] = data["confidence"]

        voice_corpus = _voice_corpus_from_text(page_text) if page_text else {
            "text": "", "word_count": 0, "truncated": False,
        }

        typography = TypographyExtractor.extract_type_scale_from_css(combined_text)
        rounded = ShapeExtractor.extract_border_radii(combined_text)
        spacing = SpacingExtractor.extract_spacing_scale(combined_text)
        
        if typography:
            for level in typography:
                confidence_scores[f"typography.{level}"] = 0.80
        if rounded:
            confidence_scores["rounded"] = 0.70
        if spacing:
            confidence_scores["spacing"] = 0.50
            
        ret = {
            "colors": colors,
            "logos": logos,
            "fonts": fonts,
            "source": {
                "type": "url",
                "reference": safe_reference,
            },
            "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "confidence_scores": confidence_scores,
            "voice_corpus": voice_corpus,
        }
        if typography:
            ret["typography"] = typography
        if rounded:
            ret["rounded"] = rounded
        if spacing:
            ret["spacing"] = spacing
        return ret

    except Exception as e:
        return {
            "colors": {},
            "logos": {},
            "fonts": {},
            "source": {
                "type": "url",
                "reference": safe_reference,
            },
            "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "confidence_scores": {},
            "voice_corpus": {"text": "", "word_count": 0, "truncated": False},
            "error": "URL destination is not public" if isinstance(e, UrlNotPublicError) else "URL extraction failed",
        }


def extract_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """Extract branding from a PDF file (brand guide, logo, etc.).

    Reads up to 5 pages by default. Confidence is reduced to reflect
    the fragility of PDF text extraction vs canonical OOXML theme XML.
    """
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        return {
            "colors": {},
            "logos": {},
            "fonts": {},
            "source": {
                "type": "pdf",
                "reference": pdf_path,
            },
            "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "confidence_scores": {},
            "voice_corpus": dict(_EMPTY_VOICE_CORPUS),
            "error": "PDF file not found",
        }

    try:
        try:
            import pypdf
            with open(pdf_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                pdf_text = "\n".join(t for t in (page.extract_text() for page in reader.pages[:5]) if t)
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    pdf_text = "\n".join(t for t in (page.extract_text() for page in pdf.pages[:5]) if t)
            except ImportError:
                pdf_text = "(PDF text extraction unavailable)"

        colors_list = ColorExtractor.extract_hex_colors(pdf_text)
        logo_paths = LogoExtractor.extract_logo_paths(pdf_text)
        fonts_list = FontExtractor.extract_fonts_from_pdf_text(pdf_text)

        colors = {}
        color_roles = ["primary", "secondary", "accent", "background", "text"]
        for i, color in enumerate(colors_list[:3]):
            if i < len(color_roles):
                colors[color_roles[i]] = {
                    "hex": color["hex"],
                    "confidence": color["confidence"] * 0.8,
                }

        logos = {}
        if logo_paths:
            logos["primary"] = {
                "path": logo_paths[0]["path"],
                "confidence": logo_paths[0]["confidence"],
            }

        fonts = {}
        for font in fonts_list[:3]:
            if font["usage"] not in fonts:
                fonts[font["usage"]] = {
                    "name": font["font_name"],
                    "confidence": font["confidence"] * 0.9,
                }

        confidence_scores = {}
        for role, data in colors.items():
            confidence_scores[f"color_{role}"] = data["confidence"]
        if "primary" in logos:
            confidence_scores["logo_primary"] = logos["primary"]["confidence"]
        for usage, data in fonts.items():
            confidence_scores[f"font_{usage}"] = data["confidence"]

        brand_guide_prose = _extract_brand_guide_prose(pdf_text, filename=pdf_file.name)
        
        ret = {
            "colors": colors,
            "logos": logos,
            "fonts": fonts,
            "source": {
                "type": "pdf",
                "reference": pdf_path,
            },
            "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "confidence_scores": confidence_scores,
            "voice_corpus": _voice_corpus_from_text(pdf_text) if pdf_text else dict(_EMPTY_VOICE_CORPUS),
        }
        if brand_guide_prose:
            ret["brand_guide_prose"] = brand_guide_prose
        return ret

    except Exception as e:
        return {
            "colors": {},
            "logos": {},
            "fonts": {},
            "source": {
                "type": "pdf",
                "reference": pdf_path,
            },
            "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "voice_corpus": dict(_EMPTY_VOICE_CORPUS),
            "confidence_scores": {},
            "error": str(e),
        }
