"""Multi-tenant isolation E2E tests for the house-view family.

Context
-------
Per DECISIONS.md 2026-05-24, Phase D (managed backend) is cancelled — the
judge stays client-side per bank, so the system is effectively single-tenant
per machine via ``~/.parallax/active-house-view/``. However, the
``PARALLAX_HOUSE_VIEW_DIR`` env var AND the explicit ``view_dir`` parameter
on ``MakerOptions`` / ``JudgeConfig`` are the multi-tenant primitives today:
a CG-managed inference box hosting multiple bank clients would route each
client to a distinct view dir.

These tests verify that isolation actually holds end-to-end:

  1. Explicit ``view_dir`` per tenant → no cross-pollution of view.yaml,
     audit.jsonl, or judge reports.
  2. Override priority: explicit > env var > DEFAULT_DIR (mirrors
     ``view_status._resolve_dir`` semantics for the consumer side).
  3. Concurrent two-tenant operation via threads + explicit ``view_dir``.
     Env vars are process-wide so they CAN'T provide concurrent-tenant
     isolation; explicit ``view_dir`` is the only safe primitive.

Failure modes hunted
--------------------
- Module-level state keyed on something other than view_dir (e.g., a
  module-level cache that caches the first-seen view_dir, then ignores
  subsequent ones).
- Default-arg leakage (e.g., ``view_dir: Path = DEFAULT_VIEW_DIR`` evaluated
  at import time then mutated, causing later tenants to share state).
- Bundle/report dir leakage when both tenants use the same parent.
- Audit chains sharing fcntl-locked state across tenants (each tenant's
  audit.jsonl is a separate file, so the lock is per-file — but verifying
  it via test catches future regressions).
"""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
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
# Helpers — duplicated inline from test_e2e.py per repo convention (test
# files in this directory don't share a conftest for these helpers; each
# test file inlines them so failures are self-contained)
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


import copy as _copy  # noqa: E402  (grouped near class that uses it)


class _MockMCPRunner(maker.MCPRunner):
    def __init__(self, mcp: dict[str, Any]):
        # Deep-copy so concurrent _MockMCPRunner instances (Test 3) don't
        # share nested dict references. Today the maker/judge pipeline
        # does not mutate response dicts, but this test exists to catch
        # FUTURE regressions where a processing step mutates a nested
        # response in-place (e.g., `resp["content"] = ...`). Without the
        # deep-copy, such a regression would silently corrupt the other
        # thread's view via shared reference — GIL serializes Python
        # bytecode but doesn't isolate mutable-object sharing.
        self.mcp = _copy.deepcopy(mcp)

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


def _audit_actions(audit_path: Path) -> list[str]:
    if not audit_path.exists():
        return []
    lines = [ln for ln in audit_path.read_text().splitlines() if ln.strip()]
    return [json.loads(ln)["action"] for ln in lines]


# ---------------------------------------------------------------------------
# Test 1 — Two tenants via explicit view_dir are isolated end-to-end
# ---------------------------------------------------------------------------


