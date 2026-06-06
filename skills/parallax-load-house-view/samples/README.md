# Sample CIO House Views

Five realistic CIO house-view documents. Each is intentionally written in the prose style and length a real CIO would produce — not a structured form, not a clean YAML. They are the test inputs for the extraction pipeline in `parallax-load-house-view`.

## The 5 samples

| File | Pattern under test |
|---|---|
| `2026-reflationary.md` | Sector + factor + region tilts mixed with hedged language ("more nuanced than the headline suggests"). Tests handling of split-sector views (positive on AI infra, selective in software). |
| `recession-defensive.md` | Strong macro-regime view with explicit factor implications and probability-weighted positioning. Tests macro-regime → factor-tilt mapping (loader.md §3) and handling of "modest" vs "strong" qualifiers. |
| `AI-concentrated.md` | High-conviction thematic with deliberate concentration. Tests theme tilt extraction, multi-region tilts (US + Taiwan + Korea + Japan), and acknowledgment of self-described tracking error. |
| `ESG-screened.md` | Mandate-heavy with extensive hard excludes specified by category and revenue-exposure threshold. Tests the excludes pipeline and how the loader handles "permanent vs review-period" mandate fields. |
| `China-skeptic.md` | Region-focused with revenue-exposure-based exclusions ("companies with >25% China revenue"). Tests whether extraction can capture indirect exposure rules vs simple sector/region tilts. |

## Using these for testing

To dogfood:

```
/parallax-load-house-view skills/load-house-view/samples/2026-reflationary.md
```

Walk through the confirmation gate. Note any extraction misses or low-confidence fields. After confirm + save, run a portfolio skill against a realistic test portfolio:

```
/parallax-portfolio-builder "diversified global equity portfolio, mid-cap focus"
```

Verify the output preamble references the loaded view, that tilts are visibly applied (e.g., financials/industrials/energy overweight), and that any conflict between the user's "diversified" intent and the view's directional tilts is banner-flagged.

Repeat for each sample. Capture results in your local notes.

## Notes on realism

These samples were written to expose the failure modes flagged in the adversarial review:

- **Hedged sector calls** ("constructive on tech but selective in semis") — extraction should produce sector-level tilt + theme-level boost, not collapse to a single integer.
- **Probability-weighted positioning** ("we put recession at ~45%") — extraction should not treat hedged probability as a hard regime label.
- **Mandate vs view fields** — ESG sample has both permanent excludes (mandate) and review-period tilts (view). Extraction should populate both correctly.
- **Indirect exposure rules** ("companies with >25% China revenue") — these don't map cleanly to RIC suffix or sector. Loader should mark these as a known-limit and surface to user at confirmation.

If extraction fails to handle these patterns at >0.7 confidence, the schema or extraction prompt needs revision before any release that depends on the corpus.
