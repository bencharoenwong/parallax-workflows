"""Adversarial coverage for folder and multi-source brand ingestion."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import types
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from extract import (  # noqa: E402
    AmbiguousClassificationError,
    UnresolvedMismatchError,
    extract_from_folder,
    extract_from_pdf,
    merge_drafts,
    merge_resolved_drafts,
)
from extract.voice import _voice_corpus_from_text  # noqa: E402


def _draft(reference: str, color: str, words: list[str], confidence: float = 0.9) -> dict:
    return {
        "colors": {"primary": {"hex": color, "confidence": confidence}},
        "logos": {},
        "fonts": {},
        "confidence_scores": {},
        "source": {"type": "docx", "reference": reference},
        "extracted_at": "2026-01-01T00:00:00Z",
        "voice_corpus": {
            "text": " ".join(words),
            "word_count": len(words),
            "truncated": False,
        },
    }


def test_merge_caps_retained_voice_and_reports_exact_count():
    first = _draft("a.docx", "#112233", [f"a{i}" for i in range(2000)])
    second = _draft("b.docx", "#112233", [f"b{i}" for i in range(1001)])

    merged = merge_drafts([first, second])

    assert len(merged["voice_corpus"]["text"].split()) == 3000
    assert merged["voice_corpus"]["word_count"] == 3000
    assert merged["voice_corpus"]["truncated"] is True
    assert merged["voice_corpus"]["by_source"] == [
        {"reference": "a.docx", "word_count": 2000},
        {"reference": "b.docx", "word_count": 1000},
    ]


@pytest.mark.parametrize(
    ("size", "expected_count", "expected_truncated"),
    [(3000, 3000, False), (3001, 3000, True)],
)
def test_single_source_voice_count_describes_retained_text(
    size, expected_count, expected_truncated
):
    corpus = _voice_corpus_from_text(" ".join(f"word{i}" for i in range(size)))

    assert len(corpus["text"].split()) == expected_count
    assert corpus["word_count"] == expected_count
    assert corpus["truncated"] is expected_truncated


def test_resolved_merge_is_stable_across_input_order():
    alpha = _draft("alpha.docx", "#112233", ["alpha"])
    beta = _draft("beta.docx", "#AABBCC", ["beta"])
    resolutions = {"colors.primary": "beta.docx"}

    forward = merge_resolved_drafts([alpha, beta], resolutions)
    reverse = merge_resolved_drafts([beta, alpha], resolutions)

    assert forward == reverse
    assert forward["colors"]["primary"]["hex"] == "#AABBCC"
    assert forward["multi_source"]["resolutions"] == resolutions
    assert [source["reference"] for source in forward["multi_source"]["sources"]] == [
        "alpha.docx",
        "beta.docx",
    ]


def test_visual_mismatch_requires_source_attributed_resolution():
    alpha = _draft("alpha.docx", "#112233", [])
    beta = _draft("beta.docx", "#AABBCC", [])

    with pytest.raises(UnresolvedMismatchError, match="colors.primary"):
        merge_resolved_drafts([alpha, beta], {})

    with pytest.raises(ValueError, match="unknown source"):
        merge_resolved_drafts(
            [alpha, beta], {"colors.primary": "unrelated.docx"}
        )


def test_mixed_folder_classification_controls_visual_and_voice(tmp_path, monkeypatch):
    folder = tmp_path / "synthetic-brand"
    folder.mkdir()
    newsletter = folder / "quarterly-newsletter.docx"
    memo = folder / "internal-research-memo.docx"
    compliance = folder / "compliance-terms.txt"
    transcript = folder / "manager-interview.txt"
    logo = folder / "primary-logo.png"
    skipped = folder / "holdings.csv"
    for path in (newsletter, memo):
        path.write_bytes(b"placeholder")
    compliance.write_text("Legal boilerplate must stay out.", encoding="utf-8")
    transcript.write_text("HOST: How do you invest? MANAGER: Patiently.", encoding="utf-8")
    logo.write_bytes(b"synthetic image placeholder")
    skipped.write_text("symbol,weight", encoding="utf-8")

    calls: list[str] = []

    def fake_docx(path: str) -> dict:
        calls.append(Path(path).name)
        if "newsletter" in path:
            return _draft(path, "#123456", ["measured", "outlook"])
        return _draft(path, "#FEDCBA", ["deep", "research"])

    monkeypatch.setattr("extract.folder.extract_from_docx", fake_docx)
    result = extract_from_folder(folder, {logo: "branded"})

    assert calls == ["internal-research-memo.docx", "quarterly-newsletter.docx"]
    assert result["colors"]["primary"]["hex"] == "#123456"
    assert result["logos"]["primary"] == {
        "local_path": str(logo),
        "confidence": 1.0,
    }
    voice = result["voice_corpus"]["text"]
    assert "measured outlook" in voice
    assert "deep research" in voice
    assert "Patiently" in voice
    assert "Legal boilerplate" not in voice
    assert "symbol,weight" not in voice
    roles = {
        Path(item["path"]).name: item["classification"]
        for item in result["folder_inventory"]
    }
    assert roles["quarterly-newsletter.docx"] == "branded"
    assert roles["internal-research-memo.docx"] == "voice_only"
    assert roles["compliance-terms.txt"] == "skip"
    assert roles["manager-interview.txt"] == "voice_only"
    assert roles["primary-logo.png"] == "branded"
    assert roles["holdings.csv"] == "skip"


def test_operator_classification_alias_drives_callable_folder_extraction(
    tmp_path, monkeypatch
):
    folder = tmp_path / "synthetic-brand"
    folder.mkdir()
    material = folder / "material.docx"
    material.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "extract.folder.extract_from_docx",
        lambda path: _draft(path, "#123456", ["confirmed", "copy"]),
    )

    result = extract_from_folder(
        folder, {material: "branded_visual_voice"}
    )

    assert result["colors"]["primary"]["hex"] == "#123456"
    assert result["voice_corpus"]["text"] == "confirmed copy"
    assert result["folder_inventory"][0]["classification"] == "branded"


def test_confirmed_branded_text_is_retained_as_voice(tmp_path):
    folder = tmp_path / "synthetic-brand"
    folder.mkdir()
    material = folder / "client-copy.txt"
    material.write_text("Patient capital supports durable growth.", encoding="utf-8")

    result = extract_from_folder(folder, {material: "branded"})

    assert result["source"]["type"] == "folder-voice-only"
    assert result["voice_corpus"]["text"] == (
        "Patient capital supports durable growth."
    )


def test_folder_preserves_truncation_when_a_later_source_is_fully_dropped(
    tmp_path, monkeypatch
):
    folder = tmp_path / "synthetic-brand"
    folder.mkdir()
    first = folder / "deck-a.docx"
    second = folder / "deck-b.docx"
    first.write_bytes(b"placeholder")
    second.write_bytes(b"placeholder")

    def fake_docx(path: str) -> dict:
        words = [f"a{i}" for i in range(3000)] if path == str(first) else ["last"]
        return _draft(path, "#123456", words)

    monkeypatch.setattr("extract.folder.extract_from_docx", fake_docx)

    result = extract_from_folder(folder)

    assert result["voice_corpus"]["word_count"] == 3000
    assert len(result["voice_corpus"]["text"].split()) == 3000
    assert result["voice_corpus"]["truncated"] is True


def test_folder_preserves_structured_extraction_errors_with_partial_results(
    tmp_path, monkeypatch
):
    folder = tmp_path / "synthetic-brand"
    folder.mkdir()
    good = folder / "deck-good.docx"
    bad = folder / "deck-bad.docx"
    good.write_bytes(b"placeholder")
    bad.write_bytes(b"placeholder")

    def fake_docx(path: str) -> dict:
        if path == str(bad):
            return {
                **_draft(path, "#000000", []),
                "error": "malformed OOXML",
            }
        return _draft(path, "#123456", ["usable"])

    monkeypatch.setattr("extract.folder.extract_from_docx", fake_docx)

    result = extract_from_folder(folder)

    assert result["colors"]["primary"]["hex"] == "#123456"
    assert result["extraction_errors"] == [
        {"reference": str(bad), "error": "malformed OOXML"}
    ]


def test_unresolved_ambiguous_file_stops_before_extraction(tmp_path, monkeypatch):
    folder = tmp_path / "synthetic-brand"
    folder.mkdir()
    (folder / "material.docx").write_bytes(b"placeholder")
    calls: list[str] = []
    monkeypatch.setattr(
        "extract.folder.extract_from_docx", lambda path: calls.append(path)
    )

    with pytest.raises(AmbiguousClassificationError, match="material.docx"):
        extract_from_folder(folder)

    assert calls == []


def test_voice_only_ooxml_never_supplies_visual_tokens(tmp_path, monkeypatch):
    folder = tmp_path / "synthetic-brand"
    folder.mkdir()
    memo = folder / "internal-memo.docx"
    memo.write_bytes(b"placeholder")
    monkeypatch.setattr(
        "extract.folder.extract_from_docx",
        lambda path: _draft(path, "#DEADBE", ["patient", "capital"]),
    )

    result = extract_from_folder(folder)

    assert result["source"]["type"] == "folder-voice-only"
    assert result["colors"] == {}
    assert result["fonts"] == {}
    assert result["logos"] == {}
    assert result["voice_corpus"]["text"] == "patient capital"


@pytest.mark.parametrize("kind", ["pptx", "docx"])
def test_oversized_ooxml_member_returns_structured_error(
    tmp_path, monkeypatch, kind
):
    member_limit = 32
    monkeypatch.setattr(
        "extract.ooxml.MAX_OOXML_XML_MEMBER_BYTES", member_limit
    )

    path = tmp_path / f"oversized.{kind}"
    member = "ppt/theme/theme1.xml" if kind == "pptx" else "word/theme/theme1.xml"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, b"x" * (member_limit + 1))

    from extract import extract_from_docx, extract_from_pptx

    result = (extract_from_pptx if kind == "pptx" else extract_from_docx)(str(path))

    assert result["colors"] == {}
    assert result["voice_corpus"]["word_count"] == 0
    assert "OOXML XML member exceeds" in result["error"]


def test_malformed_ooxml_returns_structured_error(tmp_path):
    path = tmp_path / "malformed.docx"
    path.write_bytes(b"not a zip archive")

    from extract import extract_from_docx

    result = extract_from_docx(str(path))

    assert result["colors"] == {}
    assert result["voice_corpus"]["word_count"] == 0
    assert result["error"]


def test_malformed_ooxml_xml_returns_structured_error(tmp_path):
    path = tmp_path / "malformed-theme.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/theme/theme1.xml", b"<a:theme")

    from extract import extract_from_docx

    result = extract_from_docx(str(path))

    assert result["colors"] == {}
    assert result["voice_corpus"]["word_count"] == 0
    assert result["error"]


def test_pdf_uses_settled_ten_page_limit(tmp_path, monkeypatch):
    path = tmp_path / "guide.pdf"
    path.write_bytes(b"synthetic")
    seen_slices: list[slice] = []

    class Pages:
        def __getitem__(self, item):
            seen_slices.append(item)
            return [
                types.SimpleNamespace(extract_text=lambda i=i: f"page{i}")
                for i in range(item.stop)
            ]

    fake_pypdf = types.SimpleNamespace(
        PdfReader=lambda stream: types.SimpleNamespace(pages=Pages())
    )
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    result = extract_from_pdf(str(path))

    assert [item.stop for item in seen_slices] == [10]
    assert "page9" in result["voice_corpus"]["text"]


def test_pdf_page_limit_matches_onboarding_instructions():
    white_label = Path(__file__).parent.parent
    skill_text = (
        white_label.parent.parent / "parallax-white-label-onboard" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "Reads up to 10 pages by default." in skill_text
    assert "Reads up to 5 pages by default." not in skill_text


def test_extract_package_imports_from_unrelated_working_directory(tmp_path):
    white_label = Path(__file__).parent.parent
    env = os.environ.copy()
    env["PYTHONPATH"] = str(white_label)
    command = [
        sys.executable,
        "-c",
        (
            "import json; import extract; import extract.folder; import extract.merge; "
            "import extract.ooxml; import extract.web_pdf; "
            "corpus = extract._voice_corpus_from_text('one two'); "
            "print(json.dumps({'exports': sorted(extract.__all__), 'corpus': corpus}))"
        ),
    ]

    completed = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "extract_from_folder" in payload["exports"]
    assert payload["corpus"] == {
        "text": "one two",
        "word_count": 2,
        "truncated": False,
    }
