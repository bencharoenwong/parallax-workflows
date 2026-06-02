# Downstream Skill Integration Contract

How visual and voice consumers load and apply white-label branding. SKILL.md keeps the high-level routing; this file holds the loader call patterns and the voice prompt-prepend template.

## Two consumer classes

**Visual consumers** — Skills that produce a PDF or formatted report. They read `branding.colors`, `branding.logos`, `branding.fonts`. They ignore `voice`. Currently integrated:

- **Tier 1**: `/parallax-cio-letter-prep`, `/parallax-client-review`, `/parallax-due-diligence`, `/parallax-deep-dive`
- **Tier 2**: `/parallax-should-i-buy`, `/parallax-thematic-screen`, `/parallax-portfolio-checkup`, `/parallax-portfolio-builder`, `/parallax-rebalance`, `/parallax-morning-brief`, `/parallax-explain-portfolio`, `/parallax-scenario-analysis`, `/parallax-country-deep-dive`, `/parallax-pair-finder`, `/parallax-peer-comparison`, `/parallax-macro-outlook`

The canonical consumer-side contract — header rendering, provenance line, color substitution, logo placement, fallback behavior — lives in `_parallax/white-label/integration-pattern.md` (§1–§9). New visual consumers must JIT-load it via the `<!-- white-label: integration-pattern.md -->` sentinel; the drift gate at `tests/test_integration_pattern_referenced.py` enforces the sentinel ↔ load-directive pairing.

**Voice consumers** — letter-writing, newsletter, meeting-prep, email-drafting, and any skill that produces written content under the client's name. They read `voice.*` and apply it as a style guide before generating prose. They optionally also read `branding.*` if the output is rendered (e.g., a branded PDF letter).

Both classes silently fall back to default Parallax styling/voice if the config is absent or corrupted. The skill never breaks downstream consumers.

## Visual consumer loading pattern

Visual-rendering skills call `loader.load_visual_branding()` — it returns only the six keys a visual consumer is permitted to read (`client_name`, `colors`, `logos`, `fonts`, `source`, `error`) and structurally excludes `voice`/typography/`multi_source` so a misuse (`branding["voice"]`) raises `KeyError` instead of silently inheriting voice data. Pair it with `loader.is_white_label_active(branding)` (rendering predicate — do not re-implement inline; see `integration-pattern.md` §2/§4/§8) and `loader.safe_source_reference(branding)` (display-safe Provenance source ref — §7). The full 13-key shape from `load_client_branding()` is reserved for voice consumers (CIO letter, newsletter, future writing skills) that need both visual and voice. Both wrappers bridge v1↔v2 file shapes so downstream code keeps working through the schema migration:

```python
from skills._parallax.white_label.loader import load_visual_branding

result = load_visual_branding()
if result.get("error") is None:
    # 6-key visual subset — works against both v1 AND v2 config.yaml on disk
    primary_color = result["colors"]["primary"]
    accent_color  = result["colors"]["accent"]   # v2: derived from colors.tertiary
    bg_color      = result["colors"]["background"]  # v2: derived from colors.neutral
    header_font   = result["fonts"]["header"]    # v2: derived from typography.h1.fontFamily
```

For voice consumers that need the full token tree alongside voice, call `load_client_branding()` and read `result["typography"]`, `result["rounded"]`, `result["spacing"]`, `result["components"]` (empty dicts on v1 configs and on every error path — safe to access unconditionally), plus `result["voice"]`.

**Do NOT** read `cfg["branding"]["colors"]["accent"]` directly — that key exists in v1 files but is named `tertiary` in v2. The loader is the single source of truth for the legacy return shape.

## Voice consumer loading pattern

```python
import yaml, os
config_path = os.path.expanduser("~/.parallax/client-branding/config.yaml")
voice = None
if os.path.exists(config_path):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    if cfg.get("voice", {}).get("enabled"):
        voice = cfg["voice"]

# In the prose-generation prompt, prepend something like:
if voice:
    style_block = f"""
    Write in the voice of {cfg['metadata']['client_name']}. Their register is
    {voice['tone']['register']}. Primary attributes: {', '.join(voice['tone']['primary_attributes'])}.
    Avoid: {', '.join(voice['tone']['avoid_attributes'])}.

    Non-negotiable rules:
    {chr(10).join('- ' + r for r in voice['core_rules'])}

    Phrases to delete on sight (anti-filler):
    {chr(10).join('- ' + p for p in voice['anti_filler'])}

    How they describe themselves: {voice['company_context']}
    """
    prompt = style_block + "\n\n" + content_prompt
```

## Drafted-vs-Sent feedback loop

Voice consumer skills SHOULD save the AI draft + the human-edited final version after each session as an entry in `voice.drafted_vs_sent`. This is the highest-quality voice calibration data and improves future outputs. Implementation deferred until at least one voice consumer is wired up.
