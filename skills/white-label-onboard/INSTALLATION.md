# White-Label Onboarding — Installation Guide

## Prerequisites

- **Python**: 3.9 or later
- **Dependencies** (auto-installed via Claude Code):
  - `pyyaml` — YAML config parsing
  - `jsonschema` — Schema validation
  - `pillow` (PIL) — Image dimension checking
  - `matplotlib` — Font detection via FontManager
  - `requests` or `scrapling` — Web content fetching (for URL extraction)

## Installation

The white-label onboarding skill is part of the `parallax-workflows` repository. No separate installation is required—it's automatically discovered by Claude Code.

### Verify Installation

```bash
# In any Claude Code session, test the skill:
ls -la skills/white-label-onboard/
ls -la skills/_parallax/white-label/

# Expected output: SKILL.md, schema.yaml, loader.py, validator.py, extract.py, tests/
```

### First-Time Directory Setup

On first run, the skill creates the global branding directory:

```bash
mkdir -p ~/.parallax/client-branding/assets
chmod 700 ~/.parallax/client-branding
chmod 700 ~/.parallax/client-branding/assets
```

If directory creation fails, manually create it:

```bash
mkdir -p ~/.parallax/client-branding/assets
chmod 700 ~/.parallax/client-branding
chmod 700 ~/.parallax/client-branding/assets
```

The `chmod 700` restriction ensures only the current user can read/write branding configuration.

## Dependencies

### Python Packages

Install all dependencies:

```bash
pip install pyyaml jsonschema pillow matplotlib requests
```

Or with `scrapling` (recommended for robust web scraping):

```bash
pip install pyyaml jsonschema pillow matplotlib scrapling
```

### Optional: For PDF Extraction

If you plan to extract branding from PDF files, install one of:

```bash
pip install pypdf2              # Lightweight, pure Python
pip install pdfplumber          # More features, better text extraction
```

Either is auto-detected; the skill uses whichever is available.

## Verification

### Test: Import the Loader

```python
from skills._parallax.white_label.loader import load_client_branding

result = load_client_branding()
print(f"Error: {result['error']}")
print(f"Config path: {result['source']}")
```

**Expected output (on fresh install):**
```
Error: config_not_found
Config path: {}
```

This is normal—config will be created after first onboarding.

### Test: Run Unit Tests

```bash
pytest skills/_parallax/white-label/tests/ -v
```

**Expected output:**
```
============================= 67 passed in 12s ==============================
```

All 67 tests (extraction, validation, loader, integration) should pass.

### Test: Font Detection

```python
from skills._parallax.white_label.validator import FontValidator

fonts = FontValidator.get_system_fonts()
print(f"Found {len(fonts)} fonts on system")
print(f"Examples: {list(fonts)[:5]}")
```

**Expected output:**
```
Found XXX fonts on system
Examples: ['Helvetica', 'Arial', 'Georgia', ...]
```

## First Onboarding

After installation, onboard your first client:

```bash
/parallax-white-label-onboard
```

Follow the interactive prompts:
1. **Source selection**: URL, PDF, or manual wizard?
2. **Asset review**: Confirm extracted colors, logos, fonts
3. **Adjustment**: Manually edit any assets if needed
4. **Confirmation**: Approve and save

After completion, verify:

```bash
cat ~/.parallax/client-branding/config.yaml
ls -la ~/.parallax/client-branding/assets/
```

**Expected output:**
```yaml
# config.yaml contents
metadata:
  schema_version: 1
  client_name: "Your Client Name"
  ...

branding:
  colors:
    primary: "#XXXXXX"
    ...
```

## Configuration

### Config Location

- **Path**: `~/.parallax/client-branding/config.yaml`
- **Permissions**: `0600` (read/write owner only)
- **Format**: YAML with embedded JSON Schema validation

### Environment Variables

No environment variables required. The skill uses hardcoded paths:

```
~/.parallax/client-branding/config.yaml       (configuration)
~/.parallax/client-branding/assets/           (logo files)
skills/_parallax/white-label/schema.yaml      (JSON Schema)
```

### Manual Configuration

If needed, you can manually edit the config:

```bash
# Edit configuration
nano ~/.parallax/client-branding/config.yaml

# Verify syntax
python -c "import yaml; yaml.safe_load(open('~/.parallax/client-branding/config.yaml').read())"

# Re-onboard if validation fails
/parallax-white-label-onboard
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'jsonschema'"

Install missing dependencies:

```bash
pip install jsonschema pyyaml pillow matplotlib
```

### "Font detection returned 0 fonts"

This is rare but can happen in headless environments. The skill gracefully falls back to system fonts without detection:

```bash
# Test matplotlib font detection
python -c "import matplotlib.font_manager; fonts = matplotlib.font_manager.findSystemFonts(); print(len(fonts), 'fonts found')"
```

If no fonts are found, install system fonts:

```bash
# macOS
brew install ttf-dejavu ttf-liberation ttf-inconsolata

# Ubuntu/Debian
sudo apt-get install fonts-dejavu fonts-liberation fonts-ubuntu

