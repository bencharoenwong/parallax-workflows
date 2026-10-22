# Status Block Format

Output template for `/parallax-white-label-onboard --status`.

```
Active client branding
──────────────────────
Client:       <client_name>
Source:       <type>: <reference>
Configured:   <extracted_at>

Colors:
  Primary:    <hex> — <swatch text approximation>
  Secondary:  <hex>
  Accent:     <hex>
  Background: <hex>
  Text:       <hex>
  Contrast:   <ratio>:1 (<pass|warn|fail>)

Logos:
  Primary:    <local path | not configured>
  Favicon:    <local path | not configured>

Fonts:
  Header:     <name>
  Body:       <name>
  Monospace:  <name>

Voice:
  Enabled:    <yes | no>
  Register:   <e.g., formal-institutional>
  Tone:       <comma-list of primary_attributes | not configured>
  Corpus:     <N words from M documents | not configured>
  Confidence: <X.XX | not configured>

Validation:   <N pass, N warn, N fail>
Audit chain:  <ok | not yet initialized>
```

If `config.yaml` fails to load (YAML parse error, missing required keys), show:

```
! Config corrupted or outdated. Re-run /parallax-white-label-onboard to reconfigure.
```
