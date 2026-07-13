# Phase 4 — World verdict (Pass 1 synthesis)

Loaded when Phase 4 fires. This is the client-invariant synthesis that closes Pass 1 — the last
phase before any client conditioning. It runs on every thesis, profile or not.

## What Phase 4 consumes

The **structured records** already produced in Phases 1–3, not the raw tool output:

- the thesis restatement (Phase 1);
- the full Assumption Map — all five layers (layer-5 rows still marked `needs-client-profile`
  unless Phase 5 will run);
- every layer-1–4 assumption's Phase-2/3 record: `status`, `break_condition`, `magnitude`,
  `time_to_play_out`, `base_severity`;
- the Phase-3 position reads (direction alignment, peer-relative factor check, macro alignment,
  news + staleness), if the thesis named any tickers.

## The call (optional enrichment — not the default)

**Build the World Verdict from the Phase-2/3 records by default** (see "Default synthesis" below).
`get_assessment` is an *optional* deep-research cross-check, not the source of truth and not required
for a complete verdict. Fire it only when the operator wants an external-research pass and can absorb
the ~3-min latency. When you do fire it (**async, ~3 min** — fire it and don't block; per
`_parallax/parallax-conventions.md` §4), the prompt must:

- **Hand the per-assumption records over as fixed inputs.** The statuses were already established
  against live data in Phase 2/3 — the assessment *synthesizes* them, it does not re-derive or
  re-classify them. State this explicitly in the prompt (mirror the fixed-input instruction in
  `client-conditioning.md`), so the deep-research pass doesn't silently overwrite a Supported/
  Contradicted/Unconfirmed call with its own web-sourced view.
- **Stay client-invariant.** This is Pass 1. Do **not** mention any `client_profile` even if one
  was supplied — client conditioning is Phase 5's job, and mixing it in here corrupts the
  Pass-1/Pass-2 boundary the whole skill is built around. (If a profile was supplied, Phase 5 makes
  its own optional, separately-instructed re-call.)
- **Ask exactly three questions:** (1) which assumptions the thesis most depends on (load-bearing);
  (2) which are least supported by the current reads; (3) where it most likely fails first, and
  over what horizon — independent of who holds it.
- **Bound the response — but do not trust the bound.** Ask for **≤300 words, structured around the
  three questions, no asset-class literature review** — but treat this as a *hint the deep-research
  model empirically ignores*: it has returned ~2,000-word, multi-citation essays with their own
  section headers, and can **truncate mid-sentence**. Enforcement therefore lives on OUR side, not in
  the prompt: **never paste `get_assessment` output into the report raw.** Extract only its answers to
  the three questions, discard the literature review and headers, and compress into the World Verdict
  yourself. Treat the returned text as best-effort research notes, not finished copy.

## What Phase 4 emits

The **World Verdict**: what has to be true for the thesis to hold, which assumptions are
load-bearing, and the most likely failure with its sequence and horizon — all holder-independent.
This is also the ranking that Phase 5 re-weights (never overwrites) when a profile is supplied, so
keep it explicit and ordered.

**Lead the verdict with an `Assumption Strength` label** — `Weak` / `Mixed` / `Strong` — rating how
well the *load-bearing* assumptions are supported by the current Pass-1 reads:

- **Weak** — at least one high-criticality assumption is `Contradicted` or `Unconfirmed`.
- **Mixed** — the load-bearing set is partly Supported, partly Contradicted/Unconfirmed, with no
  single high-criticality failure dominating.
- **Strong** — the load-bearing set is `Supported`.

This label rates the **argument's evidential support, not the security** — it is explicitly **not** a
buy/sell/hold call, a PASS/FAIL grade, or a suitability verdict, and it never gates or short-circuits
the report (every section still runs regardless of the label). It is client-invariant: Phase 5
re-weights the underlying severity per holder but never restates this Pass-1 label. (See `SKILL.md`
Output Format for how it renders and the optional per-vulnerability tag.)

## Default synthesis (records-based) — also the fallback if `get_assessment` is skipped or times out

This is the **primary path**: the Pass-1 findings already live in the structured Phase-2/3 records,
so the World Verdict is fully synthesizable without any async call. Use it by default, and also
whenever `get_assessment` is skipped, errors, or times out past a reasonable wait — never block the
report on that call. Synthesize the verdict directly from the records:

- rank load-bearing assumptions by `criticality` × status severity (a **Contradicted**
  high-criticality assumption outranks an Unconfirmed one, which outranks a Supported one) and
  `base_severity`;
- name the earliest-firing / highest-severity break as the most-likely failure, using the
  `time_to_play_out` and `magnitude` already captured;
- note in **Confidence & Caveats** that the verdict was assembled without the assessment pass.

Never gate the whole report on this one async call.
