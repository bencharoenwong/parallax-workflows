# White-Label Branding Integration Pattern

Shared reference for Parallax skills that render visual content (markdown reports, .docx letters) and need to swap the default Parallax-CG palette for a client's brand when configured.

JIT-loaded by consumer skills via the sentinel comment `<!-- white-label: integration-pattern.md -->` placed at the top of each consuming `SKILL.md` and a `Load .../integration-pattern.md` directive at the call site (the `### Pre-Render — Load white-label branding` step). The pairing is asserted by `tests/test_integration_pattern_referenced.py`.

This file is **specification**, not Python. The consumer SKILL.md is the operator instruction; this doc supplies the contract and patterns the operator follows.

---

## §1 — Purpose & scope

**In scope:** visual identity for rendered output — palette tokens, fonts, cover-page or header logo, client name in the deliverable header, and a one-line Branding row in the Provenance footer.

**Out of scope:**

- **Voice prose generation.** Brand tone, persona, signature phrases. Voice is a separate concern handled by future writing-pipeline skills (newsletter, letter, content marketing). Visual-rendering skills MUST NOT generate prose from `branding["voice"]`.
- **Auto-jurisdiction disclaimers.** Disclaimers stay as the standard wording per each skill's own Disclaimer section. Voice config does not override the disclaimer block.
- **Semantic color overrides.** Tokens `cg-green-700` (positive), `cg-red-700` (negative), `cg-amber-*` (warning) signal meaning, not brand identity. They are NEVER overridden by client branding.

The structural guardrail enforcing this scope is `load_visual_branding()` in `loader.py` — it returns only the six visual keys; voice and v2 token-tree fields are absent from the dict, so accidental access raises `KeyError`.

---

## §2 — Loading the branding

Every consumer skill calls `load_visual_branding()` (not `load_client_branding()`):

```python
import sys
from pathlib import Path

# loader.py lives at _parallax/white-label/loader.py
_WHITE_LABEL_DIR = Path(__file__).parent.parent / "_parallax" / "white-label"
sys.path.insert(0, str(_WHITE_LABEL_DIR))
from loader import load_visual_branding  # noqa: E402

branding = load_visual_branding()

err = branding.get("error")
white_label_active = (
    err is None
    or err.startswith("logo_missing")
)
client_name = branding.get("client_name", "")
```

`white_label_active` is the rendering flag. `client_name` is safe to read with `.get(..., "")` because legacy configs predating the field return `""` rather than `KeyError`.

**Do not load the YAML directly.** A second `yaml.safe_load` against the same config file bypasses the loader's error handling, schema validation, and logo resolution, and creates a race window between the loader's existence check and the second read.

---

## §3 — Safe key access

`load_visual_branding()` returns exactly six keys: `client_name`, `colors`, `logos`, `fonts`, `source`, `error`. Voice and v2-only token-tree fields (`typography`, `rounded`, `spacing`, `components`, `multi_source`, `confidence_scores`) are absent.

This is enforced by the loader at code level (a dict-comprehension over the `_VISUAL_BRANDING_KEYS` constant in `loader.py`). Accidental `branding["voice"]` access raises `KeyError`. **The constant in `loader.py` is the machine-enforced source of truth; the six-key list above is its human-readable declaration. If the two ever diverge during a PR, the constant wins — and `tests/test_loader.py::test_visual_branding_keys_are_subset_of_load_client_branding` will fail.** Update both together (see §9).

If a future visual key (e.g. `branding["icons"]`) is added, the allowlist must be updated deliberately — additive-safe by construction.

---

## §4 — Error handling

`branding["error"]` is one of:

| Value | Meaning | What the skill does |
|---|---|---|
| `None` | Clean load | Apply white-label substitution. |
| `"config_not_found"` | No client onboarded | Silent default-Parallax path. No warning. Provenance reads `Branding: default Parallax`. |
| `"logo_missing: <path>"` | Logo file referenced but absent on disk | Palette + fonts usable; cover-page / header logo skipped. Provenance reads `Branding: white-label (source: <ref>) (logo unavailable, omitted)`. |
| `"schema_invalid: <details>"` | Schema validation failed | Fall back to defaults. Provenance reads `Branding: default Parallax (config invalid: <details>)`. |
| `"yaml_parse_error: <details>"` | YAML corrupt | Fall back to defaults. Provenance reads `Branding: default Parallax (config unreadable)`. |
| `"schema_unavailable"` | Loader's own schema file missing | Best-effort branding apply; Provenance reads `Branding: white-label (best-effort, schema unavailable)`. |

The `white_label_active` flag in §2 collapses these to a binary: clean or `logo_missing` → render the brand; anything else → default.

---

## §5 — Substitution for markdown skills

Markdown skills (the 12 Tier 2 consumers) render in chat, not to .docx. "Branding" reduces to three render-time elements:

1. **Header line** (when `white_label_active` AND `client_name != ""`): one line at the top of the deliverable, before any analytical content:
   ```
   **<client_name>** report
   ```
   If `client_name == ""` (legacy config with no name field), **skip the header line entirely** — do not render `**** report` with empty bolding. The deliverable starts with the first analytical section in that case.

   If `branding["logos"]["primary"]` is set AND is a URL (starts with `http://` or `https://`), embed: `![<client_name>](<url>)`. The loader resolves on-disk logos to absolute local filesystem paths (e.g., `/Users/<user>/.parallax/client-branding/primary-logo.png`), which are not embeddable in any markdown delivered over a network. **If `branding["logos"]["primary"]` starts with `/` or `~`, skip image embed entirely and add a second Provenance line: `Logo on file: <basename>`** (see §7).

2. **Provenance footer** (always present when this skill is wired, regardless of `white_label_active`): see §7.

3. **No palette tokens.** Markdown rendered in chat has no color-token substrate, so palette swap is degenerate. The semantic-token rule (§1) still applies but is moot for markdown skills — they have no `cg-green-700` references to begin with. **Implication for `error == "logo_missing"`:** for markdown skills, `logo_missing` has no effect on rendering beyond the Provenance line — there is no palette or font substitution to apply or skip. The skill renders normally with the client_name header (if any) and the `logo_missing` Provenance line.

Markdown skills do NOT modify their analytical content based on `white_label_active`. Branding is a presentation overlay, not a synthesis flag.

---

## §6 — Substitution for docx skills

The single docx consumer in this PR is `cio-letter-prep` (post-retrofit). When `white_label_active`, the renderer substitutes brand-identity tokens with the client's config and leaves semantic tokens (positive / negative / warning) untouched. This table is the canonical reference; cio-letter-prep/SKILL.md applies it.

| Default token | Substitute with | Notes |
|---|---|---|
| `cg-navy-900` | `branding["colors"]["primary"]` | H1/H2 fill, table header fill |
| `cg-navy-700` | `branding["colors"]["secondary"]` (or primary if secondary missing) | H3/H4 |
| `cg-neutral-900` | `branding["colors"]["text"]` | Body text |
| `cg-neutral-100` | derive lighter shade from `branding["colors"]["background"]` | Alternating-row shading; if background is `#FFFFFF`, keep default `#EAEDF3` |
| (no token; new) | `branding["logos"]["primary"]` | Inserted as cover-page header image (left-aligned, ≤ 1.5 inch height). Per §4: skip on `logo_missing`. |
| (no token; new) | `branding["fonts"]["header"]` | Word style: Heading 1, Heading 2, Heading 3 |
| (no token; new) | `branding["fonts"]["body"]` | Word style: Body Text, table cells |
| `cg-green-700` | **(unchanged)** | Semantic positive — never branded |
| `cg-red-700` | **(unchanged)** | Semantic negative — never branded |
| `cg-amber-700` / `cg-amber-50` | **(unchanged)** | Semantic warning — never branded |
| `cg-neutral-500` | **(unchanged)** | Muted text contrast — fund's `text` color may be too dark for muting |

