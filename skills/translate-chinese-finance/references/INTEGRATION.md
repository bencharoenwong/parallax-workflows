# Integration with the Parallax Translation Pipeline

Status: skill files ready, loader ready. Pipeline-side wiring is not yet done — this document is the punch list.

The Thai pipeline lives in `~/Downloads/CIO report/` (locally — should be relocated to a permanent project dir):

```
CIO report/
├── load_skill.py                              # parses ~/.claude/skills/translate-thai/SKILL.md
├── final_translate - Thai - Short_CIO.py      # Pass 1: translate
├── review_translation - Thai - Short_CIO.py   # Pass 2: review
├── pass4_final_filter_CIO.py                  # Pass 4: naturalness filter
├── Disclosure_CIO_Thai.html                   # Pass 4 disclosure template
├── schema_helper.py
├── report_schema_enhanced.json
└── output/
```

For Chinese, mirror that structure with locale-aware variants.

---

## 1. Loader ✅ DONE

`~/parallax-workflows/skills/translate-chinese-finance/references/load_skill.py`

- Parses both top-level web-upload skill files (`skill_simplified.md`, `skill_traditional.md`); falls back to legacy `runtime-config-zh-{CN,TW}.md` names if those exist.
- Returns the same shape as Thai's `get_dictionaries()` / `get_prompts()` so downstream scripts can be near-copies of the Thai equivalents.
- Resolves the skill dir via (in order): `CHINESE_SKILL_DIR` env var → `~/.claude/skills/translate-chinese-finance/references/` → its own directory.
- CLI smoke test: `python3 load_skill.py --locale zh-CN` (or `zh-TW`).

Verified: 418 label translations + 83 replacement rules per locale.

---

## 2. Translation Pass Scripts — TO DO

For each existing Thai script, create a Chinese variant. Recommended naming (parallel to Thai):

```
final_translate - Chinese - Short_CIO.py
review_translation - Chinese - Short_CIO.py
pass4_final_filter_CIO_Chinese.py
Disclosure_CIO_Chinese_zh-CN.html
Disclosure_CIO_Chinese_zh-TW.html
```

Take the Thai version and apply this mechanical transform:

| Thai code | Chinese code |
|-----------|--------------|
| `from load_skill import get_dictionaries, get_prompts` | `from load_skill_chinese import get_dictionaries, get_prompts` |
| `dicts = get_dictionaries()` | `dicts = get_dictionaries(locale=LOCALE)` where `LOCALE` is `"zh-CN"` or `"zh-TW"` (CLI arg) |
| `Disclosure_CIO_Thai.html` | `Disclosure_CIO_Chinese_{locale}.html` |
| Output dir `output/thai/...` | `output/chinese/{locale}/...` |
| Hardcoded "Thai" strings in prompt instructions | Replaced by the prompts loaded from the runtime config (`get_prompts(locale)`) — these already include locale-specific instructions. |

Make `LOCALE` a required CLI flag on every Chinese script: `python3 final_translate_chinese.py --locale zh-CN <input>`.

---

## 3. Loader Placement Options

### Option A: bundled with the CIO report scripts (recommended)
Copy `load_skill.py` from this skill into `CIO report/load_skill_chinese.py`:

```bash
cp ~/parallax-workflows/skills/translate-chinese-finance/references/load_skill.py \
   "<project>/CIO report/load_skill_chinese.py"
```

Pros: scripts can `from load_skill_chinese import ...` without sys.path hacks.
Cons: two copies of the loader to keep in sync with the parallax-workflows source.

### Option B: shared via PYTHONPATH
```bash
export PYTHONPATH="$HOME/parallax-workflows/skills/translate-chinese-finance/references:$PYTHONPATH"
```
Then scripts do `from load_skill import ...` (will collide with Thai loader if both on path — rename one).

### Option C: package install
Make `load_skill.py` part of a `parallax_translate` python package and install editable. Most disciplined but heaviest setup.

---

## 4. Disclosure Templates

Pass 4 of the Thai pipeline injects `Disclosure_CIO_Thai.html` near the end of the report. For Chinese, two templates are needed (one per locale). Source the legal/disclosure text from the Compliance team — do NOT translate the Thai disclosure; the Chinese disclosure is a separate document.

---

## 5. CLAUDE.md / global skill index

Add a one-line entry to `~/.claude/CLAUDE.md` under the Skills section pointing to `translate-chinese-finance` (alongside the existing `translate-thai-finance` reference) so it's discoverable from the Skill tool.

---

## 6. Regenerating the web-upload skill files

The `chinese_translation_config.py` source lives in `~/Downloads/` (and `~/Downloads/chinese_translation_review_for_kevin/`). When that file changes:

1. Regenerate `skill_simplified.md` from `chinese_translation_config.py` (existing pipeline already does this — the file's top says "Auto-generated from `chinese_translation_config.py`").
2. Build a `chinese_translation_config_tw.py` analogue (currently `skill_traditional.md` is hand-tuned canonical; the source `.py` doesn't exist yet).
3. Write the regenerator to emit `skill_traditional.md` from the TW config.

Until step 2 exists, treat `skill_traditional.md` as hand-edited canonical and don't overwrite it. Drop the regenerated file at the top level of this skill (`~/parallax-workflows/skills/translate-chinese-finance/skill_simplified.md`) — the loader picks it up there.

---

## 7. Marko / Kira sharing

Once the pipeline runs cleanly on this machine, decide whether Marko or Kira need the skill. If yes, follow `~/.claude/skills/PATHS.md`:
- For Marko: symlink `~/parallax-workflows/skills/translate-chinese-finance` → `~/.openclaw-marko/skills/translate-chinese-finance`, register in Marko's ROUTER.md / AGENTS.md / MEMORY.md.
- For Kira: copy as a full directory (Kira's pattern).

---

## 8. Outstanding decisions for the user

1. **Where does the CIO report project live long-term?** Currently `~/Downloads/CIO report` — should be moved (e.g., into `~/parallax-api/` or its own repo) before further work.
2. **Should the Thai loader be unified with the Chinese loader?** They use different SKILL.md formats today (Thai = human-readable headers, Chinese = CONSTANT_NAME headers). Could converge if we regenerate the Thai SKILL.md from a `thai_translation_config.py` source the same way Chinese does.
3. **zh-HK distinct config?** Currently zh-TW covers HK by convention. If HK-listed reports need different terminology (e.g., HK uses some mainland forms), add a top-level `skill_hong_kong.md` (parallel to `skill_simplified.md` / `skill_traditional.md`), wire `"zh-HK"` into `VALID_LOCALES` and `_LOCALE_FILES` in `load_skill.py`.
