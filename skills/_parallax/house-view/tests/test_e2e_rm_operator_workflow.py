"""End-to-end tests for the RM / operator "day in the life" workflow.

These tests exercise the FULL lifecycle of a house view from the
operator's vantage point: CIO publishes → RMs consume → view ages → PM
judges drift → PM edits → cycle repeats. They complement
``test_e2e.py`` (which exercises individual cross-skill protocol points)
and ``test_e2e_versioning.py`` (which exercises the version-chain
primitives in isolation).

Scope of THIS file:

* Test 1 — multi-day operator scenario with time-travel via
  ``metadata.effective_date`` mutation, walking maker save → consumer
  no-fire → judge aligned → time-travel → judge drift → PM edit save
  → judge re-aligned. End-to-end chain integrity asserted across the
  full cycle.
* Test 2 — morning-brief's CONDITIONAL drift-suggestion contract
  (a SKILL.md prose contract, not Python code). Verifies the trigger,
  the conditional structure, the suggestion target, the "do not
  auto-invoke" guard, and the Batch-B placement.
* Test 3 — "first day, no view yet" — graceful degradation across
  all three auto-on-load consumer skills (portfolio-builder, rebalance,
  thematic-screen). Verifies view_status returns ``state='none'``
  cleanly AND that each consumer SKILL.md documents the skip clause
  identically (single source of truth via JIT-loaded pattern file).

Time-travel approach
--------------------
We do NOT mock ``date.today``. Instead, the tests directly mutate
``view.yaml``'s ``metadata.effective_date`` (and, where needed,
``valid_through``) to shift the view's age relative to today. This is
the same mechanism a backdated CIO view would exercise in production
and keeps the tests deterministic across calendar dates.
"""
from __future__ import annotations

import copy
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
MAKER_DIR = REPO / "skills" / "make-house-view"
JUDGE_DIR = REPO / "skills" / "judge-house-view"
SHARED_DIR = REPO / "skills" / "_parallax" / "house-view"
MAKER_FIXTURES = MAKER_DIR / "tests" / "fixtures"

