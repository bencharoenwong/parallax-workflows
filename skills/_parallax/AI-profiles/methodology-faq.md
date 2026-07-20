# AI Investor Profiles — Methodology FAQ

Compliance-facing FAQ on the named-investor framing used by the `parallax-ai-*` skill family. Sourced only from repo-public rationale — no internal review notes or non-public source material.

## Is this profile actually [Investor]'s view?

No. A profile is a **workflow specification** derived from a public source (peer-reviewed academic paper or the investor's own published book) that mechanically applies that source's documented methodology to current Parallax data. It is not an impersonation, an endorsement, or a prediction of what the named investor would do. See `README.md` "What a profile is."

## Why name a real investor at all?

The name identifies which public, citable methodology is being applied (e.g., "Buffett-style" points to Frazzini-Kabiller-Pedersen's factor decomposition of Berkshire's returns, not to Warren Buffett personally). Every output cites the source on every render, and framing is strictly third person — "Buffett-style," never "Buffett would say" or first-person impersonation. See `output-template.md` §5 (Verdict) and Rendering rule 5.

## What stops a profile from misrepresenting the investor?

The inclusion criteria in `README.md` require a public anchor (academic paper or the investor's own book — not interviews, tweets, or third-party characterizations), a mechanically specific workflow, and a defensibility test: if the named investor saw the profile, could they reasonably object that it misrepresents their approach? If yes, the profile does not ship.

## Has counsel reviewed the disclaimer language?

Counsel review is a continuous quality process, not a pre-invocation gate. The disclaimer in `output-template.md` §8 — "not financial advice," "AI-inferred... from publicly available information," "not endorsed by [Investor] or their representatives," "consult a qualified financial advisor" — is the runtime mitigation and is rendered verbatim on every output regardless of review status. A profile's `last_legal_review` frontmatter field tracks review completion internally; it is never rendered as "pending" in output (see `output-template.md` §7 render rule) — only a completed review date is surfaced, and only when one exists. See `README.md` "Legal posture."

## Where is the citation requirement enforced?

Every profile's `public_anchor.citation` is a REQUIRED frontmatter field (`profile-schema.md`), checked at dispatcher load time. A profile without a valid citation cannot render (`output-template.md` Rendering rule 3).
