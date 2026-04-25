#!/usr/bin/env python3
"""Reasoning chain emitter (Batch 4).

Implements the chain envelope from notes/2026-04-24-reasoning-chain-spec.md
§2-§4. The chain is the audit artifact: every consumer-skill invocation
that applies a house view writes one chain per run, capturing the view,
the manifest in force, the base scores, and the final portfolio in a
single YAML file an auditor can replay against.

Scope (Batch 4):
  - `emit_chain()` builds + writes a structured chain.yaml per spec §2.
  - Phase-0 transition path: when no manifest is in force, manifest_ref
    is filled with the `phase-0-bundled` placeholder per chain spec §3.2,
    skill_version-pinned replay still works because all values come
    from the skill code at that tag.
  - Directory creation enforces 0700 (security audit B-2 / chain spec §4.3).
  - Files written 0600 with atomic rename, parallel to the manifest cache.
  - Anti-collision assertion (chain spec §3.2 normative): if a fresh
    manifest_ref.hash equals a recomputed signing_payload_hash for the
    same manifest, refuse to emit. The verifier already enforces this
    at verification time; emit_chain re-checks defensively when the
    caller passes both hashes.

Out of scope:
  - Prose rendering of the chain (§6.1 vs §6.2). The structured form
    is canonical; prose is on-demand and deferred to Batch 4.5.
  - Chain signing (§3.6). v1 default is `alg: "none"`; client-side
    signing waits for the D-migration.
  - Hash-receipt ledger upload (§4.2 v2 option). v1 is local-only.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import manifest_verify  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_CHAIN_DIR = Path.home() / ".parallax" / "reasoning-chains"
_CHAIN_FILE_MODE = 0o600
_CHAIN_DIR_MODE = 0o700

# Spec version of the chain artifact itself (chain spec §2).
CHAIN_SPEC_VERSION = "1.0.0"

# Phase-0 manifest_ref shape (chain spec §3.2 transition special case).
_PHASE_0_MANIFEST_REF: dict[str, Any] = {
    "calibration_version": "phase-0-bundled",
    "schema_version": None,
    "hash": None,
    "signed_by": None,
    "signing_key_id": None,
    "sections_touched": [],
    "notes": None,
}

# Top-level org_id placeholder when no manifest has authenticated the
# session (chain spec §3.2 Phase-0 special case).
PHASE_0_ORG_ID = "phase-0-unauthenticated"


# --- Errors -----------------------------------------------------------

class ChainEmitError(Exception):
    error_code: str = "chain_emit_error"


class ChainEnvelopeMalformed(ChainEmitError):
    error_code = "chain_envelope_malformed"


class ChainAntiCollisionTripped(ChainEmitError):
    """Defensive guard (chain spec §3.2 normative): the manifest_ref.hash
    being recorded equals the signing_payload_hash of the same manifest,
    meaning the manifest's `signature` field was missing or trivial.
    Refuse to emit a chain whose trust anchor is indistinguishable from
    the unsigned payload.
    """
    error_code = "manifest_signature_missing"


# --- Helpers ----------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, _CHAIN_DIR_MODE)
    except OSError as e:
        logger.warning(
            "chain_dir_permissions_unsafe: cannot chmod %s to 0%o: %s",
            path, _CHAIN_DIR_MODE, e,
        )


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text to `path` atomically with mode 0600.

    Uses tempfile in the same directory + os.replace, mirroring the
    manifest cache's write pattern so chain emission and cache writes
    have identical atomicity semantics.
    """
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".yaml", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(tmp_path, _CHAIN_FILE_MODE)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sections_touched_filtered(
    manifest_dict: dict[str, Any] | None,
    requested: list[str] | None,
) -> list[str]:
    """Return `sections_touched` after applying the `active: false`
    suppression rule from chain spec §7 (preserves PRISM-routing privacy
    posture: anchors with active=false are NOT advertised in chains).
    """
    if requested is None:
        return []
    if manifest_dict is None:
        return list(requested)
    values = manifest_dict.get("values", {}) or {}
    out: list[str] = []
    for anchor in requested:
        section = values.get(anchor)
        if isinstance(section, dict) and section.get("active") is False:
            continue
        out.append(anchor)
    return out


