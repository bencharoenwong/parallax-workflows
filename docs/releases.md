# Building a release

The marketplace plugin is the primary distribution. Individual `.skill` files
are an upload fallback. Native-review holds and private-beta skills never enter
the default release. The manifest controls both sets.

## Prepare

Use a dedicated checkout. First create and activate its Python environment and
install the dependencies listed in [Contributing](../CONTRIBUTING.md#before-opening-a-pr).
`prepare`, `build` and `verify` all require PyYAML, which those requirements
install. All three commands also require the full maintainer-local scan-term
file, so configure it before running `prepare`; the developer partial-scan
option does not bypass this requirement.

Set `PARALLAX_ROOT` to the checkout's absolute path:

```bash
export PARALLAX_ROOT="$HOME/parallax-workflows"
python3 "$PARALLAX_ROOT/skills/_parallax/scripts/release.py" prepare YYYY.M.D
python3 "$PARALLAX_ROOT/skills/_parallax/scripts/distribution_docs.py"
```

Replace `YYYY.M.D` with the release date, and use a later date for each
subsequent release. Versions use `YYYY.M.D`,
without leading zeroes, and must represent a valid calendar date. This format
also satisfies semantic versioning. `prepare` rejects an earlier version;
rerunning it with the current version repairs generated files for that version
and does not create a new release. Once published, use a later version for
changes instead of replacing the existing tag or assets. The version literal
in `build_bundle.py` is the sole source. `prepare` updates it, renames the
CHANGELOG `## Unreleased` heading to the version, or adds a version heading
when none exists, and regenerates both plugin manifests. Review those changes
before committing through the repository's normal process. The command does
not commit, tag, push or publish.

## Check and build

```bash
bash "$PARALLAX_ROOT/skills/_parallax/scripts/run-gate-tests.sh"
python3 "$PARALLAX_ROOT/skills/_parallax/scripts/release.py" build --preview
```

A preview can use uncommitted changes. Its index records the base commit,
working-tree fingerprint and dirty state. Its download URLs are null. Preview
assets are for local testing, not publication. Builders use tracked files;
stage new runtime files before previewing them.
Package input paths under `skills/` and `examples/` must not contain symlinks.
Extracted plugin and upload files must be UTF-8 text without NUL bytes so the
full term scan can inspect their contents.

After review and commit, build without `--preview`. A release build requires a
clean tree and a matching CHANGELOG heading. Every build requires the full
maintainer-local scan terms, even if the developer partial-scan option is set.
No term list is copied into the assets.

```bash
python3 "$PARALLAX_ROOT/skills/_parallax/scripts/release.py" build
python3 "$PARALLAX_ROOT/skills/_parallax/scripts/release.py" verify "$PARALLAX_ROOT/dist/YYYY.M.D"
```

Each build writes to a fresh directory. Existing output is never replaced.
Use `--out` for a distinct review build. On failure, the command exposes no
partial release directory. The builder scans extracted packages, checks their
references, and rejects changes to tracked source files during the build.

## Assets

- `parallax-plugin.zip`: one plugin folder, including its connector declaration.
- One `.skill` file per web workflow and release-tier standalone translator.
- `parallax-claude-ai-skills.zip`: a collection to unzip before individual skill uploads.
- `index.json`: version, source provenance, skill descriptions, distributions,
  asset names, byte sizes, SHA-256 hashes, pinned and latest download URLs.
  Each description matches the packaged skill in the row's mapped asset.
- `SHA256SUMS`: checksums for all assets and the index.

The index describes planned download URLs. They become available only after an
approved GitHub Release publishes these files. Checksums detect corruption;
they are not cryptographic signatures or proof of publisher identity.

## Publish gate

Run fresh-account installation checks before the first public release: install
the plugin, connect Parallax, run the concierge and a stock workflow, then test
one portfolio workflow and both supported translators. Test Claude chat,
Cowork and Claude Code separately. Verify account sync and version updates.
Offline package tests do not establish those behaviors.

After owner approval, use tag `v<version>` at the exact `source.commit` in the
non-preview index and attach only the files in that release directory. Do not
publish previews. Keep marketplace, plugin and release versions equal. A
release does not itself merge the corresponding source branch.
