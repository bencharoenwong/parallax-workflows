"""Deterministic mechanics for confirmed folder-mode brand extraction."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from .merge import cross_validate_visual, merge_drafts
from .ooxml import extract_from_docx, extract_from_pptx
from .web_pdf import _html_to_page_text, extract_from_pdf


VOICE_WORD_LIMIT = 3000
MAX_TEXT_FILE_BYTES = 1 * 1024 * 1024

_BRANDED_WORDS = ("newsletter", "quarterly", "letter", "brochure", "pitch", "deck")
_VOICE_WORDS = ("memo", "internal", "notes", "research", "whitepaper", "analysis")
_COMPLIANCE_WORDS = ("policy", "compliance", "disclosure", "terms")
_TRANSCRIPT_WORDS = ("transcript", "interview", "q&a", "call")
_OOXML_EXTENSIONS = {".pptx", ".docx", ".pdf"}
_TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".htm", ".rtf", ".eml"}
_VISUAL_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp"}
_ALLOWED_CLASSIFICATIONS = {"branded", "voice_only", "skip"}
_CLASSIFICATION_ALIASES = {"branded_visual_voice": "branded"}


class AmbiguousClassificationError(ValueError):
    """Folder extraction cannot continue until every ambiguous file is resolved."""


def _filename_has(path: Path, words: tuple[str, ...]) -> bool:
    normalized = path.stem.lower().replace("_", "-")
    return any(word in normalized for word in words)


def _automatic_classification(path: Path) -> tuple[str, str]:
    extension = path.suffix.lower()
    if extension not in _OOXML_EXTENSIONS | _TEXT_EXTENSIONS | _VISUAL_EXTENSIONS:
        return "skip", "out_of_scope"
    if extension in _VISUAL_EXTENSIONS:
        return "skip", "visual_asset"
    if _filename_has(path, _COMPLIANCE_WORDS):
        return "skip", "compliance"
    if _filename_has(path, _TRANSCRIPT_WORDS):
        return "voice_only", "transcript"
    if _filename_has(path, _VOICE_WORDS):
        return "voice_only", "internal_voice"
    if _filename_has(path, _BRANDED_WORDS):
        return "branded", "branded_marketing"
    if extension in _TEXT_EXTENSIONS:
        return "voice_only", "text_voice"
    return "ambiguous", "ambiguous"


def inventory_folder(
    folder_path: str | Path,
    classifications: Mapping[str | Path, str] | None = None,
) -> list[dict[str, Any]]:
    """Inventory one folder level and apply deterministic role classifications."""
    folder = Path(folder_path)
    if not folder.is_dir():
        raise ValueError(f"Folder not found: {folder}")
    inventoried: list[Path] = []
    for item in sorted(folder.rglob("*"), key=str):
        if not item.is_file():
            continue
        try:
            depth = len(item.relative_to(folder).parts)
        except ValueError:
            continue
        if depth > 2:
            continue
        inventoried.append(item)

    # A basename shorthand is only safe while it is unambiguous. Mapping every
    # override onto its basename let one operator disposition silently apply to
    # an identically-named file in a sibling directory, so a file the operator
    # never classified could inherit "branded" or "skip". Count basenames over
    # the files this inventory actually reports, so a deeper file the caller
    # never sees cannot make an otherwise unique shorthand look ambiguous.
    basename_counts: dict[str, int] = {}
    for item in inventoried:
        basename_counts[item.name] = basename_counts.get(item.name, 0) + 1

    # A full path always applies to exactly the file it names, and additionally
    # claims its basename while that is unique. A BARE name has no other way to
    # land, so an ambiguous one is refused outright: falling back to the
    # automatic classification would answer with keyword matching, turning
    # {"newsletter.pdf": "skip"} into "branded" without telling anyone.
    #
    # A key that reaches no inventoried file at all — a typo, or a name only a
    # file below the two inventoried levels answers to — is refused for the
    # same reason. Registering it is a silent no-op, and the file the operator
    # meant to disposition is then classified by keyword instead.
    inventoried_paths = {str(item) for item in inventoried}
    overrides: dict[str, str] = {}
    for key, value in (classifications or {}).items():
        text = str(Path(key))
        name = Path(key).name
        count = basename_counts.get(name, 0)
        unique = count <= 1
        if text != name:
            if text not in inventoried_paths and not (count == 1):
                raise AmbiguousClassificationError(
                    f"{key} names no file in the two inventoried levels of "
                    f"{folder}; check the path"
                )
            overrides[text] = value
            if unique:
                overrides.setdefault(name, value)
            continue
        if count == 0:
            raise AmbiguousClassificationError(
                f"{name} names no file in the two inventoried levels of "
                f"{folder}; check the name"
            )
        if not unique:
            raise AmbiguousClassificationError(
                f"{name} matches {count} files; supply a full path"
            )
        overrides[name] = value

    inventory: list[dict[str, Any]] = []
    for path in inventoried:
        automatic, role = _automatic_classification(path)
        classification = overrides.get(str(path), overrides.get(path.name, automatic))
        classification = _CLASSIFICATION_ALIASES.get(classification, classification)
        if classification not in _ALLOWED_CLASSIFICATIONS | {"ambiguous"}:
            raise ValueError(
                f"Unsupported folder classification for {path.name}: {classification}"
            )
        inventory.append(
            {
                "path": str(path),
                "extension": path.suffix.lower(),
                "size": path.stat().st_size,
                "role": role,
                "classification": classification,
            }
        )
    return inventory


def _read_voice_text(path: Path) -> str:
    if path.stat().st_size > MAX_TEXT_FILE_BYTES:
        raise ValueError(f"Text voice file exceeds {MAX_TEXT_FILE_BYTES} bytes: {path.name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        return _html_to_page_text(text)
    if path.suffix.lower() == ".eml":
        text = re.split(r"\r?\n\r?\n", text, maxsplit=1)[-1]
        return _html_to_page_text(text) if "<" in text and ">" in text else text
    if path.suffix.lower() == ".rtf":
        return re.sub(r"\\[a-z]+\d* ?|[{}]", " ", text, flags=re.IGNORECASE)
    return text


def _bounded_voice(parts: list[tuple[str, str, bool]]) -> dict[str, Any]:
    retained_parts: list[str] = []
    by_source: list[dict[str, Any]] = []
    remaining = VOICE_WORD_LIMIT
    available_word_count = sum(len(text.split()) for _, text, _ in parts)
    truncated = any(source_truncated for _, _, source_truncated in parts)
    for reference, text, source_truncated in parts:
        words = text.split()
        kept = words[:remaining]
        if kept:
            retained_parts.append(" ".join(kept))
            by_source.append({"reference": reference, "word_count": len(kept)})
        remaining -= len(kept)
        if remaining == 0:
            break
    text = "\n\n".join(retained_parts)
    return {
        "text": text,
        "word_count": len(text.split()),
        "truncated": truncated or available_word_count > VOICE_WORD_LIMIT,
        "by_source": by_source,
    }


def extract_from_folder(
    folder_path: str | Path,
    classifications: Mapping[str | Path, str] | None = None,
) -> Dict[str, Any]:
    """Execute folder extraction after deterministic or operator classifications."""
    folder = Path(folder_path)
    inventory = inventory_folder(folder, classifications)
    ambiguous = [
        Path(item["path"]).name
        for item in inventory
        if item["classification"] == "ambiguous"
    ]
    if ambiguous:
        raise AmbiguousClassificationError(
            "Operator disposition required for: " + ", ".join(ambiguous)
        )

    extractors: dict[str, Callable[[str], Dict[str, Any]]] = {
        ".pptx": extract_from_pptx,
        ".docx": extract_from_docx,
        ".pdf": extract_from_pdf,
    }
    visual_drafts: list[Dict[str, Any]] = []
    voice_parts: list[tuple[str, str, bool]] = []
    logo_assets: list[Path] = []
    extraction_errors: list[dict[str, str]] = []
    for item in inventory:
        classification = item["classification"]
        if classification == "skip":
            continue
        path = Path(item["path"])
        if path.suffix.lower() in extractors:
            draft = extractors[path.suffix.lower()](str(path))
            if draft.get("error"):
                extraction_errors.append(
                    {"reference": str(path), "error": str(draft["error"])}
                )
                continue
            corpus = draft.get("voice_corpus") or {}
            if classification == "branded":
                visual_drafts.append(draft)
            else:
                voice_parts.append(
                    (str(path), corpus.get("text", ""), bool(corpus.get("truncated")))
                )
        elif path.suffix.lower() in _VISUAL_EXTENSIONS:
            if classification != "branded":
                raise ValueError(
                    f"Visual asset cannot be classified as {classification}: {path.name}"
                )
            logo_assets.append(path)
        elif path.suffix.lower() in _TEXT_EXTENSIONS:
            try:
                voice_parts.append((str(path), _read_voice_text(path), False))
            except (OSError, ValueError) as exc:
                extraction_errors.append(
                    {"reference": str(path), "error": str(exc)}
                )

    if visual_drafts:
        draft = merge_drafts(visual_drafts)
        existing_parts = []
        corpus = draft.get("voice_corpus") or {}
        for source in corpus.get("by_source", []):
            reference = source["reference"]
            matching = next(
                (d for d in visual_drafts if d.get("source", {}).get("reference") == reference),
                None,
            )
            if matching:
                matching_corpus = matching.get("voice_corpus") or {}
                existing_parts.append(
                    (
                        reference,
                        matching_corpus.get("text", ""),
                        bool(matching_corpus.get("truncated")),
                    )
                )
        if not existing_parts and corpus.get("text"):
            existing_parts.append(
                (
                    draft.get("source", {}).get("reference", str(folder)),
                    corpus["text"],
                    bool(corpus.get("truncated")),
                )
            )
        bounded_corpus = _bounded_voice(existing_parts + voice_parts)
        bounded_corpus["truncated"] = (
            bounded_corpus["truncated"] or bool(corpus.get("truncated"))
        )
        draft["voice_corpus"] = bounded_corpus
        if len(visual_drafts) > 1:
            validation = cross_validate_visual(visual_drafts)
            draft["multi_source"] = {
                "sources": [
                    d["source"]
                    for d in sorted(
                        visual_drafts,
                        key=lambda item: item["source"]["reference"],
                    )
                ],
                **validation,
            }
    elif voice_parts or logo_assets:
        source_type = "folder-voice-only" if not logo_assets else "multi"
        draft = {
            "colors": {},
            "logos": {},
            "fonts": {},
            "source": {"type": source_type, "reference": str(folder)},
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "confidence_scores": {},
            "voice_corpus": _bounded_voice(voice_parts),
        }
    else:
        if extraction_errors:
            details = "; ".join(
                f"{Path(item['reference']).name}: {item['error']}"
                for item in extraction_errors
            )
            raise ValueError(f"Folder extraction failed: {details}")
        raise ValueError("Folder contains no confirmed brand inputs")

    logo_roles: dict[str, list[Path]] = {}
    for path in logo_assets:
        is_favicon = path.suffix.lower() == ".ico" or "favicon" in path.stem.lower()
        role = "favicon" if is_favicon else "primary"
        logo_roles.setdefault(role, []).append(path)
    for role, paths in logo_roles.items():
        if len(paths) > 1:
            names = ", ".join(path.name for path in paths)
            raise AmbiguousClassificationError(
                f"Operator must select one {role} logo: {names}"
            )
        draft["logos"][role] = {
            "local_path": str(paths[0]),
            "confidence": 1.0,
        }
        draft["confidence_scores"][f"logo_{role}"] = 1.0

    if extraction_errors:
        draft["extraction_errors"] = extraction_errors
    draft["folder_inventory"] = inventory

    # Image files auto-classify to "skip" so the operator, not the filename,
    # decides which asset is the logo. Left implicit, a folder holding an
    # obvious logo-primary.png produced logos={} with nothing in the draft
    # saying a candidate had been seen and dropped. Surface the unclaimed
    # candidates so the confirmation gate can prompt for a disposition.
    claimed = {
        str(role_paths[0])
        for role_paths in logo_roles.values()
    }
    unclaimed = [
        item["path"]
        for item in inventory
        if item["role"] == "visual_asset"
        and item["classification"] == "skip"
        and item["path"] not in claimed
    ]
    if unclaimed:
        draft["logo_candidates"] = unclaimed
    return draft
