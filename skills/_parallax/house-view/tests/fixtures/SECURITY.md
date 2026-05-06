# Test-only signing fixtures

Files in this directory:

- `test-signing-key.priv` — Ed25519 private key used ONLY by round-trip
  signing tests. The `kid` is fixture-scoped (`test-only`) and has no
  production trust binding. See `trusted_keys.json` (`use: "test-only"`).
- `trusted_keys.json` — public key registry. Production deployments
  configure their own kids via the manifest signing flow.

These are intentionally checked in. They are referenced by:

- `skills/_parallax/house-view/tests/_gen_test_fixture.py`
- `skills/_parallax/house-view/tests/test_chain_emit.py`
- `skills/_parallax/house-view/tests/test_skill_integration.py`
- `skills/_parallax/house-view/tests/test_manifest_cache.py`

Repo-level scanner allowlists exempt this path:

- `.gitleaks.toml` — `[allowlist].paths` entry
- `.github/secret_scanning.yml` — `paths-ignore` entry

Do NOT replace this fixture with a production key. Production signing
keys must never be checked into source control.
