# Evals — wall-clock benchmark harness for skill changes

Lightweight runner for timing fresh-session `/parallax-*` invocations. Use this
to **validate that a change actually improved end-to-end latency**, not just
that the code looks faster on paper. The skill SKILL.md is cached at session
start (per `CONTRIBUTING.md`), so the only honest way to test SKILL.md edits
is a fresh `claude -p` session — that's what this harness wraps.

## Layout

```
evals/
├── README.md          # this file
├── bench.sh           # run one prompt, time it, log
├── compare.sh         # run a prompt across two git refs, summarize delta
├── portfolios/        # reusable JSON test portfolios
│   ├── small_5.json
│   └── medium_10.json
└── results/           # gitignored; accumulates timings locally
```

## Single-run timing

```bash
# Time one invocation — saves output + timing under evals/results/
./evals/bench.sh "/parallax-morning-brief $(cat evals/portfolios/small_5.json)"
```

The label defaults to `git rev-parse --short HEAD`. Override:

```bash
./evals/bench.sh "/parallax-morning-brief $(cat evals/portfolios/small_5.json)" pre-fix-baseline
```

## Comparing two commits (typical pre/post change workflow)

```bash
# Compare two refs, 3 runs each, take median
./evals/compare.sh \
  "/parallax-morning-brief $(cat evals/portfolios/small_5.json)" \
  HEAD~1 HEAD 3
```

Refuses to run if the working tree is dirty (would be lost on `git checkout`).
Restores the original branch on exit.

The summary prints the median wall-clock for each ref and the delta. **Run at
similar times of day** — Parallax MCP server load varies and a 2× swing is
within normal variance for a single run. Median over 3+ runs filters most of it.

## Caveats

- **Wall-clock only in v1.** Token usage, individual MCP call durations, and
  parallelism observation are out of scope for now. If you want those,
  `claude -p --output-format stream-json` exposes a verbose tool-use stream
  that can be parsed.
- **Server load is the dominant noise term.** A 30s run today might be 10s
  tomorrow on the same code. Always measure pre/post under the same
  conditions, and treat single-run differences <5s as noise.
- **Async tools are not bounded.** `get_news_synthesis`, `get_assessment`, and
  `get_financial_analysis` can take 30-90s independently of the skill's
  parallelization quality. Skills that wait on these will dominate the
  wall-clock regardless of per-holding batching. Look at the output for
  `"news": "pending"` markers to identify async-bound runs.
- **Holdings size matters.** Per-holding parallelization wins scale linearly
  with N. A 5-holding portfolio shows ~1/2 the absolute saving of a 10-holding
  one. Always benchmark the size you actually care about.

## Saving and sharing observations

`evals/results/` is gitignored. If you want to commit a notable finding (a
significant regression, a confirmed improvement), copy the relevant `.time`
file under `notes/archive/` (also gitignored — local-only) with a short
description, or paste the key numbers into a `DECISIONS.md` entry if it
informs a strategic call.

Don't commit raw results to the public repo — they leak server-load info and
specific portfolio examples. The harness is public; the data isn't.

## Adding new test portfolios

Drop a `<name>.json` into `evals/portfolios/` with the standard holdings
shape: `[{"symbol":"<RIC>","weight":<float>}, ...]`, weights summing to 1.0.
Keep them small (≤15 holdings) and use generic public tickers.

---

## Quality evals (v2) — grading, not just timing

v1 (above) times latency. v2 adds a **two-tier quality signal** (deterministic
structural checks + LLM-as-judge rubric) on top of a **spec-driven, skill-agnostic
grading engine** (design: `notes/2026-05-29-skillopt-eval-substrate-design.md`,
local-only). Latency timing is retained (it becomes the Stage-2 Tier-3
non-regression check); v2 supersedes only the "no quality scoring" caveat.

### Layout (v2 additions)