for _p in (SHARED_DIR, MAKER_DIR, JUDGE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_chain  # noqa: E402
import gate_present  # noqa: E402
import judge  # noqa: E402
import maker  # noqa: E402
import view_status  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (inlined per the repo's conftest-collision convention — see the
# leading comment in test_e2e_versioning.py for the rationale.)
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


def _mutate_us_and_japan_to_divergent(maker_res: maker.MakerResult) -> maker.MakerResult:
    """Flip both US and Japan prose so MCP 'current' reads as opposite to
    the saved view across multiple markets.

    Mirrors test_integration_make_judge.py's two-market mutation pattern
    rather than test_e2e.py's US-only mutation: US-only weighs <60% of
    aggregate, which can leave overall severity at drift_minor (same as
    aligned), making the Day 31 severity-strictly-worse assertion
    vacuously satisfied. Flipping US + Japan reliably escalates severity
    to drift_moderate or drift_material.
    """
    out = copy.deepcopy(maker_res)
    flips = {
        "United States": (
            "US growth is rapidly deteriorating. Cautious on tech and "
            "consumer sectors. Underweight equities through year-end. "
            "Valuation metrics at +2.0 and entropy at -2.0 confirm "
            "stretched multiples losing breadth support."
        ),
        "Japan": (
            "Japan tactical view turns outright bearish. Sell industrials "
            "into year-end. JPY weakness now structural; cyclicals under "
            "pressure from rising input costs."
        ),
    }
    for m in out.mcp_responses.per_market:
        if m.market_name not in flips:
            continue
        for _comp, resp in (m.components or {}).items():
            if resp is None:
                continue
            resp["content"] = flips[m.market_name]
    return out


def _simulate_pm_edit_save(
    view_dir: Path,
    *,
    prior_view_id: str,
    prior_version_id: str,
    mutate_fn=None,
) -> tuple[str, str, dict[str, Any]]:
    """Simulate /parallax-load-house-view --edit Step 4 save flow.

    Copy of test_e2e_versioning.py's _simulate_load_edit_save (per the
    repo's conftest-collision convention: helpers are duplicated across
    test files rather than cross-imported). Keeps each test file
    self-contained while exercising the same low-level primitives a
    real PM edit would use (audit_chain.append_entry, rfc8785-canonical
    structural hashing, parent_version_id chaining).

    Returns ``(new_view_id, new_version_id, audit_entry)``.
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

    new_version_id = str(uuid.uuid4())
    view_data["metadata"]["view_id"] = prior_view_id
    view_data["metadata"]["version_id"] = new_version_id
    view_data["metadata"]["parent_version_id"] = prior_version_id

    provenance_data["view_id"] = prior_view_id
    provenance_data["version_id"] = new_version_id

    prov_hash = hashlib.sha256(rfc8785.dumps(provenance_data)).hexdigest()
    view_data["metadata"]["provenance_hash"] = prov_hash
    view_hash = hashlib.sha256(
        rfc8785.dumps(view_data.get("tilts", {}))
    ).hexdigest()
    view_data["metadata"]["view_hash"] = view_hash

    view_yaml_path.write_text(yaml.safe_dump(view_data, sort_keys=True))
    provenance_yaml_path.write_text(
        yaml.safe_dump(provenance_data, sort_keys=True)
    )
    prose_md_path.write_text(
        "---\n"
        f"paired_yaml_hash: {view_hash}\n"
        f"view_id: {prior_view_id}\n"
        f"version_id: {new_version_id}\n"
        "---\n"
        "Edited prose body for RM-operator-workflow Test 1."
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


def _backdate_view(view_dir: Path, *, effective_days_ago: int) -> None:
    """Time-travel: shift the view's effective_date N days into the past.

    Leaves valid_through alone so the view stays "active" (not expired)
    from view_status's perspective; only the *age* changes. Used in
    Test 1 to push view_age past the >30d threshold without expiring.
    """
    view_yaml = view_dir / "view.yaml"
    view_data = yaml.safe_load(view_yaml.read_text())
    new_effective = (
        datetime.date.today() - datetime.timedelta(days=effective_days_ago)
    )
    view_data.setdefault("metadata", {})["effective_date"] = (
        new_effective.isoformat()
    )
    # Ensure the view doesn't fall off the valid_through cliff: push
    # valid_through out to 1 year past today so view_status stays in
    # one of {active, warning, critical}, never expired.
    far_future = (
        datetime.date.today() + datetime.timedelta(days=365)
    )
    view_data["metadata"]["valid_through"] = far_future.isoformat()
    view_yaml.write_text(yaml.safe_dump(view_data, sort_keys=False))


# ---------------------------------------------------------------------------
# Test 1 — full operator lifecycle: v1 published → consumed → judged →
# drifts → PM edits → re-judged
# ---------------------------------------------------------------------------


def test_e2e_full_operator_lifecycle_v1_to_v2_with_drift_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate a 35-day operator scenario from CIO publish through
    PM-driven edit.

    Day 1: CIO publishes via maker (v1 saved).
    Days 1-29: RMs use consumer skills — view_age < 30d, the pre-flight
        auto-on-load drift check does NOT fire per
        auto-on-load-judge-pattern.md.
    Day 30: PM runs judge against current MCP. View is still aligned;
        severity == drift_minor. One judge audit row appended.
    Day 31: Backdate effective_date by 31 days (time-travel). View is
        now stale. Re-run judge against MUTATED MCP (US flipped to
        divergent). Severity is NOT BETTER than the prior judge run.
    Day 32: PM edits view based on recommendations (simulated edit
        save with parent_version_id chaining back to v1). view_id is
        stable; version_id changes.
    Day 33: Re-run judge against the (still mutated) MCP. The PM's
        edit is structural-only (no MCP-driven tilt rewrite), so the
        spec says: severity is NOT WORSE than the pre-edit judge run.

    Final-state assertions cover audit-row count + ordering, view_id
    stability, version_id change, end-to-end chain integrity, and
    presence of judge report bundles.
    """
    view_dir = tmp_path / "active-house-view"
    report_dir = tmp_path / "judge-reports"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    # ---- Day 1: CIO publishes ----
    base_mcp = build_mock_mcp_aligned()
    maker_res = _run_maker(base_mcp, view_dir)
    assert maker_res.disposition == "confirm"
    assert (view_dir / "view.yaml").exists()

    v1_data = yaml.safe_load((view_dir / "view.yaml").read_text())
    v1_view_id = v1_data["metadata"]["view_id"]
    v1_version_id = v1_data["metadata"]["version_id"]
    assert v1_view_id and v1_version_id

    # ---- Days 1-29: RM uses consumer skills (no auto-fire) ----
    # The pattern says fire ONLY when view_age > 30 days. Verify that
    # at age 0d, view_status is "active" and the pre-flight protocol's
    # condition (view_age > 30) is False.
    fresh_status = view_status.compute_status(view_dir)
    assert fresh_status.state == "active", (
        f"Fresh view should be active; got {fresh_status.state!r}"
    )
    assert fresh_status.tilts_apply is True

    # ---- Day 30: PM runs judge while view is still aligned ----
    aligned_jr = _judge_dry(maker_res, view_dir, report_dir)
    assert aligned_jr.severity == "drift_minor", (
        f"Aligned MCP should produce drift_minor; got {aligned_jr.severity!r}"
    )
    assert aligned_jr.audit_entry is not None
    assert aligned_jr.audit_entry["action"] == "judge"
    aligned_report_dir = Path(aligned_jr.report_dir)
    assert aligned_report_dir.is_dir()

    # ---- Day 31: backdate view to view_age == 31d, judge a divergent MCP ----
    _backdate_view(view_dir, effective_days_ago=31)
    aged_status = view_status.compute_status(view_dir)
    # Whether the aged status lands in active/warning/critical depends on
    # how 31 days of age compares to view_status's countdown thresholds
    # given the 1-year valid_through we just set; all three are
    # acceptable. What MUST hold is that tilts still apply (view is not
    # expired) so consumer skills would still tilt.
    assert aged_status.state in ("active", "warning", "critical"), (
        f"31d-aged view with 1y valid_through should not be expired; "
        f"got {aged_status.state!r}"
    )
    assert aged_status.tilts_apply is True
    # Pre-flight protocol condition (view_age > 30) is now satisfied.
    age_days = (
        datetime.date.today()
        - datetime.date.fromisoformat(aged_status.effective_date)
    ).days
    assert age_days > 30

    divergent = _mutate_us_and_japan_to_divergent(maker_res)
    divergent_jr = _judge_dry(divergent, view_dir, report_dir)
    # The mutation must STRICTLY escalate severity vs the aligned run.
    # Severity tier ordering used by the judge.
    _severity_rank = {
        "drift_minor": 0,
        "drift_moderate": 1,
        "drift_material": 2,
    }
    assert _severity_rank[divergent_jr.severity] > _severity_rank[
        aligned_jr.severity
    ], (
        f"Two-market divergent mutation (US + Japan) did not escalate "
        f"severity above aligned: divergent={divergent_jr.severity!r}, "
        f"aligned={aligned_jr.severity!r}. Drift detection regression — "
        f"a real production drift across two major markets would also "
        f"silently report drift_minor."
    )
    divergent_report_dir = Path(divergent_jr.report_dir)
    assert divergent_report_dir.is_dir()
    assert divergent_report_dir != aligned_report_dir

    # ---- Day 32: PM edits view based on recommendations ----
    def _pm_edit(view_data: dict[str, Any], _prov: dict[str, Any]) -> None:
        view_data["metadata"]["basis_statement"] = (
            (view_data["metadata"].get("basis_statement") or "")
            + " [PM edit responding to Day-31 drift recommendations]"
        )
        # Reflect the recommendation: bring US tilt down to align with
        # the deteriorating macro reads.
        regions = view_data.setdefault("tilts", {}).setdefault("regions", {})
        regions["us"] = int(regions.get("us", 0)) - 1

    _, v2_version_id, v2_audit = _simulate_pm_edit_save(
        view_dir,
        prior_view_id=v1_view_id,
        prior_version_id=v1_version_id,
        mutate_fn=_pm_edit,
    )
    assert v2_version_id != v1_version_id
    assert v2_audit["parent_version_id"] == v1_version_id

    v2_data = yaml.safe_load((view_dir / "view.yaml").read_text())
    assert v2_data["metadata"]["view_id"] == v1_view_id, (
        "view_id changed across PM edit — view family must be stable"
    )
    assert v2_data["metadata"]["version_id"] == v2_version_id

    # ---- Day 33: re-run judge against the (still mutated) MCP ----
    # The edit is a structural change to the saved view; the judge
    # re-reads view.yaml at run time. The spec assertion is the weaker
    # of the two options in the brief: severity is NOT WORSE than the
    # pre-edit judge run.
    post_edit_jr = _judge_dry(divergent, view_dir, report_dir)
    assert _severity_rank[post_edit_jr.severity] <= _severity_rank[
        divergent_jr.severity
    ], (
        f"Post-edit judge produced WORSE severity "
        f"({post_edit_jr.severity!r}) than pre-edit ({divergent_jr.severity!r})"
    )
    # The judge MUST have read the new version_id from disk.
    assert post_edit_jr.audit_entry is not None
    assert post_edit_jr.audit_entry.get("judged_version_id") == v2_version_id, (
        f"Post-edit judge audited against "
        f"{post_edit_jr.audit_entry.get('judged_version_id')!r}; "
        f"expected v2 version_id {v2_version_id!r}"
    )

    # ---- Final-state assertions ----
    # Audit log shape: at least
    #   generate(v1) + judge(v1 aligned) + judge(v1 divergent)
    #   + save(v2) + judge(v2)
    # = 5 rows minimum.
    audit_lines = (view_dir / "audit.jsonl").read_text().strip().split("\n")
    entries = [json.loads(line) for line in audit_lines if line.strip()]
    assert len(entries) >= 5, (
        f"Expected ≥5 audit rows for full lifecycle; got {len(entries)}: "
        f"{[(e.get('action'), e.get('version_id')) for e in entries]}"
    )
    actions = [e["action"] for e in entries]
    save_or_gen = [a for a in actions if a in ("save", "generate")]
    judges = [a for a in actions if a == "judge"]
    assert len(save_or_gen) >= 2, (
        f"Expected ≥2 save/generate rows (v1 + v2); got actions {actions}"
    )
    assert len(judges) >= 3, (
        f"Expected ≥3 judge rows (aligned + divergent + post-edit); got "
        f"actions {actions}"
    )

    # view_id stable across both versions; version_id distinct.
    v1_saves = [
        e for e in entries
        if e.get("action") in ("save", "generate")
        and e.get("view_id") == v1_view_id
    ]
    assert len(v1_saves) == 2, (
        f"Expected 2 saves in family {v1_view_id}; got {len(v1_saves)}"
    )
    assert v1_saves[0]["version_id"] == v1_version_id
    assert v1_saves[1]["version_id"] == v2_version_id
    assert v1_saves[1]["parent_version_id"] == v1_version_id

    # Chain integrity end-to-end across the full operator cycle.
    verified = audit_chain.verify_chain(view_dir / "audit.jsonl")
    assert len(verified) == len(entries), (
        f"verify_chain returned {len(verified)} but audit.jsonl has "
        f"{len(entries)} lines — silent skip?"
    )

    # Both pre-edit judge runs and the post-edit judge run produced
    # report bundles.
    report_bundles = [p for p in report_dir.iterdir() if p.is_dir()]
    assert len(report_bundles) >= 3, (
        f"Expected ≥3 judge report bundles (aligned, divergent, post-edit); "
        f"got {len(report_bundles)}: {[p.name for p in report_bundles]}"
    )


# ---------------------------------------------------------------------------
# Test 2 — morning-brief conditional drift-suggestion contract
# ---------------------------------------------------------------------------


def test_e2e_morning_brief_conditional_suggestion_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """morning-brief is LLM-orchestrated prose, not Python. But its
    suggestion contract IS Python-testable as a content shape over the
    SKILL.md file. This test asserts the contract has the four required
    structural elements (trigger phrase, conditional structure,
    suggestion target, "do NOT auto-invoke" guard) AND the placement
    invariant (the suggestion lives under/near the Batch-B alignment
    section, not at the top of the skill).

    The point: catch regressions where someone deletes the conditional,
    inverts it (auto-invoking instead of suggesting), moves it out of
    Batch B, or rewrites it in a way that masks the alignment-check
    dependency.
    """
    brief_md = (REPO / "skills" / "morning-brief" / "SKILL.md").read_text()

    # (1) Trigger phrase: a ≥3 holdings quantifier in some form.
    # Accept "≥3 holdings", ">=3 holdings", "3 or more holdings", or
    # "at least 3 holdings". The presence of one of these is the
    # quantifier-tied trigger.
    trigger_phrases = (
        "≥3 holdings",
        ">=3 holdings",
        "3 or more holdings",
        "at least 3 holdings",
    )
    assert any(phrase in brief_md for phrase in trigger_phrases), (
        "morning-brief SKILL.md must carry a ≥3-holdings quantifier "
        f"trigger; none of {trigger_phrases} present"
    )

    # (2) Conditional structure: an "if/when" clause tied to the
    # alignment check.
    conditional_markers = ("If the Batch B alignment check", "if the alignment check")
    assert any(m in brief_md for m in conditional_markers), (
        "morning-brief SKILL.md must guard the suggestion with a "
        "conditional clause tied to the Batch-B alignment check"
    )

    # (3) Suggestion target: /parallax-judge-house-view.
    assert "/parallax-judge-house-view" in brief_md, (
        "morning-brief SKILL.md must reference /parallax-judge-house-view "
        "as the suggestion target"
    )

    # (4) Explicit "Do NOT auto-invoke" guard.
    assert "Do NOT auto-invoke the judge" in brief_md, (
        "morning-brief SKILL.md must explicitly forbid auto-invoking the "
        "judge from inside morning-brief (the suggestion is a one-liner, "
        "not an action)"
    )

    # Placement invariant: the conditional drift suggestion must appear
    # under or near the Batch-B section, NOT at the top of the skill.
    # Operationalised as: the suggestion's anchor phrase appears AFTER
    # the "### Batch B" header in file order.
    batch_b_idx = brief_md.find("### Batch B")
    assert batch_b_idx != -1, "morning-brief must have a '### Batch B' section"
    suggestion_idx = brief_md.find("Conditional drift suggestion")
    assert suggestion_idx != -1, (
        "morning-brief must carry a 'Conditional drift suggestion' anchor"
    )
    assert suggestion_idx > batch_b_idx, (
        f"Conditional drift suggestion (offset {suggestion_idx}) must "
        f"appear AFTER the '### Batch B' header (offset {batch_b_idx}) — "
        "it has been moved out of Batch B"
    )


# ---------------------------------------------------------------------------
# Test 3 — first-day-no-view: consumer skills skip gracefully end-to-end
# ---------------------------------------------------------------------------


def test_e2e_no_active_view_consumer_skills_skip_gracefully_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The "first day, no view yet" scenario.

    1. No view directory exists → view_status returns state='none'.
    2. Each of the three auto-on-load consumer SKILL.md files
       (portfolio-builder, rebalance, thematic-screen) documents the
       graceful-skip clause: "Skip this pre-flight if invoked with
       --skip-drift-check or if no active house view exists." This is
       a SKILL.md content assertion — the runtime degradation path
       lives in the LLM-readable prose.
    3. Maker save activates a view → view_status flips to active.
    4. Re-read each consumer SKILL.md prose — the static text is
       unchanged (this is the "static prose, runtime-branched behavior"
       invariant: consumer skills don't get rewritten when a view
       appears; only their conditional pre-flight stops skipping).

    Catches regressions where the skip clause drifts away from one of
    the three consumer skills (single-source-of-truth invariant via
    the JIT-loaded pattern file).
    """
    view_dir = tmp_path / "active-house-view"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    # Drive the consumer list dynamically: any SKILL.md that references
    # the auto-on-load-judge-pattern.md (per Phase F consumer integration)
    # IS a consumer skill that must carry the skip clause. Hardcoding a
    # static tuple would miss a future 4th consumer skill that adopts the
    # drift gate but omits the skip clause.
    skills_root = REPO / "skills"
    pattern_marker = "auto-on-load-judge-pattern.md"
    consumers = sorted(
        p.parent.name
        for p in skills_root.glob("*/SKILL.md")
        if pattern_marker in p.read_text()
    )
    # Sanity floor — Phase F installed the gate in 3 skills; if dynamic
    # discovery returns 0, the JIT-load references were renamed/removed
    # and this test has lost its grip on the contract.
    assert len(consumers) >= 3, (
        f"Expected ≥3 consumer skills referencing {pattern_marker!r}; "
        f"discovered {consumers}. Has the JIT-load reference moved?"
    )
    expected_clause = (
        "Skip this pre-flight if invoked with `--skip-drift-check` or "
        "if no active"
    )

    # ---- Step 1: no view → state='none' ----
    assert not view_dir.exists()
    status_before = view_status.compute_status(view_dir)
    assert status_before.state == "none", (
        f"Empty view dir must yield state='none'; got "
        f"{status_before.state!r}"
    )
    assert status_before.tilts_apply is False

    # ---- Step 2: every consumer SKILL.md documents the skip clause ----
    consumer_md_before: dict[str, str] = {}
    for consumer in consumers:
        skill_md = (
            REPO / "skills" / consumer / "SKILL.md"
        ).read_text()
        consumer_md_before[consumer] = skill_md
        assert expected_clause in skill_md, (
            f"{consumer}/SKILL.md is missing the graceful-skip clause: "
            f"{expected_clause!r}. The auto-on-load pre-flight must not "
            "block when no active house view exists."
        )

    # ---- Step 3: activate view via maker save ----
    base_mcp = build_mock_mcp_aligned()
    res = _run_maker(base_mcp, view_dir)
    assert res.disposition == "confirm"

    # ---- Step 4: view_status flips to active ----
    status_after = view_status.compute_status(view_dir)
    assert status_after.state != "none", (
        f"After maker save, view_status must not be 'none'; got "
        f"{status_after.state!r}"
    )
    # Fresh save with default windowing should be one of the
    # tilts-applying states.
    assert status_after.tilts_apply is True
    assert status_after.state in ("active", "warning", "critical"), (
        f"Fresh-save view should be in a tilts-applying state; got "
        f"{status_after.state!r}"
    )

    # ---- Step 5: consumer SKILL.md prose is unchanged ----
    # The "graceful degradation is documented, runtime is branched" rule
    # means the SKILL.md prose stays identical across view-present /
    # view-absent. Only the LLM's pre-flight branch differs.
    for consumer in consumers:
        skill_md_after = (
            REPO / "skills" / consumer / "SKILL.md"
        ).read_text()
        assert skill_md_after == consumer_md_before[consumer], (
            f"{consumer}/SKILL.md changed between the no-view and "
            "view-present checks — prose should be static; only runtime "
            "behavior should branch on view_status"
        )
        # The skip clause is still present after activation (sanity:
        # ensures we didn't accidentally re-read a different file).
        assert expected_clause in skill_md_after
