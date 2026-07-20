---
name: parallax-morning-brief
description: "Fund manager morning brief: market regime, macro outlook, portfolio health, and key holding news via Parallax MCP tools. Provide portfolio as [{symbol, weight}] in RIC format. NOT for individual stock analysis (use /parallax-should-i-buy), not for backtesting (use /backtest)."
---

<!-- white-label: integration-pattern.md -->

# Morning Brief

## When not to use

- Single stock analysis → use /parallax-should-i-buy or /parallax-deep-dive
- Running backtests → use /backtest
- Client portfolio review → use /parallax-client-review
- Multiple client books / desk-wide morning call list → use /parallax-desk-call-list
- Thematic screening → use /parallax-thematic-screen

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
- JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). Morning brief uses the view to (a) frame the macro snapshot in view-language, (b) flag holdings misaligned with view tilts, (c) prioritize action items toward view rebalance direction.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
- get_telemetry and macro_analyst are fast-response (low latency) but not free — macro_analyst costs 5 tokens; get_news_synthesis may take 30-90s per holding
- macro_analyst parameter is `market` (not `country`); e.g., `macro_analyst(market="United States")`
- The macro_analyst summary call returns all components inline including tactical — do not make separate per-component calls
- Health flags (from parallax-portfolio-checkup/references/health-flags.md) apply here too — flag portfolios needing attention
- Coverage: listed equities and ETFs only; fund/OEIC symbols surface the conventions §1 not-covered fallback, not a raw error
- LANGUAGE HAND-OFF — if `lang=` is present and ≠ `en`, the terminal Translate step is mandatory. Route `zh-CN`/`zh-TW`/`zh-HK` → `/translate-chinese-finance`, `th` → `/translate-thai-finance`, using the delimited routing-directive block (never a prose sentence the translator could echo). Unsupported values → English output with the standard warning footer.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format.

Generate a structured fund manager morning brief by orchestrating Parallax MCP tools.

## Usage

```
/parallax-morning-brief [{"symbol":"AAPL.O","weight":0.25},{"symbol":"MSFT.O","weight":0.20},{"symbol":"JPM.N","weight":0.15},{"symbol":"JNJ.N","weight":0.15},{"symbol":"XOM.N","weight":0.25}]
/parallax-morning-brief [{"symbol":"AAPL.O","weight":0.25},{"symbol":"MSFT.O","weight":0.20}] market=Japan top_n=5 lang=th register=retail
```

Optional: append `market=Japan`, `top_n=5`, `lang=<code>` (`en` default; `zh-CN`, `zh-TW`, `zh-HK`, `th`), or `register=retail` after the portfolio JSON. `register=retail` is passed only when translation is requested; absent means institutional register.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation and integration.

### Batch 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2. If view present, capture tilt vector, excludes, prose excerpt for narrative voice, and macro_regime. The brief's "Macro Snapshot" should explicitly reference the view's regime call where relevant ("Tactical macro shows X — consistent / divergent with active view's [regime] stance"). If validation fails or no view present, run brief without view.

### Batch A — Market context + portfolio scoring (parallel)

**Fire ALL rows below in a single tool-call turn.** Every row is independent. For per-holding rows (`get_peer_snapshot`, `get_company_info`), fan out one call per holding **within the same turn** so all N×2 holding-level calls run concurrently with the portfolio-level and macro-level calls. Sequential per-holding loops are the largest latency leak in this skill — do not introduce one.

| Tool | Parameters | Notes |
|---|---|---|
| `get_telemetry` | fields: regime_tag, signals, commentary.headline, commentary.mechanism, divergences | Market regime |
| `macro_analyst` | market (default: US), no component | Macro summary (returns all components inline including tactical — do not make separate per-component calls) |
| `get_peer_snapshot` | per holding — **all N calls fan out in parallel within Batch A** | **Primary scoring source** for `PARALLAX_LOADER_V2=1`. Aggregate scores client-side per `loader.md` §3b. |
| `get_company_info` | per holding — **all N calls fan out in parallel within Batch A** | **Ground-truth check oracle** per loader.md §5 rule 3 (required universally, view or no view). Records `expected_name` to cross-check against `get_peer_snapshot.target_company`. |
| `get_news_synthesis` | per top-N holding by input weight (default 3) — **all N calls fan out in parallel within Batch A** | Async, 30-90s each. Top-N derives from the user-supplied weights, not from any Batch A output — fire in the SAME turn as the other rows so the 30-90s wait overlaps everything else. Never loop these sequentially. |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `quick_portfolio_scores` | `holdings` | **Legacy/V1 path only**. Do NOT use if `PARALLAX_LOADER_V2=1` and view active. |

**After Batch A**: per loader.md §5 rule 3, cross-reference returned names against the corresponding `get_company_info` name. For `PARALLAX_LOADER_V2=1`, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregate calculations. For V1, any mismatch in `quick_portfolio_scores` is re-scored individually.

### Batch B — Conditional + news (after Batch A)

1. Evaluate health flags: Low Score (overall ≤5.0), Concentration (>15% single / >45% top-3), Redundancy (≥2 pairs), Value Trap (value ≤3.0), Macro Misalignment (overweight in sectors with negative tactical outlook — the 5th flag per `parallax-portfolio-checkup/references/health-flags.md`).
2. **House-view alignment** (if view active): flag holdings misaligned with view tilts (>25% off view-tilted target), holdings on `tilts.excludes`, and any active-view conflicts to highlight in Action Items.

