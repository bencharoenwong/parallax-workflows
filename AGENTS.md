# Parallax workflows: agent entry point

Read `CLAUDE.md` and `CONTRIBUTING.md` before modifying this repository. This is
a public repository; local operating notes and private material must stay out
of tracked files, commit messages and release assets.

## Run a workflow

For a requested workflow, read `skills/<workflow>/SKILL.md` and follow it.
Read referenced shared files relative to that skill's directory. Begin with
`skills/parallax-concierge/SKILL.md` when the user needs help choosing a workflow.

Discover the connected Parallax MCP tools in the active host. Use their exact
names and schemas; never manufacture a server namespace. A missing connector
is unavailable data. Do not fabricate results. Ask the user to connect and
authenticate Parallax when the workflow requires it.

Claude users can install the marketplace plugin through the README's Get
started instructions. Other agents can read skills directly from this clone.
For a host-local installation, follow that host's skill installation rules and
preserve the relative layout of each skill and its shared `_parallax` files.
`install.sh` targets Claude Code by default; do not run it as a generic agent installer.

## Distribution metadata

`skills/_parallax/manifest.json` controls plugin, upload and standalone tiers.
Held and private-beta entries are not public-release candidates. Run
`skills/_parallax/scripts/distribution_docs.py` after changing distribution or
role metadata. Rebuild generated plugin files with `build_bundle.py plugin`.
Never edit `plugin/` or `.claude-plugin/marketplace.json` directly.

Published releases, once available, expose a machine-readable index at
`https://github.com/bencharoenwong/parallax-workflows/releases/latest/download/index.json`.
If no release exists, use the local manifest; do not invent a download URL.
Check the index version, source commit and asset checksum before installing.
Reject an index with `preview: true` for public distribution.

## Verify and release

Run `bash skills/_parallax/scripts/run-gate-tests.sh` for the offline gate.
Use `release.py prepare`, `release.py build` and `release.py verify` as described
in `docs/releases.md`. Publishing requires explicit owner approval. Do not
commit, push, create tags or publish unless the user requests it. When a
`no-mistakes` remote exists, follow the gated push rules in `CLAUDE.md`.
