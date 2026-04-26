"""E2E Smoke Test for Approach B (Compliance Audit).

Simulates the full flow of load-house-view SKILL.md:
1. "Extraction" (Mocked)
2. Provenance Generation
3. Provenance Hashing
4. View Injection
5. View Hashing
6. Chained Audit Append
7. Reasoning Chain Emission
8. Export Validation
"""
import sys
import json
import hashlib
import shutil
import tarfile
from pathlib import Path
from datetime import datetime, timezone

import yaml
import rfc8785

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import audit_chain
import audit_export
import chain_emit
import gap_detect
import gap_suggest

def test_e2e_compliance_flow():
    tmp_base = Path("/tmp/parallax-e2e-test")
    if tmp_base.exists():
        shutil.rmtree(tmp_base)
    tmp_base.mkdir(parents=True)
    
    active_dir = tmp_base / "active"
    active_dir.mkdir()
    audit_path = tmp_base / "audit.jsonl"
    chains_dir = tmp_base / "chains"
    chains_dir.mkdir()
    cache_dir = tmp_base / "cache"
    cache_dir.mkdir()
    
    # --- STEP 1 & 2: MOCK EXTRACTION ---
    view_data = {
        "metadata": {
            "view_name": "E2E Smoke Test View",
            "view_id": "view-123",
            "version_id": "ver-001",
            "effective_date": "2026-04-26",
            "upload_timestamp": datetime.now(timezone.utc).isoformat()
        },
        "tilts": {
            "factors": {"low_volatility": 2, "momentum": -1},
            "sectors": {"consumer_staples": 1}
        }
    }
    
    # --- STEP 3: GENERATE PROVENANCE (Approach B) ---
    provenance_data = {
        "schema_version": 1,
        "view_id": "view-123",
        "version_id": "ver-001",
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
    
    # --- STEP 4: HASHING SEQUENCE (Patch logical flaw check) ---
    # 1. Provenance Hash
    prov_hash = hashlib.sha256(rfc8785.dumps(provenance_data)).hexdigest()
    
    # 2. Inject into view
    view_data["metadata"]["provenance_hash"] = prov_hash
    
    # 3. View Hash (Simplified canonicalization for smoke test)
    view_hash = hashlib.sha256(rfc8785.dumps(view_data["tilts"])).hexdigest()
    view_data["metadata"]["view_hash"] = view_hash
    
    # --- STEP 5: WRITE FILES ---
    (active_dir / "view.yaml").write_text(yaml.safe_dump(view_data))
    (active_dir / "provenance.yaml").write_text(yaml.safe_dump(provenance_data))
    (active_dir / "prose.md").write_text("---\npaired_yaml_hash: " + view_hash + "\n---\nVerbatim prose body")
    
    # --- STEP 6: CHAINED AUDIT APPEND ---
    audit_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "view_id": "view-123",
        "version_id": "ver-001",
        "view_hash": view_hash,
        "action": "save",
        "applied": True,
        "provenance_hash": prov_hash
    }
    audit_chain.append_entry(audit_path, audit_entry)
    
    # --- STEP 7: REASONING CHAIN EMISSION ---
    chain_emit.emit_phase_0_chain(
        view=view_hash,
        base_scores={"response_inline": {}, "response_hash": "0"*64},
        final_portfolio={"weights": {}},
        run_id="01HZSMOKETEST00000000000",
        skill_version="parallax-load-house-view@1.0.0",
        chain_dir=chains_dir
    )
    
    # --- STEP 8: EXPORT ---
    bundle_path = audit_export.create_bundle(
        view_id="view-123",
        active_view_dir=active_dir,
        audit_path=audit_path,
        output_path=tmp_base / "bundle.tar.gz"
    )
    
    # --- VALIDATION ---
    assert bundle_path.exists()
    assert (chains_dir / datetime.now(timezone.utc).strftime("%Y-%m") / "01HZSMOKETEST00000000000.yaml").exists()
    
    # Verify Audit Chain
    entries = audit_chain.verify_chain(audit_path)
    assert len(entries) == 1
    assert entries[0]["chain_root"] is True
    assert entries[0]["provenance_hash"] == prov_hash
    
    # Verify Bundle Manifest
    with tarfile.open(bundle_path, "r:gz") as tar:
        manifest_f = tar.extractfile("integrity_manifest.json")
        manifest = json.loads(manifest_f.read())
        assert "provenance.yaml" in manifest
        assert "audit.jsonl" in manifest
        
    print("✓ E2E Smoke Test Passed: Provenance -> Hash -> Chain -> Export")
    shutil.rmtree(tmp_base)


