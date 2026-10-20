# Downstream Skill Integration Contract

How implemented visual consumers apply white-label branding, and what a future voice integration would require. Saving a voice profile does not activate automatic voice rewriting.

## Implemented consumers and stored voice

**Visual consumers** — Skills that produce a PDF or formatted report. They read `branding.colors`, `branding.logos`, `branding.fonts`. They ignore `voice`. Currently integrated:

- **Tier 1**: `/parallax-cio-letter-prep`, `/parallax-client-review`, `/parallax-due-diligence`, `/parallax-deep-dive`
- **Tier 2**: `/parallax-should-i-buy`, `/parallax-thematic-screen`, `/parallax-portfolio-checkup`, `/parallax-portfolio-builder`, `/parallax-rebalance`, `/parallax-morning-brief`, `/parallax-explain-portfolio`, `/parallax-scenario-analysis`, `/parallax-country-deep-dive`, `/parallax-pair-finder`, `/parallax-peer-comparison`, `/parallax-macro-outlook`

The canonical consumer-side contract — header rendering, footer line, color substitution, logo placement, fallback behavior — lives in `_parallax/white-label/integration-pattern.md` (§1–§9). New visual consumers must JIT-load it via the `<!-- white-label: integration-pattern.md -->` sentinel; the drift gate at `tests/test_integration_pattern_referenced.py` enforces the sentinel ↔ load-directive pairing.

**Voice profile storage** — onboarding can extract and persist `voice.*`. No automatic letter, newsletter or meeting-prep voice consumer is promised here. CIO letter prep is visual-only and leaves voice to the CIO; it never loads `voice.*`. A future writing consumer must explicitly implement and validate profile application before claiming support.

Absent or invalid config degrades to default visuals under the shared loader's error contract. Missing voice is not a substitute for an implemented voice consumer.

**Independent stock-report consumer** — `/parallax-white-label-stock-report` ships its own standalone reader, with no shared schema-loader dependency. It accepts the v2 visual fields documented in that skill and falls back per malformed branch. Its optional `voice.disclaimers[]` input is verbatim disclosure text for explicit full-white-label rendering, not tone or prose synthesis. The shared visual-only contract continues to keep its standard disclaimers.

## Visual consumer loading pattern

Visual-rendering skills call `loader.load_visual_branding()` — it returns only the seven keys a visual consumer is permitted to read (`client_name`, `colors`, `logos`, `fonts`, `source`, `error`, `render`) and structurally excludes `voice`/typography/`multi_source` so a misuse (`branding["voice"]`) raises `KeyError` instead of silently inheriting voice data. Pair it with `loader.is_white_label_active(branding)` (rendering predicate — do not re-implement inline; see `integration-pattern.md` §2/§4/§8) and `loader.safe_source_reference(branding)` (display-safe About This Report source ref — §7). Skills run the visual loader through the one-line `loader.py --json` command in `integration-pattern.md` §2; the import below is for Python callers. The full 14-key shape from `load_client_branding()` is available for future explicitly implemented consumers that need both visual and voice; it has no command form. Both wrappers bridge v1↔v2 file shapes so downstream code keeps working through the schema migration:

```python
from skills._parallax.white_label.loader import load_visual_branding

result = load_visual_branding()
if result.get("error") is None:
    # 7-key visual subset — works against both v1 AND v2 config.yaml on disk
    primary_color = result["colors"]["primary"]
    accent_color  = result["colors"]["accent"]   # v2: derived from colors.tertiary
    bg_color      = result["colors"]["background"]  # v2: derived from colors.neutral
    header_font   = result["fonts"]["header"]    # v2: derived from typography.h1.fontFamily
```

For a future voice consumer that needs the full token tree alongside voice, call `load_client_branding()` and read `result["typography"]`, `result["rounded"]`, `result["spacing"]`, `result["components"]` (empty dicts on v1 configs and on every error path — safe to access unconditionally), plus `result["voice"]`.

**Do NOT** read `cfg["branding"]["colors"]["accent"]` directly — that key exists in v1 files but is named `tertiary` in v2. The loader is the single source of truth for the legacy return shape.

## Future voice integration boundary

A future writing skill must call `load_client_branding()`, inspect its error state and `voice.enabled`, then define which validated profile fields its own prose-generation contract supports. It must preserve evidence, uncertainty and its disclosure rules; brand tone cannot override those rules. A saved profile alone does not authorize drafting, sending, or retaining client communications. Do not bypass the loader with raw YAML traversal or prepend unchecked profile values to a generation prompt.

## Drafted-vs-Sent feedback loop

Draft-versus-final calibration is unimplemented. Any future consumer needs an explicit retention and confirmation contract before saving communications; onboarding does not start that feedback loop.