```
evals/
├── graders/             # skill-agnostic engine + pure-function tests (CI-safe)
│   ├── eval_spec.py        # EvalSpec dataclass — the per-skill contract
│   ├── tier1_structural.py # deterministic structural check registry (hard gate)
│   ├── judge_criteria.py   # Tier-2 rubric criteria (should-i-buy baseline set)
│   ├── run_judge.py        # pinned-Anthropic rubric judge (allowlist-guarded)
│   ├── transcript.py       # stream-json → final-prose extraction
│   └── test_*.py           # pure-function unit tests (the only thing CI runs)
├── skills/              # per-skill eval specs (one eval_config.py each)
│   ├── should-i-buy/       # reference baseline spec
│   ├── AI-buffett/         # different output family — its own checks
│   ├── client-review/      # adviser-facing directive recommendations
│   ├── explain-portfolio/  # reactive drawdown attribution
│   ├── morning-brief/      # fund-manager daily regime/health brief
│   ├── portfolio-builder/  # constructive thesis-to-allocation
│   ├── rebalance/          # prioritized trades + quantified targets
│   ├── watchlist-monitor/  # score-surveillance scan (no weights)
│   ├── deep-dive/          # single-position research (structural-only)
│   ├── portfolio-checkup/  # DRAFT — spec only, never run live
│   └── stress-test-thesis/ # DRAFT — thesis decomposition; spec only, never run live
├── tasks/<skill>/core.jsonl  # eval task inputs per skill
├── fixtures/<skill>/       # golden + broken stream-json transcripts (offline tests)
├── rollout/run_rollout.sh  # one live stream-json rollout
└── baseline/run_baseline.sh  # n>=3 rollouts/task → noise-floor report
```

### Skills with evals

- `should-i-buy` — the reference baseline spec.
- `AI-buffett` — a different output family (plain-line labels, citation/verdict
  contract); declares its own required sections and skill-specific checks.
- `client-review` — adviser-facing directive recommendations; includes suitability assessment and actionable recommendation checks.
- `explain-portfolio` — reactive drawdown attribution; includes return verification and divergence verdict (Transient/Fundamental) checks.
- `morning-brief` — fund-manager daily regime/health brief; includes 800-word limit and macro-snapshot grounding checks.
- `portfolio-builder` — constructive thesis-to-allocation; includes holdings-allocated check (weights + scores).
- `rebalance` — prioritized trades + quantified targets; includes trade-recs-quantified check.
- `watchlist-monitor` — score-surveillance scan (no weights); includes score-changes-quantified check.
- `deep-dive` — single-position research; includes technical-fallback structural check.
- `portfolio-checkup` — **DRAFT spec only, never run.** Same output family as
  should-i-buy.
- `stress-test-thesis` — **DRAFT spec only, never run.** Different output family
  (Assumption Map + per-assumption status table + World Verdict; no per-stock
  scorecard). Makes no buy/sell/hold call — `verdict_no_rec` is the analogue of
  should-i-buy's `bottom_line_no_rec`. Core tasks are Pass-1-only; the §9.5
  two-pass client-conditioning acceptance test needs paired-run support the
  single-transcript engine doesn't have yet, so it stays a manual live test.

### Key scripts

- `rollout/run_rollout.sh '<args>' [lang]` — one live stream-json rollout.
- `graders/tier1_structural.py` — deterministic structural checks (Tier-1, hard gate).
- `graders/run_judge.py` + `judge_criteria.py` — pinned-Anthropic rubric judge (Tier-2).
  The judge model is allowlist-guarded — non-Anthropic models abort (perimeter).
- `baseline/run_baseline.sh [--skill NAME] [--dry-run] [-n N]` — the headline
  deliverable: n>=3 rollouts/task -> pass-rate + variance noise-floor report in
  `results/`. `--skill` loads `evals/skills/<name>/eval_config.py`, so the
  runner uses the selected skill's slash command, task file, output prefix, and
  Tier-2 criteria.
- `baseline/score_existing.py --skill NAME evals/results/<prefix>_baseline_*.stream.json`
  — offline Tier-1 scoring for already-captured rollouts; no live token spend.

Example dry-runs before spending tokens:

```bash
./evals/baseline/run_baseline.sh --skill rebalance --dry-run -n 3
./evals/baseline/run_baseline.sh --skill portfolio-builder --dry-run -n 3
```

**CI runs only the pure-function unit tests — never a live rollout:**
`cd evals && python3 -m pytest graders -q`

Live rollouts (`run_rollout.sh`, `run_baseline.sh` without `--dry-run`) cost Parallax
tokens and are run manually.

## Adding a new skill eval

Each skill's eval is one `skills/<skill>/eval_config.py` exporting a `SPEC =
EvalSpec(...)`. The engine (`graders/`) is shared; the spec is where you declare
what *this* skill's output must contain:

1. Create `evals/skills/<skill>/eval_config.py` with an `EvalSpec` — set
   `required_sections`, `check_ids` (from the Tier-1 registry), and
   `tier2_criteria`. Copy the nearest-family spec as a starting point
   (`should-i-buy` for structured-English research output) and prune to fit.
2. Add task inputs at `evals/tasks/<skill>/core.jsonl`.
3. For offline regression, drop golden + broken stream-json transcripts under
   `evals/fixtures/<skill>/` and assert against them in a `graders/test_*.py`.
