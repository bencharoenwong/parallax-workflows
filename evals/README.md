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