# Windows
# Use Windows Settings → Fonts → Get more fonts in Microsoft Store
```

### "Permission denied: ~/.parallax/client-branding/"

The directory was created with restrictive permissions. Adjust if needed:

```bash
chmod 700 ~/.parallax/client-branding
chmod 700 ~/.parallax/client-branding/assets
```

### "Config validation failed: schema_invalid"

Config.yaml structure doesn't match schema. Common issues:

1. **schema_version is a string** (should be integer):
   ```yaml
   # ❌ Wrong
   metadata:
     schema_version: "1"
   
   # ✓ Correct
   metadata:
     schema_version: 1
   ```

2. **source.confidence is out of range** (must be 0.0–1.0):
   ```yaml
   # ❌ Wrong
   source:
     confidence: 150

   # ✓ Correct
   source:
     confidence: 0.95
   ```

3. **Missing required fields** (metadata, branding, confidence_scores):
   ```yaml
   # ✓ Correct structure
   metadata: {...}
   branding: {...}
   confidence_scores: {...}
   ```

To fix, re-run onboarding:

```bash
rm ~/.parallax/client-branding/config.yaml
/parallax-white-label-onboard
```

### "Logo file not found: ~/.parallax/client-branding/assets/logo.png"

Logo path in config.yaml is incorrect or file was deleted. Solutions:

1. **Verify file exists**:
   ```bash
   ls -la ~/.parallax/client-branding/assets/
   ```

2. **Check config path is correct**:
   ```bash
   grep "primary:" ~/.parallax/client-branding/config.yaml
   ```

3. **Re-upload logo**:
   ```bash
   cp /path/to/logo.png ~/.parallax/client-branding/assets/
   ```

4. **Full re-onboarding** (if paths are corrupted):
   ```bash
   rm ~/.parallax/client-branding/config.yaml
   /parallax-white-label-onboard
   ```

### "Extraction failed: unable to fetch URL"

URL scraping failed (site blocked, network issue, or timeout). Alternatives:

1. **Try PDF instead**: Download the website as PDF, extract from PDF
2. **Use wizard**: Manually enter colors, logos, fonts
3. **Check URL**: Ensure URL is correct and site is reachable

```bash
# Test URL reachability
curl -I https://example.com
```

### "WCAG contrast ratio too low"

Brand colors don't meet accessibility standards. Solution:

1. **Review warning**: Check which color pair failed
2. **Adjust color**: Suggested lighter/darker variant is provided
3. **Confirm adjustment**: Approve or manually edit in wizard

Example:
```
⚠ PRIMARY (#FF5733) on BACKGROUND (#F5F5F5): Ratio 4.12 < 4.5 (WCAG AA fail)
Suggestion: Darken primary to #E63F1F or lighten background to #FFFFFF
```

### "Fonts not rendering in PDFs"

Font specified in config is not available on the rendering machine:

1. **Check font installation**:
   ```bash
   python -c "from skills._parallax.white_label.validator import FontValidator; print('Inter' in FontValidator.get_system_fonts())"
   ```

2. **Install font** (if missing):
   ```bash
   # Download from Google Fonts or system font manager
   # Install via system package manager or font manager GUI
   ```

3. **Check config fallback chain** (see `supported-fonts.md`):
   ```yaml
   fonts:
     header: Inter, Roboto, Helvetica, sans-serif  # Fallbacks
   ```

4. **Use web-safe fallback**: If custom font can't be installed, use `Helvetica`, `Roboto`, or `Georgia`.

## Performance Notes

- **First load**: Config is loaded once at module import; subsequent calls use cached schema
- **Font detection**: Occurs once on first validation; results are cached
- **Logo path resolution**: Tilde expansion happens during load; slow on first call, cached after
- **No network calls**: Extraction happens offline after initial URL fetch; loader never requires network

## Security Considerations

### File Permissions

- **Config file**: `0600` (owner-only read/write)
- **Assets directory**: `0700` (owner-only access)
- **Logo files**: Inherit directory permissions

Do NOT change to world-readable (e.g., `chmod 644`); branding configs may contain paths or references to sensitive assets.

### Credential Handling

The loader does NOT handle credentials. If your extraction source requires authentication:
1. Use a public mirror (public website instead of internal dashboard)
2. Extract manually and re-save via wizard
3. Contact support for secure integration options

## Support

For issues not covered here:
- Check `README.md` for usage overview
- See `references/validation-rules.md` for validation details
- Review test files for code examples
- Open an issue on the parallax-workflows repository

## Upgrade & Rollback

The white-label skill uses semantic versioning. Config schema is versioned (currently `schema_version: 1`). 

Future upgrades will:
1. Increment `schema_version` if breaking changes occur
2. Provide migration guide in release notes
3. Support both old and new schema versions during transition period

To rollback to a previous config:

```bash
# Backup current config
cp ~/.parallax/client-branding/config.yaml ~/.parallax/client-branding/config.yaml.backup

# Restore previous version
git checkout HEAD~1 -- ~/.parallax/client-branding/config.yaml

# Verify
python -c "from skills._parallax.white_label.loader import load_client_branding; print(load_client_branding()['error'])"
```
