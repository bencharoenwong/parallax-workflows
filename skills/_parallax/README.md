# Parallax shared layer (`_parallax/`)

<!-- authority: contract -->
<!-- verified: 2026-09-05 -->
<!-- overrides: none -->

The shared layer every `parallax-*` skill reads. This file is the map; it states nothing the files below own.

## The system in six layers

| Layer | What | Where |
|---|---|---|
| L5 | Operator intent | the command the operator typed |
| L4 | Skill orchestrator | `skills/parallax-<name>/SKILL.md` — one workflow, one output contract |
| L3 | Shared contracts | this directory's `.md` files (each declares `authority: contract`, `registry`, or `observation` in its header) |
| L2 | Deterministic helpers | this directory's `.py` modules and each skill's own helpers — math, gates, renderers; invoked, never re-derived in prose |
| L1 | Host primitives | `parallax-conventions.md` §14 — the nine primitives and their per-host bindings |
| L0 | Parallax MCP | the live tool contract; discovered each session, never remembered (§0.1) |

Start with `parallax-conventions.md` (runtime rules) and `skill-structure-conventions.md` (how a SKILL.md is shaped). Everything else is JIT-loaded from a skill when it names the file.

## Interpreter

CI runs Python 3.13 (`.github/workflows/evals.yml`). The local commit gate's pytest binary is pinned to Python 3.11. `scripts/build_bundle.py` declares 3.9 or newer. Every helper a SKILL.md shells out to is invoked as bare `python3`, so keep helpers compatible with 3.11 through 3.13 and stdlib-only unless the helper's directory ships a `requirements.txt` (`house-view/`, `white-label/`, `client-policy/`).

## Environment switches

| Variable | Read by | Effect |
|---|---|---|
| `PARALLAX_LOADER_V2` | consumer skills | universe construction and portfolio scoring path — `parallax-conventions.md` §0 |
| `PARALLAX_HOUSE_VIEW_DIR` | `house-view/` modules | overrides `~/.parallax/active-house-view/` — `house-view/README.md` |
| `PARALLAX_GATE_MODE` | `scripts/run-gate-tests.sh` | `network` opts in to the `npx`-marked linter smoke; default is offline |
| `PARALLAX_E2E_LIVE`, `PARALLAX_E2E_SPEND`, `PARALLAX_S1_INTEGRATION` | `scripts/run-gate-tests.sh` | blanked in offline mode so live-MCP and spend-gated tests cannot fire in the gate |
| `PARALLAX_ALLOW_PARTIAL_SCAN` | `scripts/build_bundle.py`, `scripts/scan_tracked_terms.py` | permits a scan without the local extra-terms file (CI); the full-strength scan needs that file |
| `PARALLAX_MCP_ALIASES`, `PARALLAX_MCP_FOREIGN_NAMESPACES` | `evals/graders/token_model.py` | namespace attribution for metered calls — `evals/README.md` |
| `PARALLAX_HOOKS_FORCE` | `scripts/install_git_hooks.sh` | overrides the installer's refusal on an unusual hooks layout |

## Test topology (what a contributor cannot see from the tree)

- One `conftest.py` per gate root. `skills/_parallax` spends its budget on `white-label/tests/conftest.py`; `scripts/` tests import `scripts/canary_fixture.py` instead. `run-gate-tests.sh` asserts this.
- `run-gate-tests.sh` auto-discovers roots (`--list-roots`). `.github/workflows/evals.yml` does not: a new skill with tests needs a step added there. `scripts/test_ci_root_parity.py` catches the omission after the fact.
- The full-strength term scan and the bundle build need `~/.claude/parallax-canary-extra.txt`, a local-only file. A fresh clone runs the partial scan only.

## Gate order before a push

1. `python3 skills/_parallax/scripts/build_bundle.py plugin` when any bundled source changed (the tracked-bundle test fails until it has run).
2. `python3 skills/_parallax/scripts/scan_tracked_terms.py`
3. `bash skills/_parallax/scripts/run-gate-tests.sh`
4. `python3 skills/_parallax/scripts/scan_commit_messages.py`
