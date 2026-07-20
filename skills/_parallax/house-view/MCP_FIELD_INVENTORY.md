# MCP Field Inventory — Parallax house-view dependencies

**Generated:** 2026-05-24
**Source:** Phase A0 live MCP smoke calls
**Reviewed by:** N/A (initial generation)
**Refresh cadence:** Monthly (CI smoke test in `tests/integration/test_mcp_field_inventory.py`)

This artifact documents the **observed** shape of `macro_analyst` and
`get_telemetry` responses, what component formulas can compute today vs. what
requires server-side field additions, and what coverage gaps the maker must
handle gracefully.

> Component formulas (`pillar_formulas.py` — module name preserved as field
> identifier) reference this file. If MCP surface changes, regenerate this
> file via `python -m phase_a0_validate` and update formula confidence caps +
> missing_inputs lists accordingly.

---

## 1. Market coverage

`list_macro_countries()` returns **15 entries**: 14 country reports + 1 "Global" aggregate.

| Group | Markets |
|---|---|
| Developed | Canada, France, Germany, Japan, Singapore, United Kingdom, United States |
| Emerging Asia | China, India, Indonesia, Malaysia, South Korea, Taiwan, Thailand |
| Cross-market | Global (aggregate, not a country) |

**Coverage gaps vs. v0 `aggregator_weights.yaml`:**
- ❌ **Brazil, Mexico, Hong Kong** — listed in weights but NOT in MCP coverage. Drop from weights file OR redistribute their weight.
- ❌ **Malaysia** — in MCP coverage but NOT in weights file. Add with ~0.005 weight.
- ⚠️ **Global** — special aggregate market; cross_country.aggregate should NOT include it in per-country fan-out (it's already aggregated).

**Action:** `aggregator_weights.yaml` needs an alignment pass before B1 implementation starts. Single-file edit.

---

## 2. `macro_analyst` response schema (observed)

```json
{
  "report_date": "YYYY-MM-DD",
  "market": "United States",
  "file_url": "https://...supabase.co/.../signed-url",  // full report download
  "component_name": "macro_indicators",
  "component": "macro_indicators",                       // duplicate of component_name
  "content": "<markdown prose, ~3-5 paragraphs>",       // PRIMARY DATA
  "truncated": false,                                   // true if cut for token budget
  "success": true,
  "next_steps": {<discovery suggestions>}
}
```

**Critical:** `content` is **markdown prose**, not structured fields. All component
inputs are embedded in prose and require LLM extraction. The architect's
concern about discrete `valuation_z`/`vix_percentile_12m` fields being absent
is correct for `telemetry.signals` — those fields are NOT present there.
**But equivalents ARE embedded in `macro_analyst.content` prose for some
markets** (see `valuation_state` / `market_entropy` rows below).

### 2.1 Available components (9 total)

| Component | Tested | Framework-component relevance |
|---|---|---|
| `macro_indicators` | ✓ US, China | `econometrics_phase` (growth/inflation), `valuation_state` (when explicit), `market_entropy` (when explicit) |
| `tactical` | ✓ Japan | `econometrics_phase` (regime framing), sector tilts, region tilts |
| `fixed_income` | ⚪ deferred | rates leg of `econometrics_phase` — not in the default fan-out (no v0 consumer) |
| `currency` | ⚪ untested | FX context for `econometrics_phase` |
| `sectors` | ✓ US | sector tilts (BUT: may report "data unavailable" — handle gracefully) |
| `sector_positioning` | ⚪ untested | sector tilts (overlapping with sectors) |
| `liquidity` | ⚪ untested | `market_entropy` candidate |
| `news` | ⚪ untested | `psychological_wavelength`, themes |
| `factors` | ⚪ untested | country-level factor tilts (per the tool doc, distinct from telemetry's factor_view) |

**Untested components should be sampled before B1 starts** — incomplete inventory.

---

## 3. `get_telemetry` response schema (observed)

Request: `get_telemetry(fields=["regime_tag", "signals", "divergences", "commentary.headline"])`

```json
{
  "success": true,
  "commentary": {
    "headline": "Damaged pockets bounced harder than established winners"
  },
  "divergences": [
    {"mtd": -0.166, "name": "Indonesian Commodity Miners",
     "type": "rebound", "daily": 0.092, "market": "ID",
     "basket_id": "ID_20260223_052"},
    ...
  ],
  "regime_tag": "Selective rotation",          // single string
  "report_date": "2026-05-22",
  "signals": [
    {"text": "Biggest daily move: ID Indonesian Commodity Miners +9.2%",
     "type": "biggest_move"},
    {"text": "Outlier: ID Indonesian Commodity Miners daily z=4.9",
     "type": "zscore_outlier"},
    {"text": "South Korea avg basket +3.5%", "type": "market_move"},
    {"text": "Trend divergence: ID ... +9.2% today vs -16.6% MTD",
     "type": "trend_divergence"}
  ]
}
```

### 3.1 Telemetry `signals` types observed

`biggest_move`, `zscore_outlier`, `market_move`, `trend_divergence`. **List, not
keyed object.** Prose-embedded numbers (z-scores, daily/MTD %, market codes).

### 3.2 Fields v2 plan assumed but NOT FOUND

| Plan assumed | Reality |
|---|---|
| `telemetry.signals.valuation_z` | ❌ Not a discrete field. Valuation appears only in `macro_analyst.content` prose. |
| `telemetry.signals.vix_percentile_12m` | ❌ Not present. |
| `telemetry.signals.breadth_z` | ❌ Not present (telemetry has `divergences` count, can be proxy). |
| `telemetry.signals.ig_spread_z` | ❌ Not present. |
| `telemetry.signals.risk_appetite` | ❌ Not as discrete field. `regime_tag` is closest proxy. |
| `telemetry.signals[*].pmi_global_z` | ❌ Not present. |

**Implication:** Component formulas for `valuation_state` and `market_entropy`
cannot use the structured-telemetry inputs described in v2 plan §4.2 — those
don't exist. They must extract from `macro_analyst.content` prose or fall
back to NULL with confidence 0.0.

---

## 4. Per-component availability matrix

| Component | Primary input | Observed availability | Strategy for v0 |
|---|---|---|---|
| **`econometrics_phase` (macro backdrop)** | `regime_tag` + per-country `macro_indicators` growth tokens | ✅ HIGH — regime_tag always present; per-country growth signals reliably extractable from prose | Compute as planned; cap confidence at 0.8 (heuristic_phase0) |
| **`valuation_state` (valuation)** | `macro_analyst.content` "Valuation metrics at X" prose | ⚠️ PARTIAL — US prose carries explicit "-1.00"; Japan tactical and China macro_indicators do NOT. Pattern is inconsistent across markets. | LLM-extract from prose when present; mark `missing_inputs=["valuation_in_prose"]` for markets without; component value = aggregated across markets that DO carry it, gated by 60% coverage rule (BUG-009) |
| **`market_entropy` (market state)** | `macro_analyst.content` "entropy at X" prose + `telemetry.divergences` count | ⚠️ PARTIAL — US prose carries explicit "0.00"; others do not. `divergences` is a usable proxy (more = more entropy). | Composite: prose-extracted entropy where present + normalized divergence count where prose silent. Confidence ≤ 0.5. |
| **`psychological_wavelength` (sentiment)** | `macro_analyst.content` news/sentiment + `telemetry.commentary` tone | 🟡 LLM-JUDGED — no discrete numeric input; structured-output LLM call required | LLM-judged per v2 plan §4.2; confidence ≤ 0.6 |

---

## 5. Maker / Judge implications (must read before B1)

### 5.1 `pillar_formulas.py` changes vs. v2 plan §4.2

The four `compute_*` functions in v2 plan assumed structured `telemetry.signals[*]`
inputs. **Revise as follows:**

- `compute_omega(aggregated, telemetry, inventory)` — unchanged path. Inputs available.
- `compute_phi(aggregated, telemetry, inventory)` — **prose-extracted, NOT signals-based**. Scan per-country `macro_indicators.content` for explicit "Valuation metrics at X" or similar; aggregate where present; return NULL with `missing_inputs=["valuation_prose_silent_in_all_markets"]` if no market carries one.
- `compute_xi(aggregated, telemetry, inventory)` — **composite**: prose-extracted "entropy at X" where present + normalized `len(telemetry.divergences)` as fallback proxy. Document the proxy explicitly in `composition_formula`.
- `compute_psi(aggregated, telemetry, inventory)` — unchanged path (LLM-judged).

### 5.2 `cross_country.py` market list alignment

Update `aggregator_weights.yaml` to match observed coverage (14 markets, drop
Brazil/Mexico/Hong Kong, add Malaysia, exclude Global from per-country fan-out).

### 5.3 Component fan-out scope

The maker fans out 4 components per market: {macro_indicators, tactical,
sectors, news}. The MCP exposes 9 components. These 4 are the ones consumed by
pillar/sector/region tilt extraction — `fixed_income` is deferred (no v0
formula reads it; the rates leg of `econometrics_phase` is unbuilt), and
`currency`, `liquidity`, `sector_positioning`, `factors` are either redundant
or out of scope for v0 (the country-level `factors` component would compete
with telemetry.factor_view; skip for v0 unless validation shows it adds signal).
Re-add `fixed_income` in lockstep with a rates leg in `pillar_formulas.py`.

**Fan-out budget:** 14 markets × 4 components = 56 macro_analyst calls per maker
invocation (NOT 150 as v2 plan and swarm prompt estimated — that was based on
30 markets). Plus 1 telemetry. With 8-concurrent batching: ~7 batch rounds.
At ~3s per call (per tool description), latency budget is ~30s for fan-out
plus ~15-30s for telemetry. Total interactive latency: ~45-60s. Acceptable
for a synthesis skill that the user expects to wait for.

### 5.4 Sectors graceful failure

US `sectors` component returned "Sector ranking data remains unavailable for
this reporting period" with explanatory prose. Maker must treat this as
`PARTIAL` rather than `UNREACHABLE` — the component returned, just with the
data layer missing. cross_country aggregator should classify these as
`silent`, not `UNREACHABLE`.

---

## 6. Still-untested surface (do before B1 implementation)

Sample-call the following components on US to complete the inventory:

```python
# Untested as of 2026-05-24:
macro_analyst("United States", "fixed_income")
macro_analyst("United States", "currency")
macro_analyst("United States", "sector_positioning")
macro_analyst("United States", "liquidity")
macro_analyst("United States", "news")
macro_analyst("United States", "factors")

# Untested telemetry fields:
get_telemetry(fields=["factor_view.factors", "factor_view.commentary"])
get_telemetry(fields=["commentary.paragraphs", "commentary.mechanism"])
get_telemetry(fields=["markets"])
```

Add results to §2.1 and §3 above. Update `psychological_wavelength` in §4 if
news component or telemetry commentary expose sentiment signals more directly.

---

## 7. CI smoke test design

`tests/integration/test_mcp_field_inventory.py`:

```python
def test_mcp_surface_unchanged():
    """Catch MCP surface drift. Monthly CI run.

    Asserts presence of required keys at each level. Does NOT assert
    additive changes — Parallax can add fields freely.

    Fails when:
      - macro_analyst response missing required top-level keys
        ({success, content, component, market, report_date}).
      - macro_analyst content field is empty or not a string.
      - get_telemetry response missing required top-level keys
        ({success, regime_tag, signals, divergences}).
      - list_macro_countries returns fewer than 10 markets
        (smoke test for regression).

    Does NOT fail on:
      - New components in macro_analyst (additive).
      - New signal types in telemetry.signals (additive).
      - New keys in any response (additive).
    """
```

This shapes the test toward true-regression detection rather than additive-noise.