def _build_manifest_ref(
    *,
    manifest_dict: dict[str, Any] | None,
    manifest_ref_hash: str | None,
    signing_payload_hash: str | None,
    sections_touched: list[str] | None,
    notes: str | None,
) -> dict[str, Any]:
    """Build the manifest_ref block. Phase-0 path returns the bundled
    placeholder; manifest path returns the live values + the verified
    hash (asserting it differs from the signing-payload hash).
    """
    if manifest_dict is None:
        # Phase-0: fixed placeholder. sections_touched stays empty
        # because no manifest sections were applied — values came from
        # bundled skill code.
        ref = dict(_PHASE_0_MANIFEST_REF)
        if notes:
            ref["notes"] = notes
        return ref

    if manifest_ref_hash is None:
        raise ChainEnvelopeMalformed(
            "manifest_dict provided but manifest_ref_hash is None; pass "
            "the verified hash from manifest_verify.verify_manifest()"
        )
    if (
        signing_payload_hash is not None
        and manifest_ref_hash == signing_payload_hash
    ):
        raise ChainAntiCollisionTripped(
            "manifest_ref.hash equals signing_payload_hash for the same "
            "manifest. Refusing to emit chain — the trust anchor would be "
            "indistinguishable from the unsigned payload."
        )

    # signed_by: per spec §3.2 we record the issuer (server identity);
    # v1 reads it from the manifest's optional `signed_by` field if the
    # endpoint sets one, else "parallax-mcp" as the v1 default issuer.
    signed_by = manifest_dict.get("signed_by") or "parallax-mcp"

    return {
        "calibration_version": manifest_dict.get("calibration_version"),
        "schema_version": manifest_dict.get("schema_version"),
        "hash": f"sha256:{manifest_ref_hash}",
        "signed_by": signed_by,
        "signing_key_id": manifest_dict.get("signing_key_id"),
        "sections_touched": _sections_touched_filtered(manifest_dict, sections_touched),
        "notes": notes,
    }


def _normalize_base_scores(base_scores: dict[str, Any]) -> dict[str, Any]:
    """Validate the base_scores block. Caller passes either:
        {"response_inline": <dict>, "response_hash": "<sha256>"}
        {"response_cache_path": "<path>", "response_hash": "<sha256>"}
    response_hash is always required (it's the determinism anchor).
    """
    response_hash = base_scores.get("response_hash")
    if not isinstance(response_hash, str) or not response_hash:
        raise ChainEnvelopeMalformed(
            "base_scores.response_hash is required (sha256 of the "
            "JCS-canonicalized MCP response)"
        )
    has_inline = "response_inline" in base_scores
    has_path = "response_cache_path" in base_scores
    if has_inline == has_path:
        raise ChainEnvelopeMalformed(
            "base_scores must have exactly one of response_inline OR "
            "response_cache_path"
        )
    return {
        "response_inline": base_scores.get("response_inline"),
        "response_cache_path": base_scores.get("response_cache_path"),
        "response_hash": response_hash,
    }


def _normalize_final_portfolio(fp: dict[str, Any]) -> dict[str, Any]:
    weights = fp.get("weights")
    if not isinstance(weights, dict):
        raise ChainEnvelopeMalformed("final_portfolio.weights must be a dict")
    weight_sum = sum(weights.values())
    if abs(weight_sum - 1.0) > 1e-9 and abs(weight_sum) > 1e-9:
        # Allow weights={} (empty portfolio), but if non-empty, must sum to 1.
        raise ChainEnvelopeMalformed(
            f"final_portfolio.weights sums to {weight_sum}; expected 1.0 "
            "(or {} for empty)"
        )
    band = fp.get("sensitivity_band_check") or {}
    status = band.get("status")
    if status not in {"PASS", "WARN", "KILL", None}:
        raise ChainEnvelopeMalformed(
            f"sensitivity_band_check.status={status!r}; must be PASS/WARN/KILL or null"
        )
    return {
        "weights": weights,
        "sensitivity_band_check": band,
    }


# --- Emitter ---------------------------------------------------------

