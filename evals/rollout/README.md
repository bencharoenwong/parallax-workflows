# Live-eval rollout runner (connector-access)

Runs a `/parallax-*` skill against **live Parallax data** in fresh `claude -p` sessions,
captures each as `stream-json`, and grades the batch — including a **variance pass** that
checks whether the model's judgments stay stable across repeated runs of the same input.

Fresh sessions are the point: `SKILL.md` is cached at session start, so a cold `claude -p`
is the only honest way to exercise a `SKILL.md` edit. These scripts are the harness; the
grading is in `../graders/`.

```
rollout/
├── run_rollout.sh          # one fresh session -> one stream.json (also used by should-i-buy)
├── run_corpus.sh           # batch: preflight, then one fresh session per planned run (+repeats)
├── preflight_connector.sh  # HARD GATE: verify auth + connector before spending a token
├── parallax.mcp.json.template  # copy -> parallax.mcp.json, fill in, keep OUT of git
└── README.md
```

## The connector-access contract

A spawned `claude -p` does **not** inherit an interactive session's login or its Claude.ai
connectors — by default it reports `mcp_servers: []` and returns HTTP 401. So the runner must
be *given* both, explicitly, via environment. Nothing here reads or stores a secret; you supply
them and they stay out of the repo.

| Env var | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | Authenticates the `claude -p` session (or run from an already-logged-in shell). |
| `MCP_CONFIG` | yes* | Path to a `.mcp.json` that defines the Parallax server (`--mcp-config`). *Not needed if the session already has the connector ambiently.* |
| `ALLOWED_TOOLS` | yes | Tool allowlist so a non-interactive run never stalls on a permission prompt — e.g. `"mcp__claude_ai_Parallax__*"`. |
| `STRICT_MCP` | optional | Any non-empty value adds `--strict-mcp-config` (only the supplied servers load — reproducible CI). |
| `TARGET_MODEL` | optional | Pin the model (e.g. a specific Claude version) for comparable runs. |

### Supplying the Parallax MCP config

```bash
cp evals/rollout/parallax.mcp.json.template evals/rollout/parallax.mcp.json
# edit parallax.mcp.json: set the real endpoint URL; keep the token as ${PARALLAX_MCP_TOKEN}
export PARALLAX_MCP_TOKEN=...          # never commit this
export MCP_CONFIG=evals/rollout/parallax.mcp.json
export ALLOWED_TOOLS="mcp__claude_ai_Parallax__*"
```

The real `parallax.mcp.json` is **gitignored** (only `.template` is tracked). The server key
name **must contain "Parallax"** — the preflight matches on it. Keep secrets in `${ENV_VARS}`,
not literals, so the file itself carries nothing sensitive.

> Note on Claude.ai OAuth connectors: if your Parallax access is a hosted Claude.ai connector
> rather than a plain HTTP MCP endpoint, replicating it as a local `.mcp.json` may need the
> connector's OAuth details. Either way, the contract is the same — **preflight must pass** —
> and the preflight tells you exactly which half (auth vs. connector) is missing.

## Preflight — the gate that stops silent spends

`preflight_connector.sh` runs one trivial `check_api_health` call in a fresh session and exits:

| exit | meaning |
|---|---|
| 0 | connector loaded, authenticated, health tool responded — safe to run the batch |
| 1 | auth error (401) — no valid credentials |
| 2 | no Parallax MCP server loaded — set `MCP_CONFIG` |
| 3 | `claude` CLI not on PATH |
| 4 | connector declared but the tool never executed — widen `ALLOWED_TOOLS` |

`run_corpus.sh` calls it first and **aborts the whole batch if it fails** — so a dead
connector costs one health probe, not a full corpus of empty, mis-graded 401 stubs. (That
exact failure — an empty transcript scored as a *skill* failure — is what this gate prevents.)

## Running a batch + variance pass

```bash
# 3x the canonical thesis (variance) + one each of the coverage/push-back cases
bash evals/rollout/run_corpus.sh \
  evals/tasks/stress-test-thesis/golden.jsonl live \
  "macro_led_long x3, weak_thesis, fx_carry_partial"

# grade everything under this label + report stability across the repeats
.venv/bin/python3 evals/graders/grade_corpus.py live
```

`grade_corpus.py` prints, per run, the tier-1 pass count and the four judgment signals
(Assumption Strength light, hype reading, Coverage classification, load-bearing ranking); for
any input run more than once it reports whether each signal was **STABLE** or **UNSTABLE**
across the repeats. **Infrastructure failures are counted separately from skill failures** and
never inflate the skill's fail rate. Exit codes: `0` clean, `1` a real skill failure, `2` an
infra problem (inconclusive — fix the harness and re-run).

## Calling it from CI

This repo intentionally ships **no** `.github/workflows/` (the `no-mistakes` push gate skips
`ci` for that reason — see the root `CLAUDE.md`). To wire live evals into CI, have the job
export the contract env (API key + `MCP_CONFIG` + `ALLOWED_TOOLS` from CI secrets), then call
`run_corpus.sh` followed by `grade_corpus.py` and fail the job on a non-zero grade. The scripts
are self-contained and secret-free; the secrets live only in the CI environment.