Cover-page client name: when `white_label_active` AND `client_name != ""`, the docx cover-page header gains the client name in the brand `branding["fonts"]["header"]` style at H1. When `client_name == ""`, omit the client name from the cover; the cover-page logo (if present) still renders.

**Per-skill exception — voice handling:** cio-letter-prep is the one wired skill that COULD legitimately be argued to use `branding["voice"]` (it generates CIO-authored prose). Per the cio-letter-prep gotchas, voice is OUT of scope for this skill regardless: the CIO writes the prose; the loader's voice config is ignored. The fact that cio-letter-prep uses `load_visual_branding()` (not `load_client_branding()`) is the structural enforcement of this rule — the wrapper does not expose voice.

Future writing-pipeline skills (newsletter, content) that DO want voice will call `load_client_branding()` directly and document their voice handling in their own SKILL.md. They are out of scope for this integration pattern.

---

## §7 — Provenance footer line template

Every wired skill renders a Branding line in its Provenance footer. The line is unconditional — it appears whether or not `white_label_active`. Format:

| Condition | Markdown skills | Docx skills (cio-letter-prep) |
|---|---|---|
| Clean load | `Branding: white-label (source: <branding["source"]["reference"]>)` | same |
| `logo_missing` | `Branding: white-label (source: <ref>) (logo unavailable, omitted)` | `Branding: white-label (source: <ref>) (logo unavailable, omitted from cover)` |
| `config_not_found` | `Branding: default Parallax` | same |
| `schema_invalid` / `yaml_parse_error` | `Branding: default Parallax (config error)` | same |
| `schema_unavailable` | `Branding: white-label (best-effort, schema unavailable)` | same |
| Markdown skill, abs-local logo skipped per §5 | Append `Logo on file: <basename>` as a second Provenance line | N/A (docx embeds the logo directly) |

The docx `from cover` qualifier is more precise (the logo is specifically the cover-page header asset). Markdown skills have no cover; the unqualified `omitted` is correct for them.

For markdown skills the Provenance footer is the last block of the deliverable. For docx (cio-letter-prep) the Provenance footer is rendered in the small-italic style per cio-letter-prep/SKILL.md Provenance section.

---

## §8 — Gotchas

1. **Do not re-parse the config file.** `loader.py` already does `yaml.safe_load` with proper error handling; a second `yaml.safe_load` in a consumer skill bypasses that.
2. **Tolerate empty `client_name`.** Legacy configs predating the field return `""`. Header line in §5 simply omits the name in that case; do not error.
3. **Markdown logo path is environment-dependent.** Loader returns absolute local paths. Per §5 resolution: skip image embed for any path starting with `/` or `~`; add the Provenance "Logo on file" line instead.
4. **Voice is structurally inaccessible.** `branding["voice"]` raises `KeyError` (not `None`). Do not write defensive code like `branding.get("voice", {})` — that re-introduces the model-obedience-only guardrail this wrapper exists to remove. If a skill needs voice, it must explicitly call `load_client_branding()` (full loader) and document why.
5. **Semantic tokens are never overridden.** `cg-green-700`, `cg-red-700`, `cg-amber-*` carry meaning, not brand identity. Even when `white_label_active`, these remain unchanged. (Markdown skills have no color tokens to override; this rule applies to docx skills.)
6. **`white_label_active` is binary, not three-valued.** Clean and `logo_missing` both count as active (palette/fonts still usable). Every other error class is "default Parallax." Do not introduce a third state.

---

## §9 — Versioning

Loader return shape is the contract surface. If `load_visual_branding()` grows a new key (e.g., `icons`), update `_VISUAL_BRANDING_KEYS` in loader.py AND this doc's §3 in the same commit. If a new error class is added to the loader, update §4 in the same commit.

The `tests/test_loader.py::test_visual_branding_keys_are_subset_of_load_client_branding` test is the structural drift gate for the constant.
