"""Batch-grade a live corpus rollout and report a variance pass.

Reads every `evals/results/<prefix>_<label>-*.stream.json` produced by run_corpus.sh,
grades each with the tier-1 structural checks, and — for tasks run more than once —
reports the STABILITY of the model's judgments (Assumption Strength light, hype reading,
coverage classification, load-bearing ranking) across the repeats.

Infrastructure failures (auth 401, empty transcript, connector missing) are detected and
reported SEPARATELY from skill failures: an empty transcript is not the skill's fault, and
counting it as a skill failure is the exact mistake this pipeline exists to prevent.

Pure helpers (detect_infra_failure / extract_readings / id_from_filename / stability) carry
no I/O and are unit-tested in test_grade_corpus.py. Only `main` touches the filesystem.

Usage:
    python3 evals/graders/grade_corpus.py <label> [--prefix stress-test-thesis]
"""
from __future__ import annotations

import argparse
import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "skills" / "stress-test-thesis"))

from transcript import parse_stream_json  # noqa: E402
from tier1_structural import grade_tier1  # noqa: E402
from eval_spec import load_spec  # noqa: E402

_RESULTS = _HERE.parent / "results"

# --- pure helpers -----------------------------------------------------------

_AUTH_RE = re.compile(r'"error_status":\s*401|authentication_failed|Invalid authentication', re.I)
_RESULT_RE = re.compile(r'"type":\s*"result"')
_EMPTY_MCP_RE = re.compile(r'"mcp_servers":\s*\[\s*\]')


def detect_infra_failure(raw: str) -> str | None:
    """Return an infrastructure-failure reason for a stream, or None if the run is gradeable.

    Distinguishes 'the harness/connector broke' from 'the skill produced a bad report' — the
    two must never be conflated (an auth 401 yields an empty report that would otherwise be
    mis-scored as a skill failure)."""
    if not raw.strip():
        return "empty stream (no output captured)"
    if _AUTH_RE.search(raw):
        return "authentication error (401) — no valid credentials in the session"
    if not _RESULT_RE.search(raw):
        return "no result event — run interrupted/aborted"
    if _EMPTY_MCP_RE.search(raw) and "parallax" not in raw.lower():
        return "no Parallax MCP server loaded (connector missing)"
    return None


def _light(prose: str, section_kw: str, labels: tuple[str, ...]) -> str | None:
    """The `<glyph> <Label>` reading bound on the first matching line (adjacency-bound,
    mirroring the tier-1 checks so the variance view agrees with the grader)."""
    pat = re.compile(r"(🔴|🟡|🟢)\s*\**\s*\b(" + "|".join(labels) + r")\b", re.I)
    for line in prose.splitlines():
        if section_kw in line.lower():
            m = pat.search(line)
            if m:
                return f"{m.group(1)} {m.group(2).title()}"
    # fall back to first line anywhere carrying a bound reading
    for line in prose.splitlines():
        m = pat.search(line)
        if m and section_kw in prose.lower():
            return f"{m.group(1)} {m.group(2).title()}"
    return None


def extract_readings(prose: str) -> dict:
    """The four judgment signals whose stability we track across repeated runs."""
    strength = _light(prose, "assumption strength", ("weak", "mixed", "strong"))
    hype = _light(prose, "bias & conviction", ("low", "elevated", "high"))
    cov = None
    lines = prose.splitlines()
    for i, l in enumerate(lines):
        if re.match(r"#*\s*coverage notice", l.strip(), re.I):
            body = " ".join(lines[i + 1:i + 4]).lower()
            cov = next((k for k in ("out-of-scope", "out of scope", "partial", "full") if k in body), None)
            break
    lb: list[str] = []
    cap = False
    for l in lines:
        if re.match(r"#*.*load-bearing", l.strip(), re.I):
            cap = True
            continue
        if cap and re.match(r"#+\s", l.strip()):
            break
        if cap:
            for m in re.findall(r"\b([a-z]+-\d+)\b", l):
                if m not in lb:
                    lb.append(m)
    return {"strength": strength, "hype": hype, "coverage": cov, "load_bearing": lb[:4]}


def id_from_filename(name: str, prefix: str, label: str) -> str | None:
    """Recover the corpus task id from a run_corpus.sh filename.

    run_corpus.sh labels each run `<label>-<id>-<i>`, so the file is
    `<prefix>_<label>-<id>-<i>_<safe>_<ts>.stream.json`. Task ids carry underscores but no
    hyphens, so the id is the token between `<label>-` and the next hyphen."""
    stem = f"{prefix}_{label}-"
    if not name.startswith(stem):
        return None
    rest = name[len(stem):]
    return rest.split("-", 1)[0] or None


def stability(values: list) -> dict:
    """Summarize a list of readings from repeated runs: unique set + whether it never moved."""
    norm = [tuple(v) if isinstance(v, list) else v for v in values]
    uniq = list(dict.fromkeys(norm))
    return {"n": len(values), "unique": uniq, "stable": len(uniq) <= 1}


# --- CLI --------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--prefix", default="stress-test-thesis")
    ap.add_argument("--results", default=str(_RESULTS))
    args = ap.parse_args(argv)

    spec = load_spec(args.prefix)
    pattern = str(Path(args.results) / f"{args.prefix}_{args.label}-*.stream.json")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"no result files match {pattern}", file=sys.stderr)
        return 5

    by_id: dict[str, list] = defaultdict(list)
    infra: list[tuple[str, str]] = []
    skill_fail = 0

    print(f"\n=== corpus grade: label={args.label} ({len(files)} run(s)) ===")
    for f in files:
        name = Path(f).name
        tid = id_from_filename(name, args.prefix, args.label) or "?"
        raw = Path(f).read_text()
        reason = detect_infra_failure(raw)
        if reason:
            infra.append((tid, reason))
            print(f"  [INFRA] {tid:22s} {reason}")
            continue
        t = parse_stream_json(raw)
        checks = grade_tier1(t, spec)
        fails = [c.name for c in checks if not c.passed]
        readings = extract_readings(t.final_prose)
        by_id[tid].append(readings)
        ok = not fails
        skill_fail += 0 if ok else 1
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] {tid:22s} tier1 {len(checks)-len(fails)}/{len(checks)}"
              f"  strength={readings['strength']} hype={readings['hype']} cov={readings['coverage']}"
              + (f"  fails={fails}" if fails else ""))

    # variance pass — only meaningful for ids run more than once
    printed_hdr = False
    for tid, runs in by_id.items():
        if len(runs) < 2:
            continue
        if not printed_hdr:
            print("\n--- variance (repeated runs) ---")
            printed_hdr = True
        for key in ("strength", "hype", "coverage", "load_bearing"):
            s = stability([r[key] for r in runs])
            flag = "STABLE " if s["stable"] else "UNSTABLE"
            print(f"  {tid:22s} {key:13s} [{flag}] {s['unique']}")

    print("\n--- summary ---")
    print(f"  graded runs : {sum(len(v) for v in by_id.values())}")
    print(f"  skill fails : {skill_fail}")
    print(f"  infra fails : {len(infra)}")
    if infra:
        print("  NOTE: infra fails are NOT skill failures — fix the harness/connector, then re-run.")
    # exit codes: 2 = infra problem (inconclusive), 1 = a real skill failure, 0 = clean
    return 2 if infra else (1 if skill_fail else 0)


if __name__ == "__main__":
    raise SystemExit(main())