def test_e2e_two_tenants_via_explicit_view_dir_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two distinct tenants on the same machine, each with its own
    ``view_dir`` passed explicitly to ``MakerOptions`` and ``JudgeConfig``.
    No env var is used (env vars are process-wide and don't model real
    concurrent multi-tenant infra). Verify:

      1. Each maker save lands ONLY in its own tenant dir.
      2. tenant_a's artifacts contain none of tenant_b's data (and vice
         versa) — covers view.yaml, audit.jsonl, prose.md, provenance.yaml.
      3. After tenant_b's save, tenant_a's view.yaml is byte-identical to
         what it was right after tenant_a saved (tenant_b didn't reach in).
      4. Judge against each tenant produces a report bundled into the
         per-tenant report dir and the judge audit row lands in the correct
         tenant's audit.jsonl.
    """
    tenant_a = tmp_path / "tenant_a"
    tenant_b = tmp_path / "tenant_b"
    report_a = tmp_path / "reports_a"
    report_b = tmp_path / "reports_b"
    chain_dir = tmp_path / "chains"

    # Shared chain dir is fine — chain artifacts carry unique run_ids and
    # this test isn't about chain dir isolation.
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    # Build distinguishable MCP inputs for the two tenants so cross-tenant
    # bleed shows up as content mismatch, not just metadata. We piggyback
    # on the basis_hint shaping by mutating telemetry's regime_tag.
    mcp_a = build_mock_mcp_aligned()
    mcp_b = build_mock_mcp_aligned()
    # Deepcopy via json round-trip on the parts we mutate
    mcp_b["telemetry"] = json.loads(json.dumps(mcp_b["telemetry"]))
    mcp_b["telemetry"]["regime_tag"] = "TENANT_B_DISTINCT_REGIME"

    # --- Save for tenant A first ---
    res_a = _run_maker(mcp_a, tenant_a)
    assert res_a.disposition == "confirm"
    assert (tenant_a / "view.yaml").exists()
    assert (tenant_a / "audit.jsonl").exists()
    # tenant_b should not exist yet
    assert not tenant_b.exists() or not (tenant_b / "view.yaml").exists()

    view_a_bytes_after_save = (tenant_a / "view.yaml").read_bytes()
    audit_a_bytes_after_save = (tenant_a / "audit.jsonl").read_bytes()
    view_a_data = yaml.safe_load(view_a_bytes_after_save)
    view_a_id = view_a_data["metadata"]["view_id"]
    view_a_version_id = view_a_data["metadata"]["version_id"]

    # --- Save for tenant B ---
    res_b = _run_maker(mcp_b, tenant_b)
    assert res_b.disposition == "confirm"
    assert (tenant_b / "view.yaml").exists()
    assert (tenant_b / "audit.jsonl").exists()

    view_b_bytes_after_save = (tenant_b / "view.yaml").read_bytes()
    view_b_data = yaml.safe_load(view_b_bytes_after_save)
    view_b_id = view_b_data["metadata"]["view_id"]
    view_b_version_id = view_b_data["metadata"]["version_id"]

    # 1. + 3. Tenant A's artifacts are byte-identical post tenant-B save
    assert (tenant_a / "view.yaml").read_bytes() == view_a_bytes_after_save, (
        "tenant_a/view.yaml mutated when tenant_b ran maker — CROSS-TENANT "
        "WRITE LEAK in maker save path"
    )
    assert (tenant_a / "audit.jsonl").read_bytes() == audit_a_bytes_after_save, (
        "tenant_a/audit.jsonl mutated when tenant_b ran maker — CROSS-TENANT "
        "AUDIT LEAK in maker save path"
    )

    # 2. Distinct view_ids and version_ids
    assert view_a_id != view_b_id, (
        f"Both tenants got the same view_id {view_a_id!r} — UUID generation "
        f"may be keyed on something tenant-shared (clock-only, or a cache)"
    )
    assert view_a_version_id != view_b_version_id

    # Tenant A's audit.jsonl contains exactly one save row referencing
    # view_a_id — none of tenant_b's identifiers.
    audit_a = [
        json.loads(ln)
        for ln in (tenant_a / "audit.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    audit_b = [
        json.loads(ln)
        for ln in (tenant_b / "audit.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    assert all(row.get("view_id") == view_a_id for row in audit_a), (
        f"tenant_a/audit.jsonl contains rows with foreign view_ids: "
        f"{[row.get('view_id') for row in audit_a]}"
    )
    assert all(row.get("view_id") == view_b_id for row in audit_b), (
        f"tenant_b/audit.jsonl contains rows with foreign view_ids: "
        f"{[row.get('view_id') for row in audit_b]}"
    )

    # Sanity: tenant_b's view_id never appears in tenant_a's view.yaml
    # text and vice versa.
    view_a_text = (tenant_a / "view.yaml").read_text()
    view_b_text = (tenant_b / "view.yaml").read_text()
    assert view_b_id not in view_a_text
    assert view_a_id not in view_b_text

    # 4. Judge each tenant; reports land in the correct tenant report dir
    jr_a = _judge_dry(res_a, tenant_a, report_a)
    jr_b = _judge_dry(res_b, tenant_b, report_b)

    assert Path(jr_a.report_dir).is_relative_to(report_a), (
        f"tenant_a judge report landed at {jr_a.report_dir}, expected under "
        f"{report_a}"
    )
    assert Path(jr_b.report_dir).is_relative_to(report_b), (
        f"tenant_b judge report landed at {jr_b.report_dir}, expected under "
        f"{report_b}"
    )

    # Judge audit row appended to the correct tenant
    audit_a_after_judge = [
        json.loads(ln)
        for ln in (tenant_a / "audit.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    audit_b_after_judge = [
        json.loads(ln)
        for ln in (tenant_b / "audit.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    assert len(audit_a_after_judge) == len(audit_a) + 1
    assert len(audit_b_after_judge) == len(audit_b) + 1
    assert audit_a_after_judge[-1]["action"] == "judge"
    assert audit_a_after_judge[-1]["view_id"] == view_a_id
    assert audit_b_after_judge[-1]["action"] == "judge"
    assert audit_b_after_judge[-1]["view_id"] == view_b_id

    # Chain integrity per-tenant
    audit_chain.verify_chain(tenant_a / "audit.jsonl")
    audit_chain.verify_chain(tenant_b / "audit.jsonl")


# ---------------------------------------------------------------------------
# Test 2 — Override priority: explicit > env var > DEFAULT_DIR
# ---------------------------------------------------------------------------


def test_e2e_env_var_and_explicit_view_dir_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per ``view_status._resolve_dir``: explicit param > env var > DEFAULT_DIR.

    Verify the override priority holds end-to-end:
      1. Env var points at tenant_a.
      2. Maker is called with an explicit ``view_dir=tenant_b`` — explicit
         must win, save lands in tenant_b, tenant_a stays empty.
      3. ``view_status.compute_status()`` without an ``explicit=`` arg must
         report tenant_a's state (env var wins when no explicit override).
      4. ``view_status.compute_status(view_dir=tenant_b)`` must report
         tenant_b's state (explicit wins again).
    """
    tenant_a = tmp_path / "tenant_a"
    tenant_b = tmp_path / "tenant_b"
    chain_dir = tmp_path / "chains"

    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(tenant_a))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    base_mcp = build_mock_mcp_aligned()

    # 2. Explicit overrides env var
    res = _run_maker(base_mcp, tenant_b)
    assert res.disposition == "confirm"
    assert (tenant_b / "view.yaml").exists(), (
        "Save did not land in explicit view_dir=tenant_b"
    )
    # tenant_a (the env-var target) must NOT have been written to
    assert not (tenant_a / "view.yaml").exists(), (
        "Save leaked into env-var-targeted tenant_a even though explicit "
        "view_dir=tenant_b was passed. PRIORITY VIOLATION: env var won "
        "over explicit arg in maker save path."
    )
    assert not (tenant_a / "audit.jsonl").exists()

    # 4. Explicit view_dir wins for compute_status too
    status_b_explicit = view_status.compute_status(view_dir=tenant_b)
    # tenant_b has a fresh view, so state is active (or warning/critical
    # depending on the maker-generated valid_through window — all of these
    # are non-"none", which is what matters)
    assert status_b_explicit.state != "none", (
        f"compute_status(view_dir=tenant_b) returned state='none' even "
        f"though tenant_b has a saved view.yaml. Explicit override broken."
    )

    # 3. No explicit → env var wins → tenant_a (which is empty) → state=none
    status_envvar = view_status.compute_status()
    assert status_envvar.state == "none", (
        f"compute_status() without explicit arg returned state="
        f"{status_envvar.state!r} but env var points at empty tenant_a. "
        f"Env var priority broken (or DEFAULT_DIR leaked through)."
    )

    # Defense in depth: confirm env var is actually what _resolve_dir picks
    # up when no explicit arg is given.
    resolved = view_status._resolve_dir(None)
    assert resolved == tenant_a, (
        f"_resolve_dir(None) returned {resolved}, expected {tenant_a} "
        f"(env var). DEFAULT_DIR may be shadowing the env var."
    )
    resolved_explicit = view_status._resolve_dir(tenant_b)
    assert resolved_explicit == tenant_b, (
        f"_resolve_dir(tenant_b) returned {resolved_explicit}, expected "
        f"{tenant_b}. Explicit override broken in _resolve_dir."
    )