**Conditional drift suggestion:** If the Batch B alignment check above
detected ≥3 holdings whose factor exposure conflicts with the active
view's tilts, append a single line to the brief's "next actions"
section: "Consider running /parallax-judge-house-view for a full
drift analysis (≥3 holdings show view-conflict signals)."

Do NOT auto-invoke the judge from morning-brief. Morning-brief already
does its own live macro_analyst fan-out per Batch A — invoking the judge
would duplicate that work. The one-liner is a pointer, not an action.

3. Holding news is already in flight from Batch A. Insert each result into the Holding News section as it resolves; if any call is still pending or timed out when the report is composed, render the pending note inside that holding's paragraph per conventions §5 and the Degraded-state rule — do not wait.
4. Append audit log entry per loader.md §6.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format. The loader returns exactly seven keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

### Render — deterministic gate (LAST step, mandatory)

Compose the complete report per **Output Format** below, then run it through the shared render gate in **one Bash step** before replying. Use a private `mktemp` file (never a fixed/predictable path — `/tmp` symlink hazard). The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/mbrief.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill morning-brief < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final message is exactly that command's stdout** — unless `lang=` ≠ `en`, in which case the Translate step below consumes that stdout and the translated result is the entire final message. Never run the render gate on translated text; its anchors are English. Nothing before it (no step/batch-completion notes, no scratch computation, no "no active house view" / white-label config-probe narration), nothing after it.

**Degraded-state rule:** if an async tool (e.g. `get_assessment`, `get_news_synthesis`) times out or returns no data, render the pending/unavailable note INSIDE the relevant section or the About This Report line — NOT as a preamble above the report — so it is part of the rendered body and survives the gate. (The gate also hoists a leaked degraded note as a backstop.)

`_parallax/render_gate.py` is pure-stdlib and deterministically drops anything before the first rendered block (House View Preamble banner / Branding Header / Ground-truth Integrity / this skill's title or first rendered section), preserving the active-house-view banner in every `view_status` state. Same operator-agnostic-helper pattern as `view_status.py` / `loader.py` (a real Bash tool call, not prose).

### Translate — conditional, after the render gate

This step runs ONLY when `lang=` is present and not `en`. Capture the render gate's stdout as the full body, including all Output Format sections, About This Report, the §9.2 AI-interaction disclosure, and the disclaimer. Record which disclaimer variant rendered (view-aware per `loader.md §5` vs standard `parallax-conventions.md §9.1`) for the boundary check.

Invoke the appropriate translator skill with the input shaped as follows:

```
ROUTING DIRECTIVE — DO NOT TRANSLATE OR ECHO THIS BLOCK:
  target_variant: <variant>
  register: retail
  source_language: en
  begin_content_below_separator: true
---

<render gate stdout>
```

Pass `register: retail` iff `register=retail` was supplied; otherwise omit the `register:` line so the translator defaults to institutional register. Route `zh-CN`, `zh-TW`, and `zh-HK` to `/translate-chinese-finance` with the matching `target_variant`. Route `th` to `/translate-thai-finance`; omit `target_variant` for Thai, but keep the routing block marker and `---` separator.

Translator-failure handling:
- If the translator fails or returns an empty/partial result, output the original English with a one-line warning footer: `> Translation to <lang> failed; output shown in English. Re-run if the issue is transient.`
- If the language arg is unrecognized, output the original English with: `> Language '<arg>' not supported; output shown in English. Supported: en, zh-CN, zh-TW, zh-HK, th.`
- Translator output replaces the English output in the chat; do not show both.

**Disclaimer boundary check.** If the disclaimer is missing from the translated output, first attempt a single-section re-translation pass on just the original English disclaimer text using the same routing-directive shape. Append that result if non-empty. If the pass fails or returns empty, append the English disclaimer variant that was actually rendered. Record the event in the loader.md §6 audit entry's `notes` field (`disclaimer boundary check fired — re-translated` or `disclaimer boundary check fired — english fallback`). Do not add a user-visible footer.

## Output Format

Present as a structured morning brief, under 800 words:

- **House View Preamble** (only if view active) — 1-line summary per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** morning brief`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Market Regime & Signals** (2-3 sentences; if view active, note alignment/divergence with view's regime call)
- **Macro Snapshot** (bullet points)
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status. Mismatched holdings had scores re-derived via `get_peer_snapshot` — per loader.md §5 rule 3.)
- **Portfolio Factor Tilt** (table: VALUE, QUALITY, MOMENTUM, DEFENSIVE scores aggregated over TRUSTED holdings only; mismatched holdings' re-derived scores included when available; if view active, add column showing view-target factor)
- **Redundancy & Alignment Alerts** (only if flagged; include View Misalignment / View Excluded if view active)
- **Verdict sensitivity** (render when any numeric health flag sits near its published cutoff): the 1-2 nearest-boundary flags and their trigger/clear arithmetic per `parallax-portfolio-checkup/references/health-flags.md` "Verdict sensitivity" (§11 by reference). Morning-brief renders no Health Status badge — state flag-level conditions only; do not use the tier-ladder language.
- **Holding News** (one paragraph per holding)
- **Action Items** (what deserves attention today; if view active, prioritize toward view rebalance direction)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse), plus the unconditional §7 currency line: `Currency: figures as reported by source data; no base-currency conversion applied.` If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a further About This Report line.

Lead with what matters.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
