"""End-to-end tests for the version-chain evolution surface.

Covers the version_id / parent_version_id / view_id lifecycle that lets
auditors walk the history of a single house-view family across maker
saves, /parallax-load-house-view --edit cycles, and judge runs.

The /parallax-load-house-view skill is LLM-orchestrated (no Python entry
point), so the "edit save" step is simulated by writing the artifacts
the load skill's Step 4 would write — same primitives, same audit row
shape. This mirrors the pattern in test_uninstall.py's
``run_load_house_view_against_fixture`` helper.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import rfc8785
import yaml

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
MAKER_DIR = REPO / "skills" / "parallax-make-house-view"
JUDGE_DIR = REPO / "skills" / "parallax-judge-house-view"
SHARED_DIR = REPO / "skills" / "_parallax" / "house-view"
MAKER_FIXTURES = MAKER_DIR / "tests" / "fixtures"

for _p in (SHARED_DIR, MAKER_DIR, JUDGE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_chain  # noqa: E402
import gate_present  # noqa: E402
import judge  # noqa: E402
import maker  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (duplicated inline from test_e2e.py — pytest's conftest-collision
# pattern in this repo means cross-file imports between test modules are
# unreliable, so we copy the helpers rather than reach across files).
# ---------------------------------------------------------------------------


def build_mock_mcp_aligned() -> dict[str, Any]:
    us = json.loads((MAKER_FIXTURES / "us_macro_indicators.json").read_text())
    jp = json.loads((MAKER_FIXTURES / "japan_tactical.json").read_text())
    cn = json.loads((MAKER_FIXTURES / "china_macro_indicators.json").read_text())
    tl = json.loads((MAKER_FIXTURES / "telemetry_full.json").read_text())
    return {
        "list_macro_countries": {
            "success": True,
            "markets": ["United States", "Japan", "China"],
        },
        "telemetry": tl,
        ("United States", "macro_indicators"): us,
        ("Japan", "tactical"): jp,
        ("China", "macro_indicators"): cn,
    }


class _MockMCPRunner(maker.MCPRunner):
    def __init__(self, mcp: dict[str, Any]):
        self.mcp = mcp

    def list_macro_countries(self) -> dict[str, Any] | None:
        return self.mcp.get("list_macro_countries")

    def get_telemetry(self, fields: list[str]) -> dict[str, Any] | None:
        return self.mcp.get("telemetry")

    def macro_analyst_batch(
        self,
        requests: list[tuple[str, str]],
        concurrency: int = 8,
        per_call_timeout_s: int = 45,
    ) -> dict[tuple[str, str], dict[str, Any] | None]:
        return {(m, c): self.mcp.get((m, c)) for m, c in requests}


def _run_maker(mcp: dict[str, Any], view_dir: Path) -> maker.MakerResult:
    runner = _MockMCPRunner(mcp)
    orch = maker.MakerOrchestrator(maker.MakerOptions(view_dir=view_dir))

    def _mock_gate(*args, **_kw):
        return gate_present.GateResult(disposition="confirm", final_draft=args[0])

    with patch("gate_present.run_gate_loop", side_effect=_mock_gate):
        return orch.execute_synthesis(
            mcp=runner,
            dispose_fn=lambda _: "confirm",
            edit_fn=lambda _, __: ({}, None),
        )


def _judge_dry(
    maker_res: maker.MakerResult,
    view_dir: Path,
    report_dir: Path,
    *,
    llm_call_fn=None,
) -> judge.JudgeResult:
    m_res = maker_res.mcp_responses
    mcp_dict: dict[str, Any] = {
        "per_market": m_res.per_market,
        "telemetry": m_res.telemetry,
        "list_macro_countries": m_res.list_macro_countries,
        "get_telemetry": m_res.telemetry,
    }
    cfg = judge.JudgeConfig(
        dry=True,
        mock_mcp_responses=mcp_dict,
        explicit=True,
        view_dir=view_dir,
        report_dir=report_dir,
    )
    if llm_call_fn is None:
        def llm_call_fn(*_a, **_kw):
            return {
                "recommendations": [
                    {
                        "action": "Update view",
                        "rationale": "Tests",
                        "declined": False,
                    }
                ]
            }
    return judge.run_judge(config=cfg, llm_call_fn=llm_call_fn)


def _simulate_load_edit_save(
    view_dir: Path,
    *,
    prior_view_id: str,
    prior_version_id: str,
    mutate_fn=None,
) -> tuple[str, str, dict[str, Any]]:
    """Simulate /parallax-load-house-view --edit Step 4 save flow.

    Reads the active view.yaml, applies ``mutate_fn`` (if given) to the
    view dict, assigns a new version_id, sets parent_version_id to the
    prior, recomputes view_hash + provenance_hash, writes view.yaml +
    prose.md + provenance.yaml, and appends a chained "save" audit row.

    Returns ``(new_view_id, new_version_id, audit_entry)``.

    This intentionally calls the same low-level primitives the production
    Step 4 save path uses (audit_chain.append_entry, rfc8785-canonical
    hashing), so a regression in those primitives surfaces here. It does
    NOT exercise the LLM-orchestrated workflow's sequencing of those
    primitives — that's tested live in /parallax-load-house-view's own
    samples corpus.
    """
    view_yaml_path = view_dir / "view.yaml"
    provenance_yaml_path = view_dir / "provenance.yaml"
    prose_md_path = view_dir / "prose.md"
    audit_path = view_dir / "audit.jsonl"

    view_data = yaml.safe_load(view_yaml_path.read_text())
    provenance_data = (
        yaml.safe_load(provenance_yaml_path.read_text())
        if provenance_yaml_path.exists()
        else {"schema_version": 1, "tilts": {}}
    )

    if mutate_fn is not None:
        mutate_fn(view_data, provenance_data)

    # New version, same view family.
    new_version_id = str(uuid.uuid4())
    view_data["metadata"]["view_id"] = prior_view_id
    view_data["metadata"]["version_id"] = new_version_id
    view_data["metadata"]["parent_version_id"] = prior_version_id

    provenance_data["view_id"] = prior_view_id
    provenance_data["version_id"] = new_version_id

    # Recompute structural hashes against the mutated content.
    prov_hash = hashlib.sha256(rfc8785.dumps(provenance_data)).hexdigest()
    view_data["metadata"]["provenance_hash"] = prov_hash
    view_hash = hashlib.sha256(
        rfc8785.dumps(view_data.get("tilts", {}))
    ).hexdigest()
    view_data["metadata"]["view_hash"] = view_hash

    view_yaml_path.write_text(yaml.safe_dump(view_data, sort_keys=True))
    provenance_yaml_path.write_text(yaml.safe_dump(provenance_data, sort_keys=True))
    prose_md_path.write_text(
        "---\n"
        f"paired_yaml_hash: {view_hash}\n"
        f"view_id: {prior_view_id}\n"
        f"version_id: {new_version_id}\n"
        "---\n"
        "Edited prose body for version-chain evolution test."
    )

    audit_entry_payload: dict[str, Any] = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "view_id": prior_view_id,
        "version_id": new_version_id,
        "parent_version_id": prior_version_id,
        "view_hash": view_hash,
        "provenance_hash": prov_hash,
        "skill": "parallax-load-house-view",
        "action": "save",
        "applied": True,
        "schema_version": 1,
    }
    final_entry = audit_chain.append_entry(audit_path, audit_entry_payload)
    return prior_view_id, new_version_id, final_entry


def _saves_in_family(audit_path: Path, view_id: str) -> list[dict[str, Any]]:
    """Return all save/generate rows belonging to the given view_id family,
    in file order."""
    rows: list[dict[str, Any]] = []
    for line in audit_path.read_text().strip().split("\n"):
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("action") in ("save", "generate") and e.get("view_id") == view_id:
            rows.append(e)
    return rows


# ---------------------------------------------------------------------------
# Test 1 — view_id is stable across edit-save; version_id chains via
# parent_version_id.
# ---------------------------------------------------------------------------


def test_e2e_view_id_stable_across_edit_save_with_parent_version_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Maker save → simulated /parallax-load-house-view --edit save.

    Invariants:
      - view_id is identical across both versions (view family is stable).
      - version_id changes (each save is a distinct revision).
      - The edit save's parent_version_id points back at the maker
        save's version_id.
      - Audit log has two save/generate rows in this family: v1 with
        parent_version_id null (or absent), v2 with parent_version_id=v1.
      - audit_chain.verify_chain holds end-to-end.
    """
    view_dir = tmp_path / "active-house-view"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    # Step 1: maker save → v1
    base_mcp = build_mock_mcp_aligned()
    res = _run_maker(base_mcp, view_dir)
    assert res.disposition == "confirm"

    v1_view_data = yaml.safe_load((view_dir / "view.yaml").read_text())
    v1_view_id = v1_view_data["metadata"]["view_id"]
    v1_version_id = v1_view_data["metadata"]["version_id"]
    assert v1_view_id is not None
    assert v1_version_id is not None

    # Step 2: simulated --edit save → v2 (mutate basis_statement so the
    # edit is semantically distinct, not a hash-equal no-op).
    def _mutate(view_data: dict[str, Any], _prov: dict[str, Any]) -> None:
        view_data["metadata"]["basis_statement"] = (
            (view_data["metadata"].get("basis_statement") or "")
            + " [Edited via simulated /parallax-load-house-view --edit]"
        )
        # Also bump one tilt to make the structural diff non-empty.
        regions = view_data.setdefault("tilts", {}).setdefault("regions", {})
        regions["us"] = int(regions.get("us", 0)) + 1

    _, v2_version_id, v2_audit = _simulate_load_edit_save(
        view_dir,
        prior_view_id=v1_view_id,
        prior_version_id=v1_version_id,
        mutate_fn=_mutate,
    )
    assert v2_version_id != v1_version_id

    # Step 3: reread view.yaml — view_id stable, version_id new,
    # parent_version_id links back.
    v2_view_data = yaml.safe_load((view_dir / "view.yaml").read_text())
    assert v2_view_data["metadata"]["view_id"] == v1_view_id, (
        "view_id changed across edit save — view family should be stable"
    )
    assert v2_view_data["metadata"]["version_id"] == v2_version_id
    assert v2_view_data["metadata"]["parent_version_id"] == v1_version_id, (
        "parent_version_id must point at prior version_id; got "
        f"{v2_view_data['metadata'].get('parent_version_id')!r} vs "
        f"expected {v1_version_id!r}"
    )

    # Step 4: audit log has two save/generate rows in this family with
    # the expected parent chain.
    saves = _saves_in_family(view_dir / "audit.jsonl", v1_view_id)
    assert len(saves) == 2, (
        f"Expected 2 save/generate rows in family {v1_view_id}; got "
        f"{len(saves)}: {[(s.get('action'), s.get('version_id')) for s in saves]}"
    )
    # The first row is the maker generate (parent_version_id null).
    assert saves[0]["version_id"] == v1_version_id
    assert saves[0].get("parent_version_id") in (None, ""), (
        f"First save row should have null parent_version_id; got "
        f"{saves[0].get('parent_version_id')!r}"
    )
    # Second row is the edit save (parent points at v1).
    assert saves[1]["version_id"] == v2_version_id
    assert saves[1]["parent_version_id"] == v1_version_id
    assert saves[1]["action"] == "save"

    # Step 5: chain integrity holds end-to-end.
    verified = audit_chain.verify_chain(view_dir / "audit.jsonl")
    assert len(verified) >= 2