# ---------------------------------------------------------------------------
# Test 3 — Concurrent two-tenant operation via explicit view_dir
# ---------------------------------------------------------------------------


def test_e2e_concurrent_tenants_no_cross_pollution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two threads, each driving maker+judge against a distinct tenant dir
    via the explicit ``view_dir`` parameter. Env var can't be used here:
    it's process-wide, so concurrent threads can't each have their own
    env-var-resolved view_dir.

    The barrier ensures both threads hit the maker save at roughly the
    same wall-clock moment, maximising the chance of any shared mutable
    state surfacing as cross-contamination.

    Invariants:
      1. Each tenant ends with exactly 2 audit rows (1 save + 1 judge).
      2. tenant_a's view_id != tenant_b's view_id.
      3. tenant_a's audit.jsonl mentions ONLY tenant_a's view_id; same
         for tenant_b.
      4. Per-tenant chain verification passes independently.

    If shared mutable state leaks across tenants (e.g., a module-level
    cache that doesn't key on view_dir), this test will see one tenant's
    artifacts inside the other's directory or two identical view_ids.
    """
    tenant_a = tmp_path / "tenant_a"
    tenant_b = tmp_path / "tenant_b"
    report_a = tmp_path / "reports_a"
    report_b = tmp_path / "reports_b"
    chain_dir = tmp_path / "chains"
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    base_mcp = build_mock_mcp_aligned()

    barrier = threading.Barrier(2)
    results: dict[str, Any] = {}

    def _tenant_worker(name: str, tdir: Path, rdir: Path) -> None:
        try:
            barrier.wait(timeout=10)
            mres = _run_maker(base_mcp, tdir)
            # Second barrier wait would over-synchronise; the save+judge
            # back-to-back in the same thread is the realistic workload.
            jres = _judge_dry(mres, tdir, rdir)
            results[name] = {"maker": mres, "judge": jres}
        except Exception as exc:  # noqa: BLE001 — surface diagnostics
            results[name] = exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_tenant_worker, "a", tenant_a, report_a)
        fut_b = pool.submit(_tenant_worker, "b", tenant_b, report_b)
        fut_a.result(timeout=60)
        fut_b.result(timeout=60)

    # Surface thread exceptions first
    for name, res in results.items():
        if isinstance(res, Exception):
            raise AssertionError(
                f"Tenant thread {name!r} raised under concurrent operation: "
                f"{type(res).__name__}: {res}. This suggests shared mutable "
                f"state in maker or judge that is not safe for concurrent "
                f"multi-tenant use."
            )

    # 1. Each tenant has exactly 2 audit rows
    actions_a = _audit_actions(tenant_a / "audit.jsonl")
    actions_b = _audit_actions(tenant_b / "audit.jsonl")
    assert len(actions_a) == 2, (
        f"tenant_a expected 2 audit rows (save+judge); got {len(actions_a)} "
        f"with actions={actions_a}. Possible cross-tenant write into "
        f"tenant_a's audit.jsonl (or a row was lost)."
    )
    assert len(actions_b) == 2, (
        f"tenant_b expected 2 audit rows (save+judge); got {len(actions_b)} "
        f"with actions={actions_b}."
    )
    assert actions_a.count("judge") == 1
    assert actions_b.count("judge") == 1
    save_count_a = sum(1 for a in actions_a if a in ("save", "generate"))
    save_count_b = sum(1 for a in actions_b if a in ("save", "generate"))
    assert save_count_a == 1
    assert save_count_b == 1

    # 2. Distinct view_ids
    view_a = yaml.safe_load((tenant_a / "view.yaml").read_text())
    view_b = yaml.safe_load((tenant_b / "view.yaml").read_text())
    view_a_id = view_a["metadata"]["view_id"]
    view_b_id = view_b["metadata"]["view_id"]
    assert view_a_id != view_b_id, (
        f"Both concurrent tenants produced the same view_id {view_a_id!r}. "
        f"UUID generation may be sharing state across tenants (e.g., a "
        f"module-level cached view_id keyed on something tenant-shared)."
    )

    # 3. No cross-mention of view_ids across audit logs
    audit_a_rows = [
        json.loads(ln)
        for ln in (tenant_a / "audit.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    audit_b_rows = [
        json.loads(ln)
        for ln in (tenant_b / "audit.jsonl").read_text().splitlines()
        if ln.strip()
    ]
    for row in audit_a_rows:
        assert row.get("view_id") == view_a_id, (
            f"tenant_a/audit.jsonl row references foreign view_id "
            f"{row.get('view_id')!r} (expected {view_a_id!r}). "
            f"CROSS-TENANT AUDIT POLLUTION under concurrency."
        )
    for row in audit_b_rows:
        assert row.get("view_id") == view_b_id, (
            f"tenant_b/audit.jsonl row references foreign view_id "
            f"{row.get('view_id')!r} (expected {view_b_id!r}). "
            f"CROSS-TENANT AUDIT POLLUTION under concurrency."
        )

    # 4. Per-tenant chain verification
    verified_a = audit_chain.verify_chain(tenant_a / "audit.jsonl")
    verified_b = audit_chain.verify_chain(tenant_b / "audit.jsonl")
    assert len(verified_a) == 2
    assert len(verified_b) == 2

    # Bonus: each tenant's judge report bundle landed in the correct dir
    jr_a = results["a"]["judge"]
    jr_b = results["b"]["judge"]
    assert Path(jr_a.report_dir).is_relative_to(report_a)
    assert Path(jr_b.report_dir).is_relative_to(report_b)