def test_gap_fill_e2e_flow():
    """Step 2.5 gap-fill end-to-end: detect -> plan -> mock MCP responses ->
    fold -> apply accepted suggestions -> audit entries chain cleanly.
    """
    tmp_base = Path("/tmp/parallax-gapfill-e2e-test")
    if tmp_base.exists():
        shutil.rmtree(tmp_base)
    tmp_base.mkdir(parents=True)
    audit_path = tmp_base / "audit.jsonl"

    # --- Stage a partial draft: source mentions only sectors, silent on
    # regions / macro_regime / factors.
    draft_view = {
        "metadata": {
            "view_id": "view-gapfill-001",
            "version_id": "ver-001",
        },
        "tilts": {
            "sectors": {"information_technology": -1, "energy": 1},
            "regions": {"us": 0, "japan": 0, "mexico": 0},
            "factors": {"momentum": 0, "low_volatility": 0, "profitability": 0, "value": 0, "trading_signals": 0},
            "macro_regime": {"growth": None, "inflation": None, "rates": None, "risk_appetite": None},
            "pillars": {"econometrics_phase": 0, "valuation_state": 0},
            "themes": {"ai_infrastructure": 0},
        },
        "extraction": {
            "source_type": "pdf",
            "extraction_confidence": {
                "sectors": 0.9, "regions": 0.85, "factors": 0.8, "macro_regime": 0.7,
                "pillars": 0.6, "themes": 0.7,
            },
            "extraction_notes": "Hedged on tech, constructive on energy. No view on macro regime or regions.",
        },
    }
    prose_text = "Cautious on tech, constructive on energy."

    # --- Detect ---
    gaps = gap_detect.detect_gaps(
        draft_view,
        prose=prose_text,
        extraction_notes=draft_view["extraction"]["extraction_notes"],
        source_type="pdf",
    )
    # Confirm Phase 0 boundary: no pillars/themes gaps.
    assert all(g.dimension not in ("pillars", "themes", "styles") for g in gaps)
    # us is silent but mentioned via "tech" alias? No — "tech" → information_technology.
    # us not mentioned in prose → gap. japan + mexico not mentioned → gap. mexico not in
    # REGION_MARKET_MAP so will be skipped at planning.
    region_gaps = [g for g in gaps if g.dimension == "regions"]
    assert {g.leaf_key for g in region_gaps} >= {"us", "japan", "mexico"}

    # --- Plan ---
    specs = gap_suggest.plan_calls(gaps)
    purposes = [s.purpose for s in specs]
    assert "telemetry" in purposes
    # mexico has no Parallax coverage → no region spec for it
    region_markets = [s.args["market"] for s in specs if s.purpose == "regions"]
    assert "United States" in region_markets
    assert "Japan" in region_markets
    assert all("Mexico" not in m for m in region_markets)

    # --- Mock MCP responses ---
    mock_telemetry = {
        "regime_tag": "Slowing growth + sticky inflation",
        "commentary": {"headline": "Slowing growth, sticky core inflation persists."},
        "as_of": "2026-04-26T00:00:00Z",
    }
    mock_us_macro = {
        "macro_indicators": "Constructive on US large-caps, supportive flows and improving breadth.",
        "tactical": "Overweight US.",
        "sector_positioning": {"information_technology": 1, "energy": -1},
        "as_of": "2026-04-26T00:00:00Z",
    }
    mock_japan_macro = {
        "macro_indicators": "Cautious on Japan: weak yen and deteriorating earnings, headwind to flows.",
        "tactical": "Underweight Japan equities.",
        "as_of": "2026-04-26T00:00:00Z",
    }

    call_results = []
    for spec in specs:
        if spec.purpose == "telemetry":
            call_results.append((spec, mock_telemetry))
        elif spec.purpose == "regions" and spec.args["market"] == "United States":
            call_results.append((spec, mock_us_macro))
        elif spec.purpose == "regions" and spec.args["market"] == "Japan":
            call_results.append((spec, mock_japan_macro))
        elif spec.purpose == "sectors":
            call_results.append((spec, mock_us_macro))

    # --- Fold ---
    suggestions = gap_suggest.fold_responses(gaps, call_results)
    paths = {s.field_path for s in suggestions}
    # Slowing+sticky → low_volatility +1, profitability +1, momentum -1
    assert "tilts.factors.low_volatility" in paths
    assert "tilts.factors.profitability" in paths
    assert "tilts.factors.momentum" in paths
    # macro_regime growth=slowing, inflation=sticky
    assert "tilts.macro_regime.growth" in paths
    assert "tilts.macro_regime.inflation" in paths
    # US strong-positive, Japan strong-negative (3+ tokens each)
    assert "tilts.regions.us" in paths
    assert "tilts.regions.japan" in paths
    # No suggestion for pillars / themes / styles — Phase 0 boundary
    assert all(not p.startswith("tilts.pillars.") for p in paths)
    assert all(not p.startswith("tilts.themes.") for p in paths)
    assert all(not p.startswith("tilts.styles.") for p in paths)

    # --- Audit: emit gap_fill_suggested for every gap covered by an
    # actually-fired spec, then accept some / reject others.
    for spec, _ in call_results:
        for leaf in spec.covers_leaves:
            for dim in spec.covers_dimensions:
                gp = f"tilts.{dim}.{leaf}"
                # Only audit if this leaf was an actual gap on this dimension.
                matching = [g for g in gaps if g.field_path == gp]
                if not matching:
                    continue
                audit_chain.append_entry(
                    audit_path,
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "view_id": None,
                        "version_id": None,
                        "skill": "parallax-load-house-view",
                        "action": "gap_fill_suggested",
                        "applied": False,
                        "field_path": gp,
                        "source_tool": spec.tool,
                    },
                )

    # Accept the two regional suggestions, reject everything else.
    accepted = {"tilts.regions.us", "tilts.regions.japan"}
    for s in suggestions:
        if s.field_path in accepted:
            audit_chain.append_entry(
                audit_path,
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "view_id": None,
                    "version_id": None,
                    "skill": "parallax-load-house-view",
                    "action": "gap_fill_accepted",
                    "applied": False,
                    "field_path": s.field_path,
                    "suggested_value": s.suggested_value,
                    "source_tool": s.source_tool,
                },
            )
            # Apply to draft. field_path = "tilts.<dim>.<leaf>"
            _, dim, leaf = s.field_path.split(".")
            draft_view["tilts"][dim][leaf] = s.suggested_value
        else:
            audit_chain.append_entry(
                audit_path,
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "view_id": None,
                    "version_id": None,
                    "skill": "parallax-load-house-view",
                    "action": "gap_fill_rejected",
                    "applied": False,
                    "field_path": s.field_path,
                    "suggested_value": s.suggested_value,
                    "source_tool": s.source_tool,
                },
            )

    # --- Verify draft was modified per acceptance ---
    assert draft_view["tilts"]["regions"]["us"] == 2
    assert draft_view["tilts"]["regions"]["japan"] == -2
    # Rejected fields stayed silent.
    assert draft_view["tilts"]["regions"]["mexico"] == 0
    assert draft_view["tilts"]["factors"]["momentum"] == 0
    assert draft_view["tilts"]["macro_regime"]["growth"] is None

    # --- Verify audit chain stays valid across the new action types ---
    entries = audit_chain.verify_chain(audit_path)
    actions = [e["action"] for e in entries]
    assert "gap_fill_suggested" in actions
    assert "gap_fill_accepted" in actions
    assert "gap_fill_rejected" in actions
    # Chain root is the first entry; subsequent entries link via prev_entry_hash.
    assert entries[0].get("chain_root") is True
    for e in entries[1:]:
        assert "prev_entry_hash" in e

    print("✓ Gap-Fill E2E Smoke Test Passed: Detect -> Plan -> Fold -> Apply -> Audit")
    shutil.rmtree(tmp_base)


if __name__ == "__main__":
    try:
        test_e2e_compliance_flow()
        test_gap_fill_e2e_flow()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