# ---------------------------------------------------------------------------
# Test 2 — Three-version chain reads correctly via parent_version_id.
# ---------------------------------------------------------------------------


def test_e2e_version_history_audit_log_reads_correctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Walk a three-version chain: maker → edit → edit.

    For each version, parent_version_id must point at the immediate
    predecessor. All three share the same view_id. The chain is walkable
    end-to-end via audit_chain.verify_chain.
    """
    view_dir = tmp_path / "active-house-view"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    # v1: maker save
    base_mcp = build_mock_mcp_aligned()
    _run_maker(base_mcp, view_dir)
    v1_data = yaml.safe_load((view_dir / "view.yaml").read_text())
    v1_view_id = v1_data["metadata"]["view_id"]
    v1_version_id = v1_data["metadata"]["version_id"]

    # v2: edit save
    def _mutate_v2(view_data: dict[str, Any], _prov: dict[str, Any]) -> None:
        view_data["metadata"]["basis_statement"] = (
            view_data["metadata"].get("basis_statement", "") + " [v2 edit]"
        )

    _, v2_version_id, _ = _simulate_load_edit_save(
        view_dir,
        prior_view_id=v1_view_id,
        prior_version_id=v1_version_id,
        mutate_fn=_mutate_v2,
    )

    # v3: edit save (parent is v2)
    def _mutate_v3(view_data: dict[str, Any], _prov: dict[str, Any]) -> None:
        view_data["metadata"]["basis_statement"] = (
            view_data["metadata"].get("basis_statement", "") + " [v3 edit]"
        )
        regions = view_data.setdefault("tilts", {}).setdefault("regions", {})
        regions["japan"] = int(regions.get("japan", 0)) - 1

    _, v3_version_id, _ = _simulate_load_edit_save(
        view_dir,
        prior_view_id=v1_view_id,
        prior_version_id=v2_version_id,
        mutate_fn=_mutate_v3,
    )

    # Read audit log and filter to this view family.
    saves = _saves_in_family(view_dir / "audit.jsonl", v1_view_id)
    assert len(saves) == 3, (
        f"Expected 3 saves in family {v1_view_id}; got {len(saves)}: "
        f"{[(s.get('action'), s.get('version_id'), s.get('parent_version_id')) for s in saves]}"
    )

    # All three share view_id.
    assert all(s["view_id"] == v1_view_id for s in saves), (
        f"view_id drift across saves: "
        f"{[s.get('view_id') for s in saves]}"
    )

    # Ordered parent chain: v1.parent is null, v2.parent=v1, v3.parent=v2.
    assert saves[0]["version_id"] == v1_version_id
    assert saves[0].get("parent_version_id") in (None, "")
    assert saves[1]["version_id"] == v2_version_id
    assert saves[1]["parent_version_id"] == v1_version_id
    assert saves[2]["version_id"] == v3_version_id
    assert saves[2]["parent_version_id"] == v2_version_id

    # Distinct version_ids.
    assert len({v1_version_id, v2_version_id, v3_version_id}) == 3

    # End-to-end chain integrity.
    verified = audit_chain.verify_chain(view_dir / "audit.jsonl")
    assert len(verified) >= 3


# ---------------------------------------------------------------------------
# Test 3 — Judge always audits against the CURRENT version_id, not a stale
# snapshot.
# ---------------------------------------------------------------------------


def test_e2e_judge_run_between_edits_audits_against_current_version_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Judge run after maker save → judge audit row carries
    judged_version_id == v1.version_id. After a simulated edit (→ v2),
    a second judge run must carry judged_version_id == v2.version_id.

    The judge reads view.yaml at run time; this test guards against any
    regression where the judge could cache the version_id from a prior
    run or read a stale source.
    """
    view_dir = tmp_path / "active-house-view"
    report_dir = tmp_path / "judge-reports"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    # v1: maker save
    base_mcp = build_mock_mcp_aligned()
    maker_res = _run_maker(base_mcp, view_dir)
    v1_data = yaml.safe_load((view_dir / "view.yaml").read_text())
    v1_view_id = v1_data["metadata"]["view_id"]
    v1_version_id = v1_data["metadata"]["version_id"]

    # Judge run #1
    jr1 = _judge_dry(maker_res, view_dir, report_dir)
    assert jr1.audit_entry is not None
    assert jr1.audit_entry["action"] == "judge"
    assert jr1.audit_entry.get("judged_version_id") == v1_version_id, (
        f"Judge #1 audited against {jr1.audit_entry.get('judged_version_id')!r}, "
        f"expected v1 version_id {v1_version_id!r}"
    )

    # Simulated edit → v2
    def _mutate(view_data: dict[str, Any], _prov: dict[str, Any]) -> None:
        view_data["metadata"]["basis_statement"] = (
            view_data["metadata"].get("basis_statement", "") + " [edit before second judge]"
        )
        sectors = view_data.setdefault("tilts", {}).setdefault("sectors", {})
        sectors["financials"] = int(sectors.get("financials", 0)) + 1

    _, v2_version_id, _ = _simulate_load_edit_save(
        view_dir,
        prior_view_id=v1_view_id,
        prior_version_id=v1_version_id,
        mutate_fn=_mutate,
    )
    assert v2_version_id != v1_version_id

    # Judge run #2 — must pick up v2 from the fresh view.yaml.
    jr2 = _judge_dry(maker_res, view_dir, report_dir)
    assert jr2.audit_entry is not None
    assert jr2.audit_entry["action"] == "judge"
    assert jr2.audit_entry.get("judged_version_id") == v2_version_id, (
        f"Judge #2 audited against {jr2.audit_entry.get('judged_version_id')!r}, "
        f"expected v2 version_id {v2_version_id!r} (stale read regression?)"
    )

    # Both judge rows present in the audit log with distinct judged_version_ids.
    judge_rows = [
        json.loads(line)
        for line in (view_dir / "audit.jsonl").read_text().strip().split("\n")
        if line.strip()
        and json.loads(line).get("action") == "judge"
    ]
    assert len(judge_rows) >= 2
    judged_versions = [r.get("judged_version_id") for r in judge_rows]
    # The two judge runs must reference distinct versions, and each must
    # match the version active at the time of that judge run.
    assert judged_versions[0] == v1_version_id
    assert judged_versions[-1] == v2_version_id
    assert len({judged_versions[0], judged_versions[-1]}) == 2, (
        f"Judge runs did not differentiate versions: {judged_versions}"
    )

    # Chain integrity end-to-end.
    verified = audit_chain.verify_chain(view_dir / "audit.jsonl")
    assert len(verified) >= 3  # maker + judge + edit + judge (>=3 chained)
