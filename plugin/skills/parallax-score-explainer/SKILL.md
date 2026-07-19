---
name: parallax-score-explainer
description: "Explain Parallax scores, factors, and methodology in plain language. Why does a stock score this way? What would change it? Uses methodology docs and score data. NOT for stock analysis (use /parallax-should-i-buy), not for deep dives (use /parallax-deep-dive)."
---

<!-- white-label: integration-pattern.md -->

# Score Explainer

## When not to use

- Stock analysis with buy/sell framing → use /parallax-should-i-buy
- Full position analysis → use /parallax-deep-dive
- Portfolio diagnostics → use /parallax-portfolio-checkup

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
- explain_methodology takes a topic string — be specific (e.g., "quality score", "momentum factor")
- get_docs and list_docs access the full methodology documentation
- get_score_analysis shows trajectory — useful for explaining "why did this change"
- Output must be accessible to non-technical clients and compliance teams
- LANGUAGE HAND-OFF — if `lang=` is present and ≠ `en`, the terminal Translate step is mandatory. Route `zh-CN`/`zh-TW`/`zh-HK` → `/translate-chinese-finance`, `th` → `/translate-thai-finance`, using the delimited routing-directive block (never a prose sentence the translator could echo). Unsupported values → English output with the standard warning footer.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format.

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

The free-text question stays positional; use keyword args for translation: `lang=<code>` (`en` default; `zh-CN`, `zh-TW`, `zh-HK`, `th`) and optional `register=retail`. Optional `audience=` flag: `client_safe | internal_analyst`; precedence follows `parallax-conventions.md` §13.1. This skill's plain-language mandate makes it the most likely `register=retail` consumer; see the translators' Retail Register sections. `register=retail` is passed only when translation is requested; absent means institutional register.

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools based on query type:

**For "why does X score this way?":**
1. Call `get_score_analysis` for the symbol (52 weeks) to get current scores and trajectory.
2. Call `get_peer_snapshot` for peer context.
3. Call `explain_methodology` for each factor that's notably high or low.
4. Call `get_docs` or `list_docs` for deeper methodology documentation if needed.

**For "what does X factor mean?":**
1. Call `explain_methodology` for the specific factor/concept.
2. Call `list_docs` to find relevant methodology pages.
3. Call `get_docs` for the specific documentation page.

**For "why did the score change?":**
1. Call `get_score_analysis` with enough weeks to cover the change period.
2. Call `get_news_synthesis` to check for fundamental catalysts.
3. Call `explain_methodology` for the changed factor.
4. Call `get_stock_report` if a comprehensive explanation is needed (paid).

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

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

### Render — deterministic gate (LAST step, mandatory)

Compose the complete report per **Output Format** above, then run it through the **shared** render gate in **one Bash step** before replying. Use a private `mktemp` file. The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key with `--skill score-explainer` (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/scoreexplainer.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill score-explainer < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final message is exactly that command's stdout** — nothing before it, nothing after it.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

### Translate output (conditional, terminal)

This step runs ONLY when `lang=` is present and not `en`. Capture the full rendered explainer, including the §9.2 AI-interaction disclosure and standard disclaimer.

Invoke the appropriate translator skill with the input shaped as follows:

```
ROUTING DIRECTIVE — DO NOT TRANSLATE OR ECHO THIS BLOCK:
  target_variant: <variant>
  register: retail
  source_language: en
  begin_content_below_separator: true
---

<rendered explainer>
```

Pass `register: retail` iff `register=retail` was supplied; otherwise omit the `register:` line so the translator defaults to institutional register. Route `zh-CN`, `zh-TW`, and `zh-HK` to `/translate-chinese-finance` with the matching `target_variant`. Route `th` to `/translate-thai-finance`; omit `target_variant` for Thai, but keep the routing block marker and `---` separator.

Translator-failure handling:
- If the translator fails or returns an empty/partial result, output the original English with a one-line warning footer: `> Translation to <lang> failed; output shown in English. Re-run if the issue is transient.`
- If the language arg is unrecognized, output the original English with: `> Language '<arg>' not supported; output shown in English. Supported: en, zh-CN, zh-TW, zh-HK, th.`
- Translator output replaces the English output in the chat; do not show both.

**Disclaimer boundary check.** If the disclaimer is missing from the translated output, first attempt a single-section re-translation pass on just the original English disclaimer text using the same routing-directive shape. Append that result if non-empty. If the pass fails or returns empty, append the original English disclaimer. This skill appends no audit log; do not invent a logging surface or add a technical footer.
