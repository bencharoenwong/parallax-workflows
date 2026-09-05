---
name: parallax-score-explainer
description: "Explain Parallax scores, factors, and methodology in plain language. Why does a stock score this way? What would change it? Uses methodology docs and score data. NOT for stock analysis (use /parallax-should-i-buy), not for deep dives (use /parallax-deep-dive), not for portfolio diagnostics (use /parallax-portfolio-checkup)."
---

<!-- white-label: integration-pattern.md -->

# Score Explainer

## When not to use

- Stock analysis with buy/sell framing → use /parallax-should-i-buy
- Full position analysis → use /parallax-deep-dive
- Portfolio diagnostics → use /parallax-portfolio-checkup

## Gotchas

- Expected Parallax spend: 0–2 tokens (`_parallax/token-costs.md`): methodology-only questions are free; score data adds 1–2. `get_stock_report` (10, paid) only when a comprehensive explanation is explicitly needed.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §4 fallbacks, §11 (this skill's "What Would Change It" line is the grandfathered form), §13 audience mode, §14 host primitives, §15 translation.
- `explain_methodology` takes a topic string — be specific ("quality score", "momentum factor"). `get_docs` / `list_docs` reach the full methodology documentation. `get_score_analysis` shows the trajectory — the tool for "why did this change".
- Output must be readable by non-technical clients and compliance teams; this is the likeliest `register=retail` consumer.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- Not a house-view consumer: no loader step, no audit row.

Plain-language explanations of Parallax scores, factors, and methodology.

## Usage

```
/parallax-score-explainer AAPL.O "why is the value score so low?"
/parallax-score-explainer "what does the quality factor measure?"
/parallax-score-explainer TSLA.O "why did the score drop last month?"
/parallax-score-explainer "how does Shariah screening work?"
/parallax-score-explainer AAPL.O "why is the value score so low?" lang=zh-CN register=retail
/parallax-score-explainer AAPL.O "why is the value score so low?" audience=client_safe
```

The free-text question stays positional; keyword args: `lang=<code>` (`en` default; `zh-CN`, `zh-TW`, `zh-HK`, `th`), optional `register=retail` (passed only when translation is requested), optional `audience=client_safe | internal_analyst` (precedence per conventions §13.1).

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This is a multi-mode skill: the question type chosen in Step 1 selects the Step 2 branch; the spine is the same.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2, all three branches) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: optional symbol; question; `lang=`; `register=`; `audience=`.
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name` (seven-key loader; `branding["voice"]` raises `KeyError` by design).

### Step 1 — Resolve inputs

Classify the question: **(a) why does X score this way**, **(b) what does factor X mean**, **(c) why did the score change**. If a symbol is present, `call-tool` `get_company_info` (plain ticker → conventions §1).

### Step 2 — Fetch (parallel batches)

- **(a) why does X score this way:** `call-tool` `get_score_analysis` (52 weeks) and `get_peer_snapshot` together; then `explain_methodology` for each notably high or low factor; `get_docs` / `list_docs` if deeper methodology is needed.
- **(b) what does factor X mean:** `explain_methodology` for the concept; `list_docs` then `get_docs` for the relevant page.
- **(c) why did the score change:** `get_score_analysis` with `weeks` covering the change period (typed int — conventions §0.2) and `get_news_synthesis` together; then `explain_methodology` for the changed factor; `get_stock_report` only when a comprehensive explanation is needed (paid — say so).

### Step 3 — Verify

- Branch (a) and (c): `get_score_analysis` `data[0].symbol` against the requested RIC; `get_peer_snapshot.target_company` against `get_company_info.name` (conventions §2).
- Failed or empty calls: §0.1 retry classification, then §4. No gate is rendered.

### Step 4 — Compute

No deterministic helper; scores and trajectories are quoted from the tools, never re-derived. "What Would Change It" states directions and conditions in Parallax's own terms (grandfathered §11 form).

### Step 5 — Compose

Fill **Output Format** below in order; audience mode per conventions §13 (client-safe: §13.3 gloss on factor rows, no cutoff arithmetic); Branding Header per integration-pattern.md §5; `parallax-conventions.md §9.2` disclosure; standard disclaimer `parallax-conventions.md §9.1`.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/scoreexplainer.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill score-explainer < "$DRAFT"; rm -f "$DRAFT"
```

The entire final English message is that command's stdout, or the sole input to Step 7. The stderr `[render-gate] WARN:` line is diagnostics: never include or translate it. If `run-shell` is absent, apply conventions §14.3 (render-gate row).

### Step 7 — Translate (conditional)

Only when `lang=` is present and not `en`. Translate per `parallax-conventions.md` §15 (routing block §15.2, failure footers §15.3, disclaimer boundary check §15.4 — this skill appends no audit row, so a boundary-check event is not logged anywhere; do not invent a logging surface). Body is the gated Step 6 stdout including the §9.2 disclosure and disclaimer; pass `register: retail` only when supplied.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is `## The Question`, or the Branding Header when active. Apply audience render mode per `parallax-conventions.md` §13; default internal_analyst.

- **The Question** (restate clearly)
- **The Answer** (lead with the plain-language explanation — 2-3 sentences max)
- **Score Breakdown** (table if applicable: factor scores with interpretation; under `audience=client_safe`, factor rows carry the §13.3 gloss)
- **What's Driving It** (specific data points, peer comparison, methodology context)
- **What Would Change It** (concrete conditions that would improve/worsen the score; under `audience=client_safe`, keep this grandfathered §11 wording but express conditions without published-cutoff arithmetic)
- **Methodology Reference** (brief citation of the scoring methodology for credibility)
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** score explainer`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line. Under `audience=client_safe`, append the §13.4 mode line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Symbol given but unresolvable: answer the methodology part of the question (branch b) and state that the symbol-specific part could not be resolved.
- `explain_methodology` returns nothing for a topic: fall back to `list_docs` → `get_docs`; if still nothing, say the methodology page was not found rather than paraphrasing from memory.
- `get_news_synthesis` pending in branch (c): render the trajectory explanation and mark the catalyst check pending (conventions §5).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Every Output Format section rendered or marked unavailable with its reason; first line is the Branding Header or `## The Question`.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present; under `audience=client_safe` the §13.4 mode line is in About This Report.
- Expected spend stated (Gotchas); any paid call was named as paid before it was made.
- Translation (if requested) completed per §15, or the §15.3 footer explains why not.
