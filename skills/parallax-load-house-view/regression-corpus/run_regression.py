#!/usr/bin/env python3
"""
Regression-corpus runner for the house-view extraction harness.

Reads the labeled corpus (corpus.yaml) and a directory of baseline extractions
(one YAML per corpus entry_id, named <entry_id>.yaml). For each entry, compares
the baseline extraction against the expected labels and emits a pass/fail report.

Usage:
  python3 run_regression.py --corpus corpus.yaml --baselines baselines/2026-04-21
  python3 run_regression.py --corpus corpus.yaml --baselines baselines/2026-04-21 --out report.md

Exit code: 0 if all entries pass (or are SKIPPED with missing baselines), 1 if any fail.

Semantics (see README.md for label discipline):
  - Single value label: exact match required.
  - Range [min, max]: actual value must satisfy min <= actual <= max.
  - List of acceptable values (for strings): actual must be in the list.
  - null: actual must be null or absent.
  - Omitted tilt in baseline: treated as 0 (schema convention).
  - *_contains list: every substring must appear (case-insensitive) in at least
    one element of the target list.
  - *_must_not_contain list: no substring may appear in the target list.
  - *_min confidence thresholds: actual confidence >= threshold.
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML required. Install: pip install pyyaml\n")
    sys.exit(2)


def load_yaml(path: Path):
    with path.open() as f:
        return yaml.safe_load(f)


def in_range(actual, rng):
    """rng is [min, max]. actual must satisfy min <= actual <= max."""
    if actual is None:
        return False
    lo, hi = rng
    return lo <= actual <= hi


# Factor aliases per loader.md §3. Collapse rule: if both canonical and synonym are set,
# canonical wins; if only synonym is set, synonym wins. Expected-label lookups try both.
FACTOR_ALIASES = {
    "quality": "profitability",
    "defensive": "low_volatility",
}
FACTOR_CANONICAL_TO_ALIAS = {v: k for k, v in FACTOR_ALIASES.items()}


def tilt_actual(baseline_tilts: dict, category: str, key: str):
    """Return the actual tilt value. Omitted = 0 (schema convention: omitted = neutral).

    For factors, apply the alias collapse rule: if the requested key is a synonym
    (e.g., 'quality') and the baseline uses the canonical name ('profitability'),
    return the canonical value. Vice versa for new-schema labels referring to
    canonical when baseline used the synonym.
    """
    cat = baseline_tilts.get(category, {}) or {}
    if category == "factors":
        canonical = FACTOR_ALIASES.get(key)            # key is a synonym → canonical exists
        synonym = FACTOR_CANONICAL_TO_ALIAS.get(key)   # key is canonical → synonym exists
        # Canonical wins on conflict per loader.md §3
        if canonical and canonical in cat:
            return cat[canonical]
        if synonym and key in cat:
            return cat[key]
        if key in cat:
            return cat[key]
        if synonym and synonym in cat:
            return cat[synonym]
        return 0
    return cat.get(key, 0)


def style_actual(baseline_tilts: dict, flat_key: str):
    """Handle cap_size_large -> styles.cap_size.large, growth_value_value -> styles.growth_value.value."""
    styles = baseline_tilts.get("styles", {}) or {}
    if flat_key.startswith("cap_size_"):
        return (styles.get("cap_size") or {}).get(flat_key[len("cap_size_"):], 0)
    if flat_key.startswith("growth_value_"):
        return (styles.get("growth_value") or {}).get(flat_key[len("growth_value_"):], 0)
    return styles.get(flat_key, 0)


def check_contains(target_list, needle_list, case_insensitive=True):
    """Every needle must appear as substring in at least one element of target_list."""
    missing = []
    if not target_list:
        target_list = []
    haystack = [str(x).lower() if case_insensitive else str(x) for x in target_list]
    for needle in needle_list or []:
        n = needle.lower() if case_insensitive else needle
        if not any(n in h for h in haystack):
            missing.append(needle)
    return missing


def check_must_not_contain(target_list, forbidden_list, case_insensitive=True):
    """No forbidden substring may appear in target_list."""
    violations = []
    if not target_list:
        target_list = []
    haystack = [str(x).lower() if case_insensitive else str(x) for x in target_list]
    for forbidden in forbidden_list or []:
        f = forbidden.lower() if case_insensitive else forbidden
        if any(f in h for h in haystack):
            violations.append(forbidden)
    return violations


def check_metadata(expected_meta, baseline_meta):
    failures = []
    for key, exp in (expected_meta or {}).items():
        if key == "view_name_contains":
            actual_name = baseline_meta.get("view_name", "") or ""
            for needle in exp:
                if needle.lower() not in actual_name.lower():
                    failures.append(f"metadata.view_name missing substring '{needle}' (got: '{actual_name}')")
        else:
            actual = baseline_meta.get(key)
            if isinstance(exp, list) and len(exp) == 2 and all(isinstance(x, (int, float)) for x in exp):
                if not in_range(actual, exp):
                    failures.append(f"metadata.{key} = {actual} not in range {exp}")
            else:
                if actual != exp:
                    failures.append(f"metadata.{key} = {actual!r}, expected {exp!r}")
    return failures


def check_tilt_category(expected_cat: dict, baseline_tilts: dict, category_name: str):
    """category_name in {sectors, regions, factors, themes}."""
    failures = []
    for key, rng in (expected_cat or {}).items():
        actual = tilt_actual(baseline_tilts, category_name, key)
        if not in_range(actual, rng):
            failures.append(f"tilts.{category_name}.{key} = {actual} not in range {rng}")
    return failures


def check_styles(expected_styles: dict, baseline_tilts: dict):
    failures = []
    for flat_key, rng in (expected_styles or {}).items():
        actual = style_actual(baseline_tilts, flat_key)
        if not in_range(actual, rng):
            failures.append(f"tilts.styles.{flat_key} = {actual} not in range {rng}")
    return failures


def check_macro_regime(expected_mr: dict, baseline_tilts: dict):
    failures = []
    baseline_mr = baseline_tilts.get("macro_regime", {}) or {}
    for field, exp in (expected_mr or {}).items():
        actual = baseline_mr.get(field, None)
        if exp is None:
            if actual is not None:
                failures.append(f"tilts.macro_regime.{field} = {actual!r}, expected null")
        elif isinstance(exp, list):
            # List of acceptable string values, OR [null, "value"] accepts either
            if actual not in exp:
                failures.append(f"tilts.macro_regime.{field} = {actual!r}, expected one of {exp!r}")
        else:
            if actual != exp:
                failures.append(f"tilts.macro_regime.{field} = {actual!r}, expected {exp!r}")
    return failures


def check_excludes(expected_tilts: dict, baseline_tilts: dict):
    failures = []
    excludes = baseline_tilts.get("excludes", []) or []
    excludes_freeform = baseline_tilts.get("excludes_freeform", []) or []
    combined = excludes + excludes_freeform

    missing = check_contains(combined, expected_tilts.get("excludes_contains"))
    for m in missing:
        failures.append(f"excludes missing required substring '{m}' (searched: {combined})")

    missing_ff = check_contains(excludes_freeform, expected_tilts.get("excludes_freeform_contains"))
    for m in missing_ff:
        failures.append(f"excludes_freeform missing required substring '{m}' (searched: {excludes_freeform})")

    violations = check_must_not_contain(combined, expected_tilts.get("excludes_must_not_contain"))
    for v in violations:
        failures.append(f"excludes must not contain '{v}' but found it")

    return failures


def check_confidence(expected_conf: dict, baseline_conf: dict):
    failures = []
    for key, threshold in (expected_conf or {}).items():
        if not key.endswith("_min"):
            continue
        field = key[:-len("_min")]
        actual = (baseline_conf or {}).get(field)
        if actual is None:
            failures.append(f"extraction_confidence.{field} missing (threshold {threshold})")
        elif actual < threshold:
            failures.append(f"extraction_confidence.{field} = {actual} < threshold {threshold}")
    return failures


def compare_entry(corpus_entry: dict, baseline: dict) -> list:
    expected = corpus_entry["expected"] or {}
    failures = []
    failures += check_metadata(expected.get("metadata"), baseline.get("metadata") or {})

    tilts_exp = expected.get("tilts") or {}
    baseline_tilts = baseline.get("tilts") or {}
    failures += check_tilt_category(tilts_exp.get("sectors_nonzero"), baseline_tilts, "sectors")
    failures += check_tilt_category(tilts_exp.get("regions_nonzero"), baseline_tilts, "regions")
    failures += check_tilt_category(tilts_exp.get("factors_nonzero"), baseline_tilts, "factors")
    failures += check_tilt_category(tilts_exp.get("themes_nonzero"), baseline_tilts, "themes")
    failures += check_styles(tilts_exp.get("styles"), baseline_tilts)
    failures += check_macro_regime(tilts_exp.get("macro_regime"), baseline_tilts)
    failures += check_excludes(tilts_exp, baseline_tilts)

    failures += check_confidence(expected.get("extraction_confidence"), baseline.get("extraction_confidence") or {})

    return failures


def main():
    ap = argparse.ArgumentParser(description="Run regression corpus against baseline extractions.")
    ap.add_argument("--corpus", required=True, help="Path to corpus.yaml")
    ap.add_argument("--baselines", required=True, help="Directory containing <entry_id>.yaml extractions")
    ap.add_argument("--out", help="Optional output path for markdown report")
    args = ap.parse_args()

    corpus = load_yaml(Path(args.corpus))
    baselines_dir = Path(args.baselines)

    lines = []
    lines.append(f"# Regression Corpus Report\n")
    lines.append(f"**Corpus:** `{args.corpus}` (v{corpus.get('version', '?')}, seeded {corpus.get('seeded_at', '?')})")
    lines.append(f"**Baselines dir:** `{args.baselines}`\n")

    n_pass, n_fail, n_skip = 0, 0, 0
    total_conf = []

    for entry in corpus.get("entries", []):
        entry_id = entry["entry_id"]
        baseline_path = baselines_dir / f"{entry_id}.yaml"

        lines.append(f"## {entry_id}")
        lines.append(f"- Source: `{entry['source_file']}`")
        lines.append(f"- View family: {entry.get('view_family', '?')}")

        if not baseline_path.exists():
            lines.append(f"- **SKIPPED** — no baseline at `{baseline_path}`\n")
            n_skip += 1
            continue

        baseline = load_yaml(baseline_path)
        failures = compare_entry(entry, baseline)

        # Aggregate confidence
        conf = (baseline.get("extraction_confidence") or {})
        vals = [v for v in conf.values() if isinstance(v, (int, float))]
        if vals:
            mean_c = sum(vals) / len(vals)
            total_conf.append(mean_c)
            lowest_field = min(conf.items(), key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 1.0)
            lines.append(f"- Mean confidence: {mean_c:.2f} (lowest: {lowest_field[0]}={lowest_field[1]:.2f})")

        if not failures:
            lines.append(f"- **PASS** — all {len(entry.get('expected', {}))} label categories matched\n")
            n_pass += 1
        else:
            lines.append(f"- **FAIL** — {len(failures)} mismatch(es):")
            for f in failures:
                lines.append(f"  - {f}")
            lines.append("")
            n_fail += 1

    lines.append(f"## Summary")
    lines.append(f"- PASS: {n_pass}")
    lines.append(f"- FAIL: {n_fail}")
    lines.append(f"- SKIPPED: {n_skip}")
    if total_conf:
        lines.append(f"- Mean-of-means confidence across passing entries: {sum(total_conf)/len(total_conf):.2f}")
    lines.append("")

    report = "\n".join(lines)
    print(report)

    if args.out:
        Path(args.out).write_text(report)

    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
