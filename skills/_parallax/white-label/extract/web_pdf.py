"""URL and PDF extraction.

URL path: defuddle for clean text (voice corpus + logo URLs in markdown) +
scrapling/urllib for raw HTML (CSS color/font extraction). Both passes are
best-effort; merged corpus drives the regex extractors.

PDF path: pypdf or pdfplumber for text extraction; regex extractors run
against the resulting text. Confidence is reduced to reflect the fragility
of PDF text extraction vs canonical OOXML theme XML.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .colors import ColorExtractor, _assign_color_roles_by_frequency
from .voice import _voice_corpus_from_text


_EMPTY_VOICE_CORPUS = {"text": "", "word_count": 0, "truncated": False}

# Caps for external-stylesheet following: total link follows + per-fetch size +
# overall budget. URL extraction is best-effort; runaway fetching against a
# fanned-out site is the wrong trade.
_MAX_STYLESHEET_LINKS = 5
_STYLESHEET_READ_CAP = 1 * 1024 * 1024  # 1 MB per stylesheet
_STYLESHEET_TOTAL_TIMEOUT_SECONDS = 8


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
            from urllib.request import Request, urlopen
            req = Request(absolute, headers={"User-Agent": "Mozilla/5.0"})
            remaining = max(1, int(deadline - time.monotonic()))
            with urlopen(req, timeout=remaining) as resp:
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


def extract_from_url(url: str) -> Dict[str, Any]:
    """Extract branding from a website.

    Two passes: defuddle for clean markdown (voice corpus + emitted text),
    scrapling/urllib for raw HTML (CSS color/font extraction). Both are
    best-effort; merged text drives the regex extractors.
    """
    try:
        page_text = ""
        try:
            from subprocess import run
            result = run(
                ["defuddle", "parse", url, "--md"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            page_text = result.stdout if result.returncode == 0 else ""
        except (FileNotFoundError, Exception):
            pass

        raw_html = ""
        try:
            from scrapling.fetchers import Fetcher
            page = Fetcher.get(url, stealthy_headers=True, follow_redirects=True)
            raw_html = getattr(page, "html_content", "") or str(page)
            if not page_text:
                page_text = page.get_all_text(separator="\n", strip=True)
        except Exception:
            try:
                from urllib.request import Request, urlopen
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=15) as resp:
                    # Cap the read at 5 MB. Brand-asset extraction works on the
                    # head of the page (style block, logo links, page text); a
                    # multi-megabyte response is almost certainly the wrong
                    # asset (large PDF, video) and would consume memory before
                    # the extractors run.
                    raw_bytes = resp.read(5 * 1024 * 1024)
                    encoding = resp.headers.get_content_charset() or "utf-8"
                    raw_html = raw_bytes.decode(encoding, errors="replace")
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

        return {
            "colors": colors,
            "logos": logos,
            "fonts": fonts,
            "source": {
                "type": "url",
                "reference": url,
            },
            "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "confidence_scores": confidence_scores,
            "voice_corpus": voice_corpus,
        }

    except Exception as e:
        return {
            "colors": {},
            "logos": {},
            "fonts": {},
            "source": {
                "type": "url",
                "reference": url,
            },
            "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "confidence_scores": {},
            "voice_corpus": {"text": "", "word_count": 0, "truncated": False},
            "error": str(e),
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

        return {
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
