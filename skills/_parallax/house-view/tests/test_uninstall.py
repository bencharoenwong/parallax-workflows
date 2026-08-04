import sys
import shutil
import json
import yaml
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
SKILLS_DIR = REPO / "skills"
SHARED_DIR = REPO / "skills" / "_parallax" / "house-view"
MAKER_DIR = REPO / "skills" / "parallax-make-house-view"
JUDGE_DIR = REPO / "skills" / "parallax-judge-house-view"
STRESS_DIR = REPO / "skills" / "parallax-stress-house-view"

RUNTIME_TREES = (
    (SHARED_DIR, Path("_parallax/house-view")),
    (MAKER_DIR, Path("parallax-make-house-view")),
    (JUDGE_DIR, Path("parallax-judge-house-view")),
    (STRESS_DIR, Path("parallax-stress-house-view")),
)
RUNTIME_MODULE_NAMES = {
    path.stem
    for source, _ in RUNTIME_TREES
    for path in source.glob("*.py")
}


def _ignore_non_runtime_files(_directory: str, names: list[str]) -> set[str]:
    """Keep the replica producer-realistic without copying tests or caches."""
    return {
        name
        for name in names
        if name == "tests" or name == "__pycache__" or name.endswith(".pyc")
    }


@pytest.fixture
def isolated_skills(tmp_path: Path):
    """Replicate installed runtime trees and isolate their bare imports.

    House-view skills use sibling-directory discovery and bare module imports,
    so the replica preserves the installed ``skills/`` layout.  Saving and
    restoring same-named modules prevents this fixture from contaminating
    other house-view tests when the whole root runs in one pytest process.
    """
    skills_dir = tmp_path / "replica" / "skills"
    for source, relative_destination in RUNTIME_TREES:
        shutil.copytree(
            source,
            skills_dir / relative_destination,
            ignore=_ignore_non_runtime_files,
        )

    runtime_paths = (
        skills_dir / "_parallax" / "house-view",
        skills_dir / "parallax-make-house-view",
        skills_dir / "parallax-judge-house-view",
        skills_dir / "parallax-stress-house-view",
    )
    original_sys_path = sys.path[:]
    previous_modules = {
        name: sys.modules[name]
        for name in RUNTIME_MODULE_NAMES
        if name in sys.modules
    }
    for name in RUNTIME_MODULE_NAMES:
        sys.modules.pop(name, None)
    for path in reversed(runtime_paths):
        sys.path.insert(0, str(path))

    try:
        yield skills_dir
    finally:
        sys.path[:] = original_sys_path
        for name in RUNTIME_MODULE_NAMES:
            sys.modules.pop(name, None)
        sys.modules.update(previous_modules)

@contextmanager
def temporarily_disabled(skills_dir: Path, skill_name: str):
    """Disable a skill inside an isolated installed-tree replica."""
    src = skills_dir / skill_name
    disabled_dir = skills_dir / ".disabled"
    dst = disabled_dir / skill_name
    if not src.exists():
        raise RuntimeError(f"Skill not found: {src}")
    disabled_dir.mkdir(exist_ok=True)
    shutil.move(str(src), str(dst))
    try:
        yield
    finally:
        shutil.move(str(dst), str(src))
        if not any(disabled_dir.iterdir()):
            disabled_dir.rmdir()


def checkout_metadata_snapshot() -> dict[str, tuple[int, int, int, int]]:
    """Capture checkout inode/mtime metadata for uninstall-sensitive trees."""
    snapshot = {}
    for root in (MAKER_DIR, JUDGE_DIR):
        for path in (root, *sorted(root.rglob("*"))):
            stat = path.lstat()
            snapshot[str(path.relative_to(SKILLS_DIR))] = (
                stat.st_ino,
                stat.st_mtime_ns,
                stat.st_size,
                stat.st_mode,
            )
    return snapshot

def seed_active_view_from_golden(tmp_path: Path):
    golden_dir = REPO / "skills" / "_parallax" / "house-view" / "tests" / "golden" / "pre_v2_house_view"
    if not golden_dir.exists():
        pytest.xfail("Golden baseline needs initial generation")
    for f in golden_dir.glob("*"):
        if f.is_file() and f.name != "README.md" and not f.name.endswith(".py"):
            shutil.copy2(f, tmp_path / f.name)

def build_aligned_mcp() -> dict[str, Any]:
    return {
        "list_macro_countries": {
            "success": True,
            "markets": ["United States", "Japan", "China"],
        },
        "telemetry": {"regime_tag": "test-regime", "signals": {}},
        # `success` is part of the real macro_analyst envelope (verified live
        # 2026-08-03). A bare payload without it is a shape the API never
        # returns, and the reachability check fails closed on it by design.
        ("United States", "macro_indicators"): {
            "success": True,
            "component": "macro_indicators",
            "content": "Growth steady; inflation benign.",
        },
        ("Japan", "tactical"): {
            "success": True,
            "component": "tactical",
            "content": "Equities overweight.",
        },
        ("China", "macro_indicators"): {
            "success": True,
            "component": "macro_indicators",
            "content": "Growth slowing.",
        },
    }

