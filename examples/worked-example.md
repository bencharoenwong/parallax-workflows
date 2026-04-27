# End-to-End Audit-Trail Worked Example
**Generated:** 2026-04-27 (pinned for reproducibility — same inputs → byte-identical outputs).
**Thesis:** EM-tilt balanced equity, focus on Latin America + ASEAN, ESG-aware, $1M target

> Demonstrates the consumer-side architecture end-to-end: the saved house view stays PURE (bank's view + uploader confirmation only); current-data augmentation happens at THIS portfolio's construction time, scoped to THIS decision, with explicit per-tilt source tags. A compliance officer reviewing this artifact can defensively reconstruct what came from the bank's view vs from current data, with timestamps.

## Active house view (read-only inputs)
- `view_id`: `086db6a9-9d0e-4c24-82bd-823cbda79eb3`
- `view_version_id`: `e2621adc-d90f-4054-a5be-f72546dfe340`
- `view_hash`: `6d23eecd394a3f9390cc47f789a3dc87...`
- `view_name`: UBS CIO March 2026 Monthly Letter — Navigating uncertainty
- `effective_date → valid_through`: 2026-03-19 → 2026-06-17
- `uploader_role`: CIO

## JIT augmentation gate (Step 1b)
- Thesis-relevant regions: `['brazil', 'india', 'indonesia', 'malaysia', 'mexico', 'south_korea', 'thailand', 'us']`
- Thesis-relevant sectors: `['consumer_staples', 'energy', 'financials', 'health_care', 'information_technology', 'materials']`
- Gaps detected (silent in saved view): **8**
- MCP calls planned (after live coverage filter): **3**
- Calls fired (fixtures available in this artifact): **1**
- Skipped (no MCP coverage today): **3** → `['brazil', 'indonesia', 'mexico']`
- Suggestions folded: **2**

## Selected holdings — per-tilt source tags

| Ticker | Name | Weight | Region | Region tilt | Region source | Sector | Sector tilt | Sector source |
|--------|------|-------:|--------|-----------:|---------------|--------|-----------:|---------------|
| `VALE.N` | Vale SA (BR ADR) | 15% | brazil | +0 | `[neutral]` | materials | +0 | `[neutral]` |
| `WALMEX.MX` | Walmart de Mexico | 10% | mexico | +0 | `[neutral]` | consumer_staples | -1 | `[parallax_jit, macro_analyst[United States]@2026-04-24]` |
| `BBCA.JK` | Bank Central Asia | 10% | indonesia | +0 | `[neutral]` | financials | +1 | `[house_view]` |
| `PTT.BK` | PTT PCL | 5% | thailand | +0 | `[neutral]` | energy | +1 | `[parallax_jit, macro_analyst[United States]@2026-04-24]` |
| `MAYBANK.KL` | Malayan Banking Bhd | 10% | malaysia | +0 | `[neutral]` | financials | +1 | `[house_view]` |
| `RELIANCE.NS` | Reliance Industries | 15% | india | +1 | `[house_view]` | energy | +1 | `[parallax_jit, macro_analyst[United States]@2026-04-24]` |
| `005930.KS` | Samsung Electronics | 15% | south_korea | +1 | `[house_view]` | information_technology | -1 | `[house_view]` |
| `UNH.N` | UnitedHealth Group | 20% | us | +1 | `[house_view]` | health_care | +1 | `[house_view]` |

## Per-row evidence (the `--why` story for every multiplier)

**`VALE.N` (Vale SA (BR ADR))**
- Region (`brazil` → +0, [neutral]): silent in saved view + no JIT augmentation available
- Sector (`materials` → +0, [neutral]): silent in saved view + no JIT augmentation available

**`WALMEX.MX` (Walmart de Mexico)**
- Region (`mexico` → +0, [neutral]): silent in saved view + no JIT augmentation available
- Sector (`consumer_staples` → -1, [parallax_jit, macro_analyst[United States]@2026-04-24]): The 2026 macroeconomic outlook rests on resilient 2.0%–2.5% real growth despite ...

**`BBCA.JK` (Bank Central Asia)**
- Region (`indonesia` → +0, [neutral]): silent in saved view + no JIT augmentation available
- Sector (`financials` → +1, [house_view]): saved view: tilts.sectors.financials=+1

**`PTT.BK` (PTT PCL)**
- Region (`thailand` → +0, [neutral]): silent in saved view + no JIT augmentation available
- Sector (`energy` → +1, [parallax_jit, macro_analyst[United States]@2026-04-24]): The 2026 macroeconomic outlook rests on resilient 2.0%–2.5% real growth despite ...

**`MAYBANK.KL` (Malayan Banking Bhd)**
- Region (`malaysia` → +0, [neutral]): silent in saved view + no JIT augmentation available
- Sector (`financials` → +1, [house_view]): saved view: tilts.sectors.financials=+1

**`RELIANCE.NS` (Reliance Industries)**
- Region (`india` → +1, [house_view]): saved view: tilts.regions.india=+1
- Sector (`energy` → +1, [parallax_jit, macro_analyst[United States]@2026-04-24]): The 2026 macroeconomic outlook rests on resilient 2.0%–2.5% real growth despite ...

**`005930.KS` (Samsung Electronics)**
- Region (`south_korea` → +1, [house_view]): saved view: tilts.regions.south_korea=+1
- Sector (`information_technology` → -1, [house_view]): saved view: tilts.sectors.information_technology=-1

**`UNH.N` (UnitedHealth Group)**
- Region (`us` → +1, [house_view]): saved view: tilts.regions.us=+1
- Sector (`health_care` → +1, [house_view]): saved view: tilts.sectors.health_care=+1

## Tilt-source summary (compliance-officer headline)

Across 8 holdings × 2 tilt dimensions (region + sector) = **16 multipliers**:
- `[house_view]` (sourced from the saved bank view): **7** (44%)
- `[parallax_jit]` (sourced from JIT lookup at portfolio-construction time, with tool + market + as-of date): **3** (19%)
- `[neutral]` (silent in saved view + not augmented at this run): **6** (38%)

## Audit log entry (one JSONL row, hash-chained, written to portfolio's audit chain)

```jsonl
{
  "schema_version": 1,
  "ts": "2026-04-27T09:30:00Z",
  "skill": "parallax-portfolio-builder",
  "action": "consume",
  "applied": true,
  "view_id": "086db6a9-9d0e-4c24-82bd-823cbda79eb3",
  "view_version_id": "e2621adc-d90f-4054-a5be-f72546dfe340",
  "view_hash": "6d23eecd394a3f9390cc47f789a3dc87bfb5eed0fb1a231dd1cf3a69c65fe69e",
  "run_id": "01HQA7C8M3K9N5P2T6V4W8XBYR",
  "portfolio_id": "wkd-example-em-tilt-2026-04-27",
  "thesis": "EM-tilt balanced equity, focus on Latin America + ASEAN, ESG-aware, $1M target",
  "augment_silent_flag": true,
  "augmented_dimensions": [
    {
      "field_path": "tilts.sectors.consumer_staples",
      "suggested_value": -1,
      "source_tool": "macro_analyst",
      "source_call_args": {
        "market": "United States"
      },
      "data_as_of": "2026-04-24",
      "source_snippet_first_80": "The 2026 macroeconomic outlook rests on resilient 2.0%\u20132.5% real growth despite "
    },
    {
      "field_path": "tilts.sectors.energy",
      "suggested_value": 1,
      "source_tool": "macro_analyst",
      "source_call_args": {
        "market": "United States"
      },
      "data_as_of": "2026-04-24",
      "source_snippet_first_80": "The 2026 macroeconomic outlook rests on resilient 2.0%\u20132.5% real growth despite "
    }
  ],
  "silent_dimensions_skipped": [
    {
      "path": "tilts.regions.brazil",
      "reason": "no Parallax MCP coverage today"
    },
    {
      "path": "tilts.regions.indonesia",
      "reason": "no Parallax MCP coverage today"
    },
    {
      "path": "tilts.regions.mexico",
      "reason": "no Parallax MCP coverage today"
    }
  ],
  "holdings_count": 8,
  "holdings_weight_sum": 1.0,
  "tilt_source_summary": {
    "house_view_count": 7,
    "parallax_jit_count": 3,
    "neutral_count": 6
  }
}
```

**Entry SHA-256 (over RFC-8785-canonical JSON):** `a85100f8f36d0fe7c35b2cf928770b212a1087f978238e6c191db1313ac18d3f`
This hash chains off the prior `audit.jsonl` entry's hash. A compliance officer who has the audit.jsonl file can replay the chain and confirm tamper-evidence.

## What the principal sees when they ask 'where did Mexico come from?'

For `WALMEX.MX` (Walmart de Mexico, mexico +0):

- **Source:** `[neutral]`
- **Evidence:** silent in saved view + no JIT augmentation available
- **Means:** the saved house view (UBS CIO Mar 2026) was silent on Mexico. The portfolio-construction step asked Parallax data for a current Mexico read; the response was unavailable today (no MCP coverage). Mexico stayed neutral. The bank's view is untouched. The principal can see EXACTLY what the bank said vs what Parallax filled vs what defaulted to neutral.

## Determinism check (the auditability pitch made concrete)

Re-running this script with the same active view, same thesis, same captured fixtures produces the SAME audit-entry SHA-256: `a85100f8f36d0fe7c35b2cf928770b21` — by construction, because:

- View state is read-only (same `view_hash`).
- Coverage list is pinned (same `available_markets`).
- MCP responses are captured fixtures (same bytes in → same bytes out).
- Audit timestamp + run_id are pinned at the top of the script (in production these are `now()` + a fresh ULID; the audit chain itself is what's deterministic, not these timestamps).

In production: same active view + same thesis + same MCP responses on the same date → byte-identical holdings table + byte-identical audit-entry hash. This is the **'same input → same output' property** the auditability pitch is built on.
