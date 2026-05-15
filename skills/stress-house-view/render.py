"""
Renders the markdown artifact for a house view stress test run.
"""
import datetime
import os
from pathlib import Path
import sys
from typing import Any, Dict, List

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from stress import View, RuleResult  # noqa: E402

def render_artifact(
    view_meta: Dict[str, Any],
    internal_results: List[RuleResult],
    external_results: Dict[str, Any],
    themes: List[str],
    view_hash: str,
    recommended_deltas: List[Dict[str, Any]] | None = None,
    audit_hash_short: str | None = None,
) -> str:
    """Renders the markdown report for the stress test.

    recommended_deltas + audit_hash_short, when provided, render the
    Phase 4-B handoff section (manual apply instructions citing the audit hash).
    """
    
    report = []
    
    # Header
    report.append(f"# House View Stress Test Report")
    report.append(f"**View Name:** {view_meta.get('view_name', 'N/A')}")
    report.append(f"**View Version:** {view_meta.get('version_id', 'N/A')}")
    report.append(f"**Run Date:** {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    report.append(f"**View Hash:** `{view_hash}`")
    report.append("\n---\n")

    # Internal Consistency
    report.append("## Phase 1: Internal Consistency")
    passed_internal = all(not r.triggered for r in internal_results)
    if passed_internal:
        report.append("✅ **All internal consistency checks passed.**")
    else:
        for result in internal_results:
            if result.triggered:
                if result.downgraded_from_stale_config:
                    status = "⚠️ TASTE (Downgraded from Hard Stop — config >6mo stale)"
                elif result.rule_class == "hard_stop":
                    status = "🛑 HARD STOP"
                else:
                    status = "⚠️ TASTE"
                report.append(f"\n- **{status}:** `{result.rule_id}`")
                report.append(f"  - **Evidence:** {', '.join(result.evidence)}")
    report.append("\n---\n")

    # External Comparison
    report.append("## Phase 2: External Comparison vs. Parallax")
    if not external_results:
        report.append("No external comparison was performed.")
    else:
        for market, dimensions in external_results.items():
            report.append(f"\n### Market: {market.upper()}")
            for dim, res in dimensions.items():
                report.append(f"- **{dim}:** {res['state']}")
                if 'cio_view' in res:
                    report.append(f"  - **CIO View:** {res['cio_view']}")
                if 'parallax_view' in res:
                    report.append(f"  - **Parallax View:** {res['parallax_view']}")
    report.append("\n---\n")

    # Themes
    report.append("## Cross-Dimension Themes")
    if themes:
        for theme in themes:
            report.append(f"- {theme}")
    else:
        report.append("No cross-dimension themes were identified.")

    # Phase 4-B handoff: structured deltas + manual apply instructions
    if recommended_deltas:
        report.append("\n---\n")
        report.append("## Phase 4-B Handoff — Recommended Deltas (manual apply)")
        report.append(
            f"\n{len(recommended_deltas)} divergent-stale cells. To apply, edit the "
            f"active view and cite this stress test."
        )
        report.append("\n| Path | Market | CIO value | Parallax signal | Rationale |")
        report.append("|---|---|---|---|---|")
        for d in recommended_deltas:
            mkt = d.get("market") or "(global)"
            cio_val = d.get("cio_value")
            px_sig = d.get("parallax_signal")
            rationale = (d.get("parallax_summary") or "").replace("|", "\\|")[:120]
            report.append(f"| `{d['path']}` | {mkt} | {cio_val!r} | {px_sig!r} | {rationale} |")
        report.append("\n**To apply:**")
        report.append("1. `/parallax-load-house-view --edit` — opens `view.yaml` in `$EDITOR`.")
        report.append("2. Apply the deltas above. The structured form is also saved alongside this report.")
        if audit_hash_short:
            report.append(
                f"3. In the confirmation gate's `basis_statement`, cite this stress test: "
                f"`stress_test:{audit_hash_short}`."
            )
        else:
            report.append("3. In the confirmation gate's `basis_statement`, cite this stress test by its audit hash.")
        report.append(
            "\n*(Future: `/parallax-load-house-view --apply-stress <audit-hash>` "
            "will auto-populate the draft using the `recommended_deltas` field in the audit entry.)*"
        )

    return "\n".join(report)

def save_artifact(report_content: str, view: View, output_dir: Path | None = None):
    """Saves the report to the `stress-tests/` directory under the active view.

    output_dir, when provided, overrides the default location. Tests pass a
    temp path here to avoid polluting `~/.parallax/active-house-view/stress-tests/`.
    Default precedence: explicit `output_dir` → `view.view_path.parent / "stress-tests"`
    → `$PARALLAX_HOUSE_VIEW_DIR/stress-tests` → `~/.parallax/active-house-view/stress-tests`.
    """
    if output_dir is not None:
        stress_tests_dir = Path(output_dir)
    elif view.view_path is not None:
        stress_tests_dir = view.view_path.parent / "stress-tests"
    else:
        env_dir = os.environ.get("PARALLAX_HOUSE_VIEW_DIR")
        base = Path(env_dir) if env_dir else Path(os.path.expanduser("~/.parallax/active-house-view"))
        stress_tests_dir = base / "stress-tests"

    stress_tests_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    report_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    view_hash_short = view.view_hash[:8]
    file_name = f"{report_date}-{view_hash_short}.md"
    report_path = stress_tests_dir / file_name

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    os.chmod(report_path, 0o600)

    return report_path
