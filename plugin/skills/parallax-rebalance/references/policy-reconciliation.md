# Batch C2 — Policy reconciliation (S3)

JIT-loaded by `parallax-rebalance/SKILL.md` at Step 0 item 7 when `policy=` was supplied; Batch C2 (inside Step 4) runs it. The heading numbers below (step 1 payload, step 2 solve, step 3 routing) are the ones the orchestrator cites.

JIT-load `_parallax/client-policy/policy-loader.md`. Run the S0–S2 adaptation
first (`adaptation.py`, same contract as `parallax-client-review`), then the
S3 optimizer — a real Bash tool call, never prose arithmetic:

1. **Assemble the payload** (JSON file via a private `mktemp` path):
   - `basis`: the basis the adaptation result normalized to (`sleeve`); every
     weight and band edge in the payload must share it. Declared explicitly,
     never assumed.
   - `holdings[*].symbol` / `weight`: the current holdings in that basis.
   - `holdings[*].coefficient`: the tilt-weighted composite score — the
     holding's aggregated composite score (loader.md §3b) × its region tilt
     multiplier × its sector tilt multiplier (loader.md §3; each 1.0 with no
     active view). Every non-excluded holding needs one; a holding whose score
     is unavailable must be either excluded from the solve or given an
     explicit disclosed treatment — the solver rejects a missing coefficient
     rather than guessing. **The explicit disclosed treatment for a
     profile-derived score** (Batch A coverage-gap fallback, `get_peer_snapshot`
     row): before using it as a coefficient here, cross-check it against the
     holding's latest `get_score_analysis` row. If the two agree — same
     composite field, same 1–10 scale — the coefficient is same-scale by
     construction and enters the solve with the profile-derived disclosure. If
     they disagree, or only one source returned, do NOT solve with a guessed
     value: exclude the holding from the solve instead, using the
     excluded-holding disclosure named above (mixed-scale coefficients change
     the LP optimum itself, so a guessed value is never an acceptable
     substitute). State the same-scale verification outcome for every
     profile-derived holding in Policy Reconciliation.
   - `excludes`: the subset of `tilts.excludes` that matches a held symbol,
     plus held symbols matching a parsed "no <sector>" exclusion. The solver
     hard-rejects an excludes entry that matches no holding, so intersect
     BEFORE assembling the payload; a `tilts.excludes` entry naming a symbol
     the client does not hold is vacuously satisfied — list it in the Policy
     Reconciliation section as "excluded, not held" rather than passing it.
   - `position_cap`: the most restrictive of the parsed "max N% per position"
     cap and the adaptation result's `max_position_weight` — `min()` of the
     two, never the looser. Both are sleeve-basis fractions; convert before
     comparing if the parsed cap was stated on a different basis. Name which
     bound applied in Mandate Constraints Applied. A mandate cap below a
     segment floor carried by a single holding is jointly infeasible by
     construction — the solver returns `infeasible` with the smallest
     violation and the step-3 routing below applies unchanged.
   - `bands`: one entry per adaptation segment carrying band edges —
     `{dimension, key, symbols: [members by the holding→region/sector
     mapping], min, max}`.
   - `turnover_penalty`: omit (the module's disclosed default) unless the
     mandate states one.
2. **Solve**: `python3 "<skill-dir>/../_parallax/client-policy/reconcile.py"
   --input "$PAYLOAD"` and parse the JSON result.
3. **Route by `status` — the trade list is gate-shaped (conventions §4.0)**:
   - `optimal`: the result's `target_weights`/`trades` become the Target
     Weights in Trade Recommendations. Carry `binding`, `turnover_penalty` +
     `penalty_source`, `basis`, `calibration_status`, and `total_turnover`
     into the Policy Reconciliation section. Render `total_turnover`
     prominently: it is **two-sided** turnover — the sum of the absolute
     weight changes across every holding, so a one-way trade of 20 points
     contributes 40. State the two-sided basis on the same line, or the
     figure reads as twice the trading it represents. State with it that the
     turnover penalty is `heuristic_phase0` and uncalibrated, so the figure is
     a disclosure and not a threshold verdict — do not render an advisory
     turnover limit, a "high/low" judgement, or any comparison against a
     target. If `basis` is `sleeve` and the report renders total-portfolio
     weights, convert visibly (state the equity sleeve weight used) — a
     sleeve delta read as a total delta is a wrong trade size, and the same
     visible conversion applies to `total_turnover` when rendered in
     total-portfolio terms.
   - **Single-name floor disclosure.** For every payload band with a `min`
     above 0 whose `symbols` list holds exactly one member, render one line
     in Policy Reconciliation naming the segment, the floor, and the single
     holding that carries it: a segment floor met by one position forces
     that position to at least the floor, whatever its score. Add "and the
     floor is binding in this solve" when `binding` also carries
     `band:<dimension>:<key>:min` for that band. A symbol that is the sole
     member of two floored bands gets two lines, each naming its own
     segment, floor, and binding state. Derived from the payload the skill
     assembled and the result it received; no solver change.
   - `infeasible`: render the `violations` table (the exact smallest
     relaxations) and NO optimizer targets — no target weights, no trade
     list, not even labeled "suggested". Never silently relax. Trade
     Recommendations fall back to the flag-based path, labeled "not
     policy-reconciled — constraints jointly infeasible, see Policy
     Reconciliation". When the smallest-violation table names a bound on a
     holding that is the sole member of a floored band, state that the
     mandate is internally contradictory (cap against floor) — distinct from
     ordinary infeasibility.
   - `conflict`: render each named conflict (e.g. an exclude against a user
     minimum) for human decision — precedence collisions are never
     auto-resolved (design guardrail 5). Same fallback labeling as
     `infeasible`.
   - `solver_unavailable` / `invalid_input` / `solver_error`: the
     reconciliation verdict is **UNVERIFIED** — state the reason from the
     result, render no optimizer targets, and label the flag-based fallback
     "not policy-checked". Never substitute model judgement for the solve.