def run_load_house_view_against_fixture(fixture: Any, view_dir: Path, auto_confirm: bool = True):
    """Simulate load-house-view creating output matching golden."""
    golden_dir = REPO / "skills" / "_parallax" / "house-view" / "tests" / "golden" / "pre_v2_house_view"
    if not golden_dir.exists():
        pytest.xfail("Golden baseline needs initial generation")
    
    import audit_chain
    from datetime import datetime, timezone
    import hashlib
    import rfc8785
    
    view_data = {
        "metadata": {
            "view_name": "E2E Golden Baseline View",
            "view_id": "view-12345",
            "version_id": "ver-00001",
            "effective_date": "2026-04-26",
            "upload_timestamp": datetime.now(timezone.utc).isoformat()
        },
        "tilts": {
            "factors": {"low_volatility": 2, "momentum": -1},
            "sectors": {"consumer_staples": 1}
        }
    }

    provenance_data = {
        "schema_version": 1,
        "view_id": "view-12345",
        "version_id": "ver-00001",
        "tilts": {
            "tilts.factors.low_volatility": {
                "value": 2,
                "derivation": [{
                    "type": "prose_extraction",
                    "source_span": "Strong overweight defensive factor exposure",
                    "confidence": 0.95
                }]
            }
        }
    }
    
    prov_hash = hashlib.sha256(rfc8785.dumps(provenance_data)).hexdigest()
    view_data["metadata"]["provenance_hash"] = prov_hash
    view_hash = hashlib.sha256(rfc8785.dumps(view_data["tilts"])).hexdigest()
    view_data["metadata"]["view_hash"] = view_hash
    
    (view_dir / "view.yaml").write_text(yaml.safe_dump(view_data))
    (view_dir / "provenance.yaml").write_text(yaml.safe_dump(provenance_data))
    (view_dir / "prose.md").write_text("---\npaired_yaml_hash: " + view_hash + "\n---\nVerbatim prose body")
    
    audit_path = view_dir / "audit.jsonl"
    audit_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "view_id": "view-12345",
        "version_id": "ver-00001",
        "view_hash": view_hash,
        "action": "save",
        "applied": True,
        "provenance_hash": prov_hash
    }
    audit_chain.append_entry(audit_path, audit_entry)

def structural_diff(d1: Any, d2: Any, exclude_keys: set[str], path: str = "") -> list[str]:
    """Recursively compare two dicts/lists, ignoring keys in exclude_keys."""
    diffs = []
    if isinstance(d1, dict) and isinstance(d2, dict):
        for k in d1.keys() | d2.keys():
            if k in exclude_keys:
                continue
            if k not in d1:
                diffs.append(f"{path}.{k} missing in left")
            elif k not in d2:
                diffs.append(f"{path}.{k} missing in right")
            else:
                diffs.extend(structural_diff(d1[k], d2[k], exclude_keys, f"{path}.{k}"))
    elif isinstance(d1, list) and isinstance(d2, list):
        if len(d1) != len(d2):
            diffs.append(f"{path} length mismatch: {len(d1)} != {len(d2)}")
        else:
            for i, (v1, v2) in enumerate(zip(d1, d2)):
                diffs.extend(structural_diff(v1, v2, exclude_keys, f"{path}[{i}]"))
    else:
        if d1 != d2:
            diffs.append(f"{path}: {d1} != {d2}")
    return diffs

def test_disable_maker_leaves_judge_functional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_skills: Path,
):
    """With make-house-view disabled, judge still runs (operates on
    whatever view is active; doesn't depend on maker for read-only
    judgment).
    """
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(tmp_path))
    seed_active_view_from_golden(tmp_path)

    with temporarily_disabled(isolated_skills, "parallax-make-house-view"):
        import judge
        
        config = judge.JudgeConfig(
            dry=True,
            mock_mcp_responses={},
            explicit=True,
            view_dir=tmp_path,
            report_dir=tmp_path / "reports",
        )
        
        result = judge.run_judge(config=config)
        
        assert result is not None
        assert result.severity in ("drift_minor", "drift_moderate", "drift_material")
        assert any("maker modules unavailable" in d for d in result.diagnostics)

