"""Tier-2 rubric judge driver.

Renders one prompt per criterion from the immutable template and scores it with a
PINNED Anthropic model via `claude -p`. A hard allowlist guard refuses any
non-Anthropic model (perimeter enforcement). The live judge call is intentionally
NOT exercised in CI — only the guard and prompt rendering are unit-tested.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from judge_criteria import CRITERIA
from transcript import Transcript, load_transcript

_TEMPLATE_PATH = Path(__file__).parent / "rubric_judge.md"
ALLOWED_MODEL_PREFIXES = ("claude-",)
DEFAULT_JUDGE_MODEL = "claude-opus-4-8"


def check_model(model: str) -> None:
    """Abort unless `model` is an allowlisted Anthropic model (perimeter guard)."""
    if not any(model.startswith(p) for p in ALLOWED_MODEL_PREFIXES):
        sys.stderr.write(
            f"PERIMETER ABORT: judge model '{model}' is not on the Anthropic allowlist "
            f"{ALLOWED_MODEL_PREFIXES}. Skill content must never be sent to an external model.\n"
        )
        raise SystemExit(2)


def render_prompt(criterion: dict, prose: str) -> str:
    template = _TEMPLATE_PATH.read_text()
    return (
        template.replace("{statement}", criterion["statement"])
        .replace("{pass_when}", criterion["pass_when"])
        .replace("{prose}", prose)
    )


def _parse_verdict(crit_id: str, returncode: int, stdout: str, stderr: str) -> dict:
    """Pure: map a `claude -p --output-format json` result to {id, pass, reason}.

    `pass` is True/False ONLY when the judge returned an explicit boolean;
    anything else (non-zero exit, null/empty/garbage result, missing key) yields
    `pass=None` so it is excluded from the pass-rate rather than silently counted
    as a fail. Never raises — graceful degradation for the batch loop.
    """
    if returncode != 0:
        return {"id": crit_id, "pass": None, "reason": f"judge error: {stderr.strip()[:200]}"}
    try:
        envelope = json.loads(stdout)
        raw = envelope.get("result") if isinstance(envelope, dict) else None
        verdict = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        val = verdict.get("pass") if isinstance(verdict, dict) else None
        if val is True or val is False:
            return {"id": crit_id, "pass": val, "reason": str(verdict.get("reason", ""))}
        return {"id": crit_id, "pass": None, "reason": "judge returned no explicit pass verdict"}
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        return {"id": crit_id, "pass": None, "reason": f"unparseable judge output: {exc}"}


def judge_one(criterion: dict, prose: str, model: str) -> dict:
    """Run a single criterion through the pinned judge. Returns {id, pass, reason}."""
    check_model(model)
    prompt = render_prompt(criterion, prose)
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--output-format", "json"],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"id": criterion["id"], "pass": None, "reason": "judge timeout after 180s"}
    return _parse_verdict(criterion["id"], proc.returncode, proc.stdout, proc.stderr)


def grade_tier2(t: Transcript, model: str = DEFAULT_JUDGE_MODEL) -> list[dict]:
    check_model(model)
    return [judge_one(c, t.final_prose, model) for c in CRITERIA]


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier-2 rubric judge")
    ap.add_argument("transcript", nargs="?", help="path to a .stream.json transcript")
    ap.add_argument("--model", default=DEFAULT_JUDGE_MODEL)
    ap.add_argument("--check-model", action="store_true", help="validate the model allowlist and exit")
    args = ap.parse_args()
    if args.check_model:
        check_model(args.model)
        print(f"OK: {args.model} is on the Anthropic allowlist")
        return 0
    if not args.transcript:
        ap.error("transcript path required unless --check-model")
    verdicts = grade_tier2(load_transcript(args.transcript), args.model)
    print(json.dumps(verdicts, indent=2))
    passed = sum(1 for v in verdicts if v["pass"] is True)
    print(f"Tier-2 pass-rate: {passed}/{len(verdicts)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
