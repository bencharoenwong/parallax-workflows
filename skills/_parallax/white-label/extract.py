"""Brand asset extraction from flexible sources: URLs, PDFs, wizard intake."""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse


class ColorExtractor:
    """Extract colors from text via pattern matching."""

    @staticmethod
    def extract_hex_colors(text: str) -> List[Dict[str, Any]]:
        """Find hex color patterns (#RGB, #RRGGBB, rgb(...)) in text.

        Returns: [{"hex": "#FF5733", "confidence": 0.95}, ...]
        """
        colors = []

        # Match 6-digit hex colors (#RRGGBB)
        for match in re.finditer(r'#[0-9A-Fa-f]{6}\b', text):
            colors.append({
                "hex": match.group(0).upper(),
                "confidence": 0.95,
            })

        # Match 3-digit hex colors (#RGB)
        for match in re.finditer(r'#[0-9A-Fa-f]{3}\b', text):
            colors.append({
                "hex": match.group(0).upper(),
                "confidence": 0.95,
            })

        # Match rgb(r, g, b) patterns
        for match in re.finditer(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', text):
            r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            colors.append({
                "hex": hex_color,
                "confidence": 0.85,
            })

        return colors


class LogoExtractor:
    """Extract logo URLs and paths from text and HTML."""

    @staticmethod
    def extract_logo_urls(text: str, base_url: str = "") -> List[Dict[str, Any]]:
        """Find logo image URLs in text or HTML.

        Returns: [{"url": str, "alt_text": str, "confidence": float}, ...]
        """
        logos = []
        seen_urls = set()

        # Match markdown image syntax: ![alt](url)
        for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', text):
            alt_text = match.group(1)
            url = match.group(2)

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Calculate confidence based on keywords
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

        # Match bare URLs containing logo/brand keywords
        for match in re.finditer(r'https?://[^\s]+(?:logo|brand|icon)[^\s]*\.(?:png|svg|jpg|jpeg|gif)', text, re.IGNORECASE):
            url = match.group(0)
            if url not in seen_urls:
                seen_urls.add(url)
                logos.append({
                    "url": url,
                    "alt_text": "logo",
                    "confidence": 0.9,
                })

        # Match any image URLs
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

        # Match file paths with logo/brand/icon/assets keywords (higher confidence)
        for match in re.finditer(r'/[^\s]*(?:logo|brand|icon|assets)[^\s]*\.(?:png|svg|jpg|jpeg|gif)', text, re.IGNORECASE):
            path = match.group(0)
            if path not in seen_paths:
                seen_paths.add(path)
                paths.append({
                    "path": path,
                    "confidence": 0.8,
                })

        # Match any path-like strings with image extensions (lower confidence)
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

        # Match font-family declarations
        for match in re.finditer(r'font-family\s*:\s*([^;,\n}]+)', text):
            font_decl = match.group(1).strip()
            font_name = font_decl.split(',')[0].strip(' "\'')

            # Determine usage from selector context
            usage = "body"  # default

            # Look backward in text to find the selector
            start_pos = max(0, match.start() - 200)
            selector_text = text[start_pos:match.start()].lower()

            if any(h in selector_text for h in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header']):
                usage = "header"
            elif any(m in selector_text for m in ['mono', 'code', 'pre']):
                usage = "monospace"
            elif 'body' in selector_text:
                usage = "body"

            fonts.append({
                "font_name": font_name,
                "usage": usage,
                "confidence": 0.85,
            })

        return fonts

    @staticmethod
    def extract_fonts_from_pdf_text(text: str) -> List[Dict[str, Any]]:
        """Guess fonts from OCR'd PDF text or explicit font mentions.

        Returns: [{"font_name": str, "usage": "header|body|monospace", "confidence": float}, ...]
        """
        fonts = []

        # Pattern: "Font: FontName" or "uses FontName" or "FontName font"
        font_patterns = [
            r'(?:font|family|typeface):\s*([A-Z][A-Za-z\s]+?)(?:\s*(?:,|for|in|as)|$)',
            r'(?:headers?|body|text)\s+(?:uses?|in)\s+([A-Z][A-Za-z\s]+?)(?:\s*(?:,|;)|$)',
        ]

        for pattern in font_patterns:
            for match in re.finditer(pattern, text):
                font_name = match.group(1).strip()

                # Determine usage from context
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

    Returns draft config with colors, logos, fonts, source, extracted_at, and confidence_scores.
    """
    try:
        # Attempt to fetch URL via defuddle or fallback
        try:
            from subprocess import run, PIPE
            result = run(
                ["defuddle", "parse", url, "--md"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            page_text = result.stdout if result.returncode == 0 else ""
        except (FileNotFoundError, Exception):
            # Fallback: try to use scrapling
            try:
                from scrapling.fetchers import Fetcher
                page = Fetcher.get(url, stealthy_headers=True)
                page_text = page.get_all_text(separator='\n', strip=True)
            except Exception:
                page_text = ""

        if not page_text:
            page_text = f"(Unable to fetch {url})"

        # Extract colors
        colors_list = ColorExtractor.extract_hex_colors(page_text)

        # Extract logos
        logo_urls = LogoExtractor.extract_logo_urls(page_text, base_url=url)

        # Extract fonts
        fonts_list = FontExtractor.extract_fonts_from_css(page_text)

        # Pick top assets by confidence
        top_colors = sorted(colors_list, key=lambda x: x["confidence"], reverse=True)[:3]
        top_logo = sorted(logo_urls, key=lambda x: x["confidence"], reverse=True)[0] if logo_urls else None
        top_fonts = sorted(fonts_list, key=lambda x: x["confidence"], reverse=True)[:3]

        # Build colors dict
        colors = {}
        color_roles = ["primary", "secondary", "accent", "background", "text"]
        for i, color in enumerate(top_colors):
            if i < len(color_roles):
                colors[color_roles[i]] = {
                    "hex": color["hex"],
                    "confidence": color["confidence"],
                }

        # Build logos dict
        logos = {}
        if top_logo:
            logos["primary"] = {
                "url": top_logo["url"],
                "confidence": top_logo["confidence"],
            }

        # Build fonts dict
        fonts = {}
        for font in top_fonts:
            if font["usage"] not in fonts:
                fonts[font["usage"]] = {
                    "name": font["font_name"],
                    "confidence": font["confidence"],
                }

        # Build confidence_scores
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
                "type": "url",
                "reference": url,
            },
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "confidence_scores": confidence_scores,
        }

    except Exception as e:
        # Graceful degradation: return empty config
        return {
            "colors": {},
            "logos": {},
            "fonts": {},
            "source": {
                "type": "url",
                "reference": url,
            },
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "confidence_scores": {},
            "error": str(e),
        }


def extract_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """Extract branding from a PDF file (brand guide, logo, etc.).

    Returns draft config with colors, logos, fonts, source, extracted_at, and confidence_scores.
    """
    pdf_file = Path(pdf_path)

    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        # Try to extract text from PDF
        try:
            import pypdf
            with open(pdf_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                pdf_text = "\n".join(page.extract_text() for page in reader.pages[:5])
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    pdf_text = "\n".join(page.extract_text() for page in pdf.pages[:5])
            except ImportError:
                pdf_text = "(PDF text extraction unavailable)"

        # Extract colors
        colors_list = ColorExtractor.extract_hex_colors(pdf_text)

        # Extract logos (limited in PDFs)
        logo_paths = LogoExtractor.extract_logo_paths(pdf_text)

        # Extract fonts
        fonts_list = FontExtractor.extract_fonts_from_pdf_text(pdf_text)

        # Build colors dict (lower confidence for PDF)
        colors = {}
        color_roles = ["primary", "secondary", "accent", "background", "text"]
        for i, color in enumerate(colors_list[:3]):
            if i < len(color_roles):
                colors[color_roles[i]] = {
                    "hex": color["hex"],
                    "confidence": color["confidence"] * 0.8,  # Reduce confidence for PDF extraction
                }

        # Build logos dict
        logos = {}
        if logo_paths:
            logos["primary"] = {
                "path": logo_paths[0]["path"],
                "confidence": logo_paths[0]["confidence"],
            }

        # Build fonts dict
        fonts = {}
        for font in fonts_list[:3]:
            if font["usage"] not in fonts:
                fonts[font["usage"]] = {
                    "name": font["font_name"],
                    "confidence": font["confidence"] * 0.9,  # Reduce confidence for PDF extraction
                }

        # Build confidence_scores
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
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "confidence_scores": confidence_scores,
        }

    except FileNotFoundError:
        raise
    except Exception as e:
        # Graceful degradation
        return {
            "colors": {},
            "logos": {},
            "fonts": {},
            "source": {
                "type": "pdf",
                "reference": pdf_path,
            },
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "confidence_scores": {},
            "error": str(e),
        }


def extract_from_wizard() -> Dict[str, Any]:
    """Guided intake via interactive questions.

    Returns draft config with confidence 1.0 for all fields (user is the source).
    """
    # This is a placeholder; full implementation requires AskUserQuestion
    # and will be completed during SKILL.md orchestration phase
    return {
        "colors": {},
        "logos": {},
        "fonts": {},
        "source": {
            "type": "wizard",
        },
        "extracted_at": datetime.utcnow().isoformat() + "Z",
        "confidence_scores": {},
        "note": "Wizard extraction requires interactive input; implement in SKILL.md orchestration",
    }