def emit_chain(
    *,
    view: dict[str, Any] | str,
    base_scores: dict[str, Any],
    final_portfolio: dict[str, Any],
    run_id: str,
    skill_version: str,
    manifest_dict: dict[str, Any] | None = None,
    manifest_ref_hash: str | None = None,
    signing_payload_hash: str | None = None,
    sections_touched: list[str] | None = None,
    org_id: str | None = None,
    skill: str = "parallax-load-house-view",
    notes: str | None = None,
    chain_dir: Path | str | None = None,
    overwrite: bool = False,
) -> Path:
    """Emit a single reasoning chain to disk.

    Args:
        view: the CIO YAML view as a dict (or already-serialized YAML string).
            Inlined verbatim per chain spec §3.3.
        base_scores: dict containing exactly one of {response_inline,
            response_cache_path} plus `response_hash`. See chain spec §3.4.
        final_portfolio: dict with `weights` (dict[ticker, float]) and
            optional `sensitivity_band_check` per chain spec §3.5.
        run_id: ULID-or-uuid string identifying this run.
        skill_version: `<package>@<semver>` — replay anchor (chain spec §3.1).
        manifest_dict: the verified manifest dict (or None for Phase-0).
        manifest_ref_hash: SHA-256 hex of JCS(full manifest INCLUDING
            signature). Required when manifest_dict is provided. Get it
            from manifest_verify.verify_manifest()['manifest_ref_hash'].
        signing_payload_hash: optional SHA-256 hex of JCS(manifest with
            signature stripped). When provided, emit_chain asserts it
            differs from manifest_ref_hash (defensive anti-collision
            check, chain spec §3.2 normative).
        sections_touched: list of manifest section anchors actually read
            during this run. Anchors with active=false in the manifest
            are auto-suppressed per chain spec §7.
        org_id: caller's resolved org_id. When None, defaults to
            manifest's org_id (or PHASE_0_ORG_ID for Phase-0).
        skill: which consumer skill is emitting (`parallax-<name>`).
        notes: optional manifest_ref.notes field for audit-relevant
            events (offline expiry, session-pin refresh, etc.).
        chain_dir: where to write. Defaults to ~/.parallax/reasoning-chains/.
        overwrite: if False (default), refuse to write when target file
            exists — protects against run_id collisions overwriting an
            audit trail.

    Returns:
        Path to the written chain.yaml.

    Raises:
        ChainEnvelopeMalformed: structural problems with inputs.
        ChainAntiCollisionTripped: anti-collision defensive guard.
        FileExistsError: run_id collision and overwrite=False.
    """
    # Resolve org_id
    if org_id is None:
        if manifest_dict is not None:
            org_id = manifest_dict.get("org_id") or PHASE_0_ORG_ID
        else:
            org_id = PHASE_0_ORG_ID

    manifest_ref = _build_manifest_ref(
        manifest_dict=manifest_dict,
        manifest_ref_hash=manifest_ref_hash,
        signing_payload_hash=signing_payload_hash,
        sections_touched=sections_touched,
        notes=notes,
    )

    chain: dict[str, Any] = {
        "spec_version": CHAIN_SPEC_VERSION,
        "skill_version": skill_version,
        "skill": skill,
        "run_id": run_id,
        "emitted_at": _utcnow_iso(),
        "org_id": org_id,
        "manifest_ref": manifest_ref,
        "view": view if not isinstance(view, str) else yaml.safe_load(view),
        "base_scores": _normalize_base_scores(base_scores),
        "final_portfolio": _normalize_final_portfolio(final_portfolio),
        "signature": {"alg": "none", "value": None},  # v1 default
    }

    # Resolve write path.
    if chain_dir is None:
        chain_dir = DEFAULT_CHAIN_DIR
    chain_dir = Path(chain_dir)
    month_dir = chain_dir / datetime.now(timezone.utc).strftime("%Y-%m")
    _ensure_dir(month_dir)
    out_path = month_dir / f"{run_id}.yaml"
    if out_path.exists() and not overwrite:
        raise FileExistsError(
            f"chain file already exists: {out_path}. "
            "Pass overwrite=True only if this is intentional (e.g., replay)."
        )

    # Render YAML deterministically (sorted keys, default flow style off).
    yaml_text = yaml.safe_dump(
        chain,
        default_flow_style=False,
        sort_keys=True,
        allow_unicode=True,
    )
    _atomic_write_text(out_path, yaml_text)
    return out_path


def emit_phase_0_chain(
    *,
    view: dict[str, Any] | str,
    base_scores: dict[str, Any],
    final_portfolio: dict[str, Any],
    run_id: str,
    skill_version: str,
    sections_touched: list[str] | None = None,
    notes: str | None = "phase-0-bundled: values from skill code, no manifest in force",
    chain_dir: Path | str | None = None,
    skill: str = "parallax-load-house-view",
) -> Path:
    """Convenience wrapper: emit a chain in Phase-0 mode.

    Equivalent to `emit_chain(manifest_dict=None, ...)` but documents
    the calibration-status flip clearly at call sites — Phase-0 chains
    are explicitly NOT manifest-bound and consumers should treat them
    as the heuristic_phase0 calibration_status disclosure surface.
    """
    return emit_chain(
        view=view,
        base_scores=base_scores,
        final_portfolio=final_portfolio,
        run_id=run_id,
        skill_version=skill_version,
        manifest_dict=None,
        sections_touched=sections_touched,
        notes=notes,
        chain_dir=chain_dir,
        skill=skill,
    )


if __name__ == "__main__":  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(description="Read a chain YAML and pretty-print key fields.")
    p.add_argument("chain_path")
    args = p.parse_args()
    chain = yaml.safe_load(Path(args.chain_path).read_text())
    print(f"run_id          : {chain.get('run_id')}")
    print(f"skill_version   : {chain.get('skill_version')}")
    print(f"emitted_at      : {chain.get('emitted_at')}")
    print(f"org_id          : {chain.get('org_id')}")
    print(f"calibration     : {chain.get('manifest_ref', {}).get('calibration_version')}")
    print(f"manifest hash   : {chain.get('manifest_ref', {}).get('hash')}")
    print(f"sections        : {chain.get('manifest_ref', {}).get('sections_touched')}")
    print(f"weights         : {len(chain.get('final_portfolio', {}).get('weights') or {})} positions")
    print(f"band status     : {(chain.get('final_portfolio', {}).get('sensitivity_band_check') or {}).get('status')}")
    print(f"signature alg   : {(chain.get('signature') or {}).get('alg')}")
