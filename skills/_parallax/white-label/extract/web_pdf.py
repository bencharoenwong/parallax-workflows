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

    Security note (SSRF surface):
        This function fetches arbitrary URLs harvested from `<link rel=stylesheet>`
        elements in the supplied HTML. Run against a hostile or compromised brand
        page, the href could point at internal endpoints (e.g.
        `http://169.254.169.254/...` cloud metadata, or intranet probes). The
        documented use case is operator-supplied URLs run from a personal laptop,
        which is acceptable. If this helper is ever wrapped in a server endpoint
        or shared-session context, the caller MUST restrict outbound hosts to a
        public allowlist before invoking it.
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



class TypographyExtractor:
    @staticmethod
    def extract_type_scale_from_css(css_text: str) -> Dict[str, Dict[str, Any]]:
        import re
        css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
        scale = {}
        pattern = re.compile(r'(?:\b|\.)(h[1-6]|body(?:-md)?|p|code|pre)\b[^{}]*\{([^}]+)\}', re.IGNORECASE)
        sel_map = {
            "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h5",
            "body": "body-md", "p": "body-md", "body-md": "body-md",
            "code": "code", "pre": "code"
        }
        for match in pattern.finditer(css_text):
            sel = match.group(1).lower()
            if sel not in sel_map: continue
            level = sel_map[sel]
            if level in scale: continue 
            
            block = match.group(2)
            style = {
                "fontWeight": 400,
                "lineHeight": "1.5",
                "letterSpacing": "0"
            }
            
            fs_m = re.search(r'font-size\s*:\s*([^;]+)', block, re.IGNORECASE)
            fw_m = re.search(r'font-weight\s*:\s*([^;]+)', block, re.IGNORECASE)
            lh_m = re.search(r'line-height\s*:\s*([^;]+)', block, re.IGNORECASE)
            ls_m = re.search(r'letter-spacing\s*:\s*([^;]+)', block, re.IGNORECASE)
            ff_m = re.search(r'font-family\s*:\s*([^;]+)', block, re.IGNORECASE)
            
            if not any([fs_m, fw_m, lh_m, ls_m, ff_m]): continue
            
            if fs_m: style["fontSize"] = fs_m.group(1).strip()
            if fw_m: 
                val = fw_m.group(1).strip()
                if val.isdigit(): style["fontWeight"] = int(val)
                elif val.lower() == "bold": style["fontWeight"] = 700
            if lh_m: style["lineHeight"] = lh_m.group(1).strip()
            if ls_m: style["letterSpacing"] = ls_m.group(1).strip()
            if ff_m: style["fontFamily"] = ff_m.group(1).strip().split(',')[0].strip(' "\'')
            
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
                    if num == 0: continue
                    unit = m.group(2).lower()
                    if unit == "rem": num *= 16
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
    patterns = {
        "overview": r'^(?:\d+\.\s*)?Overview\b',
        "colors": r'^(?:\d+\.\s*)?Colors\b',
        "typography": r'^(?:\d+\.\s*)?Typography\b',
        "dos_and_donts": r'^(?:\d+\.\s*)?Do\'s and Don\'ts\b'
    }
    
    positions = []
    lines = pdf_text.split('\n')
    for i, line in enumerate(lines):
        for key, pat in patterns.items():
            if re.match(pat, line.strip(), re.IGNORECASE):
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
        if prose:
            res[key] = prose
            
    return res

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
        # Cap raw_html size to prevent regex-quadratic blowup on multi-MB pages.
        # Note: the cap is measured in CHARACTERS (Python str length), not raw
        # bytes — for multi-byte UTF-8 the true byte count can be 2-4× higher.
        # This is intentional: the downstream regex extractors operate on the
        # decoded string, so the relevant cost is character count. The urllib
        # branch caps at 5MB of raw bytes BEFORE decode (different surface).
        MAX_RAW_HTML_CHARS = 5 * 1024 * 1024
        try:
            from scrapling.fetchers import Fetcher
            page = Fetcher.get(url, stealthy_headers=True, follow_redirects=True)
            raw_html = getattr(page, "html_content", "") or str(page)
            if isinstance(raw_html, str) and len(raw_html) > MAX_RAW_HTML_CHARS:
                raw_html = raw_html[:MAX_RAW_HTML_CHARS]
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
                "reference": url,
            },
            "extracted_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "confidence_scores": confidence_scores,
            "voice_corpus": voice_corpus,
        }
        if typography: ret["typography"] = typography
        if rounded: ret["rounded"] = rounded
        if spacing: ret["spacing"] = spacing
        return ret

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