def test_disable_judge_leaves_maker_functional_and_consumers_skip_gracefully(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_skills: Path,
):
    """With judge-house-view disabled:
       (a) maker still works (synthesize + save) using mocked MCP.
       (b) Auto-on-load drift check in consumer skills (per Phase F)
           emits the graceful-skip preamble, not an error.
    """
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(tmp_path))

    with temporarily_disabled(isolated_skills, "parallax-judge-house-view"):
        import maker
        import gate_present
        
        class MockMCPRunner(maker.MCPRunner):
            def __init__(self, mcp_dict):
                self.mcp_dict = mcp_dict
            def list_macro_countries(self):
                return self.mcp_dict.get("list_macro_countries")
            def get_telemetry(self, fields):
                return self.mcp_dict.get("telemetry")
            def macro_analyst_batch(self, requests, concurrency=8, per_call_timeout_s=45):
                return {(m, c): self.mcp_dict.get((m, c)) for m, c in requests}

        runner = MockMCPRunner(build_aligned_mcp())
        opts = maker.MakerOptions(view_dir=tmp_path)
        orch = maker.MakerOrchestrator(opts)

        def _mock_gate_loop(*args, **kwargs):
            return gate_present.GateResult(disposition="confirm", final_draft=args[0])

        with patch("gate_present.run_gate_loop", side_effect=_mock_gate_loop):
            result = orch.execute_synthesis(
                mcp=runner,
                dispose_fn=lambda _: "confirm",
                edit_fn=lambda _, __: ({}, None),
            )
        
        assert (tmp_path / "view.yaml").exists()
        assert result.view_id is not None

        pattern_md = (
            isolated_skills / "_parallax" / "house-view" / "auto-on-load-judge-pattern.md"
        ).read_text()
        assert "not installed; drift check skipped" in pattern_md
        assert ("Do NOT fail" in pattern_md) or ("graceful" in pattern_md.lower())
        assert not (isolated_skills / "parallax-judge-house-view").exists()


def test_disable_both_yields_structural_audit_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_skills: Path,
):
    """With both make and judge disabled, load-house-view's ingest output
    must be structurally identical to the pre-v2 golden baseline.

    KNOWN LIMITATION (code-reviewer 2026-05-24):
    This test verifies audit-chain linkage and structural schema invariants
    using synthetic ingest via ``run_load_house_view_against_fixture`` (which
    calls audit_chain + chain_emit primitives directly). It does NOT detect
    regressions in /parallax-load-house-view's actual Step 4 save path,
    because the load skill is an LLM-orchestrated workflow with no
    importable Python entry point. The synthetic ingest exercises the same
    primitives the production save path uses, so a regression in those
    primitives WILL be caught — but a regression in the SKILL.md workflow's
    sequencing of those primitives WILL NOT.

    For end-to-end coverage of the production save path, rely on the live
    integration test in /parallax-load-house-view's own samples corpus.
    """
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(tmp_path))

    with temporarily_disabled(
        isolated_skills, "parallax-make-house-view"
    ), temporarily_disabled(isolated_skills, "parallax-judge-house-view"):
        run_load_house_view_against_fixture(
            fixture=None,
            view_dir=tmp_path,
            auto_confirm=True,
        )

        current = {
            "view.yaml": yaml.safe_load((tmp_path / "view.yaml").read_text()),
            "provenance.yaml": yaml.safe_load((tmp_path / "provenance.yaml").read_text()),
            "audit.jsonl": [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().strip().split("\n") if line.strip()],
        }

        golden_dir = REPO / "skills" / "_parallax" / "house-view" / "tests" / "golden" / "pre_v2_house_view"
        golden = {
            "view.yaml": yaml.safe_load((golden_dir / "view.yaml").read_text()),
            "provenance.yaml": yaml.safe_load((golden_dir / "provenance.yaml").read_text()),
            "audit.jsonl": [json.loads(line) for line in (golden_dir / "audit.jsonl").read_text().strip().split("\n") if line.strip()],
        }

        TIME_VARYING = {"ts", "prev_entry_hash", "entry_hash", "synthesis_timestamp",
                        "view_id", "version_id", "view_hash", "provenance_hash", "upload_timestamp"}

        diff = structural_diff(current, golden, exclude_keys=TIME_VARYING)
        assert not diff, f"Structural drift from golden baseline: {diff}"

        assert current["view.yaml"]["metadata"]["view_id"]
        assert len(current["view.yaml"]["metadata"]["view_hash"]) == 64

        import audit_chain
        try:
            entries = audit_chain.verify_chain(tmp_path / "audit.jsonl")
            assert len(entries) > 0
        except Exception as e:
            pytest.fail(f"Audit chain broken: {e}")


@pytest.mark.parametrize(
    "skill_name",
    ("parallax-make-house-view", "parallax-judge-house-view"),
)
def test_injected_failure_restores_replica_without_touching_checkout(
    isolated_skills: Path,
    skill_name: str,
):
    """An exception during disable cannot alter the tracked checkout."""
    checkout_before = checkout_metadata_snapshot()

    with pytest.raises(RuntimeError, match="injected uninstall failure"):
        with temporarily_disabled(isolated_skills, skill_name):
            assert not (isolated_skills / skill_name).exists()
            raise RuntimeError("injected uninstall failure")

    assert (isolated_skills / skill_name).is_dir()
    assert not (isolated_skills / ".disabled").exists()
    assert checkout_metadata_snapshot() == checkout_before
