# Error Handling, Edge Cases & Success Criteria

## Error Handling & Edge Cases

**Config exists but is corrupted:** `yaml.safe_load()` raises an exception — catch it, warn ("Config at ~/.parallax/client-branding/config.yaml failed to parse: <error>"), offer to overwrite via full onboarding flow or abort.

**Logo download fails (network error, 404):** Warn and preserve the URL as `branding.logos.primary`. Downstream skills must handle missing local files gracefully by falling back to the URL or omitting the logo.

**All color extraction returns empty:** In URL mode, this is common for heavily JS-rendered sites. Surface the gap clearly: "No colors extracted — the site may require JavaScript rendering. Try providing the hex colors manually via wizard mode."

**Font not on system (FontValidator returns warn):** This is expected for web fonts (Google Fonts, Adobe Fonts, etc.). The warn is informational. Downstream skills should specify the fallback font from `FontValidator._suggest_fallback()` in their CSS/PDF output stack.

**WCAG contrast fails (ratio <3.0):** Surface the failure prominently at the confirmation gate. Do not block the save — the client's brand guidelines take precedence. Record the failure in `validation_summary.colors.contrast`.

**`~/.parallax/client-branding/` not writable:** Hard-fail with a clear error before any I/O. Do not create partial state.

**Staging write fails mid-way:** Clean up the staging directory. Report: "Save failed: <file> write error. No files written. Safe to retry." The active config (if any) remains unchanged.

**PDF has >10 pages:** Read only the first 10 pages via the `pages` parameter. If average confidence is <0.6, offer to continue page-by-page or switch to wizard.

## Success Criteria

A successful workflow produces:
- `~/.parallax/client-branding/config.yaml` written, permissions 0600, valid YAML parseable by `yaml.safe_load()`, conforming to schema.yaml field names
- `~/.parallax/client-branding/assets/` exists with at least one downloaded logo file (if a logo URL was provided), directory permissions 0700
- `~/.parallax/client-branding/audit.jsonl` has at least one entry with `"action":"save"` and a valid `prev_entry_hash` chain
- User saw the confirmation gate and explicitly chose "Confirm and save" before any file was written
- Validation summary is present in config.yaml with status per asset (even if some are warn/fail)
- Downstream visual-consumer check: `yaml.safe_load(open("~/.parallax/client-branding/config.yaml"))["branding"]["colors"]["primary"]` returns the configured hex string
- When voice was extracted: `cfg["voice"]["enabled"] is True`, `cfg["voice"]["positioning"]` is a non-empty string, `len(cfg["voice"]["core_rules"]) >= 2`, `len(cfg["voice"]["anti_filler"]) >= 3`, and `cfg["voice"]["source_corpus"]["word_count"] >= 500`
- When multi-source was used: `cfg["multi_source"]["sources"]` lists every input, mismatches were either resolved at the gate or recorded; no silent merges
- When voice was NOT extracted: `cfg["voice"]["enabled"] is False` and downstream voice consumers fall back to defaults silently
