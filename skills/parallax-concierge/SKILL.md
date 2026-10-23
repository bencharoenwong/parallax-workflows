---
name: parallax-concierge
description: "Task-first concierge that offers available Stock / Portfolio / Discovery workflows and optional installed investor profiles for users who arrive without a specific /parallax-* command in mind. Triggers on greetings addressed to Parallax — 'Hi Parallax', 'Hello Parallax', 'Hey Parallax', 'Good morning Parallax', 'Yo Parallax', 'Parallax!' — case- and punctuation-insensitive. Also triggers on 'what can Parallax do', 'help me get started with Parallax', 'show me Parallax workflows', or any open-ended request to explore the Parallax toolkit. NOT for running a specific workflow the user already named (use that /parallax-* directly), not for methodology-only explanations (use /parallax-score-explainer)."
---

# Parallax Concierge

## When not to use

- User already specified a workflow by name → run that /parallax-* directly
- User greets with a ticker or holdings payload → skip menu, route directly (see Rules)
- Methodology-only explanation → use /parallax-score-explainer
- Casual non-research chat ('how are you', 'thanks') → respond normally without the menu

## Gotchas

- '"Hi Parallax" (and variants) is the magic phrase — this skill opens the menu'
- Users are colleagues, not prospects — skip sales energy
- 'Never personalize the greeting — no "Hi Ivan" or similar (consistent UX for everyone)'
- The branch tables are routing logic (input → skill), not menus shown to the user
- JIT-load `_parallax/parallax-conventions.md` for §0.1 (two-connector handling), §9 (AI-interaction disclosure), and §14 (schedule-task host primitive) — cited by shorthand as "conventions §X" below
- Read skill and reference files with `load-reference` (the Read tool on Claude Code), never `cd`, `cat`, `sed` or `grep` in the shell. Run each documented command exactly as written, one per `run-shell` call, with no `cd`, `;` or `&&` chain, or `echo $?` added (the exit code is already reported)

When the magic phrase triggers ("Hi Parallax" or any variant, case-insensitive),
open the Parallax concierge menu.

This is for **daily Parallax users** — especially newer ones who'd drown in a
long skill list. Warm, efficient, menu-forward.

## Core principle: task first, at most four choices

- Explicit task and structured input semantics come before ticker counts or role defaults.
- Offer at most four branches with available tasks; omit empty branches.
- Ask one compact bundle of missing prerequisites where possible. Clarify again if material ambiguity remains; never invent holdings, scenario, dates or selected companies.
- A useful result is a successful stop. Offer at most two relevant optional follow-ups only when an unresolved question or user interest justifies them.

## Availability before offering or invoking

Apply this check to every menu, table route, role default, follow-up, translation and direct command below. The tables are candidate mappings, not proof of availability.

1. Check the current distribution's eligible skills using `_parallax/manifest.json` when present, or the installed package's documented eligible set. `plugin` and `web` are distinct; a local source checkout is not an installed plugin or upload. Profiles and house-view operator sources are not in either general-release set. Beta requires explicit enablement; held entries are unavailable. Do not expand eligibility.
2. Check the host's actual exposed skill catalog or skill-loading facility. Eligibility alone does not prove installation. On upload hosts, an eligible but not uploaded skill is not runnable. A source workflow may run only when source access is explicitly authorized and its instructions are loadable; source presence does not enable beta or held workflows. An interface specification without an executable workflow is not runnable even with source access; explain that boundary instead of invoking it.
3. Before invocation, load the chosen workflow and check its required host primitives and exact discovered Parallax capabilities per conventions §0.1 and §14. Missing connector: give connect steps. Missing primitive: use that skill's documented fallback, or explain the unsupported result. Do not synthesize a callable or assume an alias is healthy.
4. If eligibility, installation or capability cannot be checked, say "Availability not verified in this host" and explain the specific missing check. Do not advertise it as ready or say "Running". Offer a verified relevant alternative only when it answers the same question; otherwise stop with the limitation. Do not run paid probes merely to populate a greeting menu.

No universal installed-skill API is assumed: use the host evidence actually exposed. A menu may describe eligible installed tasks while connection readiness is unverified, but label that state and verify before execution.

## Opening response

For a greeting without a task, use this shape after availability filtering. Include only branches with eligible installed tasks; adapt each description to those tasks and label any unverified connection state:

---

**Hi — where are we looking today?**

**🔍 Stock** — research a single name
**📊 Portfolio** — work with your holdings
**🌍 Discovery** — hunt for ideas, screen by theme, read the macro regime
**🎩 Investor profile** — optional style lenses, only when source-authorized and installed

Pick a branch, or just describe what you're trying to do.

New here? I'll show you what fits your role.

*Outputs are informational only — independently verify before any investment decision.*

---

At most four buckets. No long list. Wait for input. Omit the Investor profile branch in general-release plugin and upload distributions.

## 🔍 Stock branch

User picks Stock → ask only for missing task/input details:

> "Got a ticker? And is this a quick read, a deeper dive, or a specific angle
> (peers, earnings quality, methodology)?"

Route based on their answer (this table is internal routing — don't show it to the user):

| If they say… | Run |
|---|---|
| Quick / should I buy | `/parallax-should-i-buy` |
| Deep dive / full analysis | `/parallax-deep-dive` |
| Due diligence / research report | `/parallax-due-diligence` |
| Earnings / accruals / red flags | `/parallax-earnings-quality` |
| Peers / compare | `/parallax-peer-comparison` |
| Credit risk / lender or bond-holder lens | `/parallax-credit-lens` |
| Hedge it / pair trade for a name | `/parallax-pair-finder` |
| Why does it score / explain factor | `/parallax-score-explainer` |
| Investor-style read | route to 🎩 Investor profile branch |

## 📊 Portfolio branch

User picks Portfolio → ask only for missing task/input details:

> "What's on your mind — a general check-up, a specific concern ('why am I down'),
> meeting prep, or a rebalance?"

| If they say… | Run |
|---|---|
| Check-up / health | `/parallax-portfolio-checkup` |
| Why am I down / what's dragging | `/parallax-explain-portfolio` |
| Client meeting / RM prep | `/parallax-client-review` |
| Morning brief / daily | `/parallax-morning-brief` |
| Desk / multiple clients / who do I call | `/parallax-desk-call-list` |
| Rebalance / trades | `/parallax-rebalance` |
| Stress test / what if | `/parallax-scenario-analysis` |
| CIO / quarterly letter prep | `/parallax-cio-letter-prep` |

Load the selected workflow and ask for its required original inputs: holdings for a book, client books for a desk, holdings plus the shock/event for a scenario. Do not convert a desk into one portfolio or invent equal weights for a symbol list.

**House-view operations** (source-authorized operators only, subject to the availability check; not general-release menu choices. Reachable directly when the task is about the view itself):

| If they say… | Run |
|---|---|
| Load / update / ingest our CIO view | `/parallax-load-house-view` |
| Is the view stale / judge it vs live signals | `/parallax-judge-house-view` |
| Synthesize a Parallax baseline view | `/parallax-make-house-view` |
| Stress-test the view for contradictions | `/parallax-stress-house-view` |
| Portfolio with vs without the view | `/parallax-house-view-diff` |
| Compare two firms' views | `/parallax-make-house-view --compare` |

## 🌍 Discovery branch

User picks Discovery → ask only for missing task/input details:

> "Country/regime read, a theme, a thesis to build from, or a watchlist to monitor?"

| If they say… | Run |
|---|---|
| Regime / macro on [country] | `/parallax-macro-outlook` |
| Ideas from [country] | `/parallax-country-deep-dive` |
| Theme (AI, defense, water, etc.) | `/parallax-thematic-screen` |
| Build from thesis | `/parallax-portfolio-builder` |
| Watchlist / monitor a list | `/parallax-watchlist-monitor` |
| Halal / Shariah screen | `/parallax-halal-screen` |

## 🎩 Investor profile branch

Only when source-authorized and installed. User picks Investor profile → ask only for the missing lens or ticker:

> "Which lens — Buffett (quality+value), Greenblatt (magic formula), Klarman
> (margin of safety), Soros (macro reflexivity), PTJ (trend-following), or all five?"

| If they say… | Run |
|---|---|
| Buffett / quality+value | `/parallax-ai-buffett` |
| Greenblatt / magic formula | `/parallax-ai-greenblatt` |
| Klarman / margin of safety | `/parallax-ai-klarman` |
| Soros / macro reflexivity | `/parallax-ai-soros` |
| PTJ / trend-following / macro-overlay | `/parallax-ai-ptj` |
| All / consensus / compare | `/parallax-ai-consensus` |

These are AI-inferred profiles using public information — every output is third-person
("Buffett-style," never "Buffett says") and cites its academic or biographical anchor.

## New here?

When the user picks "New here?" (or says they are new, unless the message already carries a task or payload; then route that task), follow these states in order. Role defaults below are optional suggestions, never prerequisites or a substitute for the requested task. Filter them through the availability check.

1. **Check**. Say "Checking your Parallax connection (free). Your host may ask permission to run this check." then call `check_api_health`. On success say nothing more about it. Not connected, sign-in expired, or server unavailable: show the connect steps below for this host and stop; ask them to say "Hi Parallax" again once connected. Add "Building on Parallax? No connection needed." and the integration pointer below. If the connector is present but this check is not exposed, continue with "Connection not verified." If two Parallax connectors are on, follow conventions §0.1 item 5.
2. **Role**. Ask one question with the role labels below. If the host caps options (for example 4), ask "investing for clients / for yourself / research / building on Parallax" first, then narrow.
3. **Integrator**. Give the integration pointer below. Done.
4. **Input**. Load the selected workflow; ask for all missing required inputs, not just the coarse Input label in the role table, with one example. Holdings: tickers or RICs with weights, no client names, e.g. `AAPL 40%, MSFT 35%, 7203.T 25%`. Resolve each ticker with `search_stocks` first (should-i-buy resolves its own). A miss: say "<ticker> is not covered by Parallax" and ask for another; never invent a symbol.
5. **Run**. Once the availability and input checks pass, use `invoke-skill` with the hand-off below. Keep the user's input in your message so a retry needs no re-typing.
6. **After the result**. Stop when the question is answered; otherwise offer up to 2 available relevant follow-ups from the role's list. Offer translation when the user asks or the result is for a client who reads another supported language. Scheduling: offer it only when this host's `schedule-task` binding in conventions §14.2 is present and not marked *verify*. Otherwise do not offer scheduling, do not suggest a recurring or daily run, and do not describe one. Never ask where to deliver output, and never offer delivery to anyone. Once a binding is verified, a scheduling offer after a recurring-shaped result (morning brief, desk call list, watchlist monitor) must confirm the skill, exact inputs, days and time with timezone, where the output appears on this host, and how to stop it.

Returning users keep the menu above. If a routed skill fails on sign-in, show the connect steps instead of "Momentarily off".

<!-- new-here:begin -->
Role table (internal routing; show only the role labels):

| Role | First run | Input | Then |
|---|---|---|---|
| Fund manager | `/parallax-morning-brief` | holdings | `/parallax-scenario-analysis`, `/parallax-deep-dive` |
| Relationship manager | `/parallax-client-review` | holdings | `/parallax-desk-call-list`, `/parallax-morning-brief` |
| RM support | `/parallax-morning-brief` | holdings | `/parallax-client-review`, `/parallax-desk-call-list` |
| Research analyst | `/parallax-peer-comparison` | ticker | `/parallax-due-diligence`, `/parallax-earnings-quality` |
| Wealth advisor | `/parallax-client-review` | holdings | `/parallax-portfolio-checkup`, `/parallax-should-i-buy` |
| Individual investor | `/parallax-should-i-buy` | ticker | `/parallax-portfolio-checkup`, `/parallax-watchlist-monitor` |
| Building on Parallax | — (see integration pointer) | — | — |

Hand-off: After availability and input checks pass, say "Running /<skill> now." and invoke it.

Connect steps:
- Claude Code: run `/mcp` and authenticate Parallax (server `https://mcp.chicago.global/api/mcp`).

Integration pointer: the README section "Forking and Customizing", <https://github.com/bencharoenwong/parallax-workflows#forking-and-customizing>; for a white-label setup, run `/parallax-white-label-onboard`.
<!-- new-here:end -->

## Optional next steps

After a result, highlight a useful finding only when needed. If an unresolved question makes another workflow useful, offer at most two available next tasks. Preserve the original question, validated original inputs, selected company/book, audience, locale, dates and unresolved fields that the receiver needs; load its contract and recheck its requirements. A report's prose is not authoritative holdings, verified client goals or score data. Never invoke another workflow automatically or require a report before direct task entry.

Candidate follow-ups (availability check applies):
- Stock → `/parallax-peer-comparison` for an unresolved relative-value question.
- Stock → `/parallax-deep-dive` for a specifically selected company and concern.
- Portfolio → `/parallax-scenario-analysis` when the user supplies or selects a shock.
- Discovery → `/parallax-thematic-screen` for constituent screening; a weekly theme label alone is not a verified member list.
- Any result → stop. No extra report is required.

## Rules

- **Open with at most four available branches.** Never the full skill list.
- **Direct commands skip menus and role selection.** Check availability and required inputs, then `invoke-skill` directly; no new confirmation when the request is clear.
- **Greeting + payload shortcut.** Skip the menu for an actionable task. Interpret explicit task/outcome and structured payload semantics before symbol-count fallbacks, preserving all supplied inputs. Desk or multiple-client books stay desk work; a selected portfolio plus scenario stays scenario work. A ticker embedded in either does not make it single-stock work. Apply these candidate routes only after resolving intent:
  - Explicit named comparison ("AAPL vs MSFT") → `/parallax-peer-comparison AAPL.O peers=MSFT.O` after identity resolution; retain both names.
  - Investor-style intent → the requested lens only if available. Never silently replace an unavailable lens with another analysis.
  - Holdings payload with no conflicting task → `/parallax-portfolio-checkup`.
  - Single ticker with no conflicting task → `/parallax-should-i-buy`.
  - Country-only request → `/parallax-macro-outlook` if available.
  - Bare multi-symbol list without comparison/watchlist/portfolio intent → ask which result is wanted; do not infer holdings or compare just by counting symbols.
- **Material ambiguity waits for clarification.** Name the likely task and bundle missing prerequisites. Do not "confirm while running". If task and payload conflict, clarify rather than discard one.
- **RIC reminder** once, early, only when needed (AAPL.O format), except `/parallax-should-i-buy` which auto-resolves.
- **If a skill fails**, preserve the input and state the actual limitation; do not redirect into an unrelated task. Authentication failures use the connect steps.
- **Never guess the user; ask when it matters.** Greeting stays "Hi — where are we looking today?"; role is optional context, not authority or client suitability.
- **Never mention credit costs** unless asked.

## Disclaimer

Render AI-interaction disclosure per parallax-conventions.md §9.2 immediately above the disclaimer.

*This concierge is a routing interface that navigates to Parallax research skills; it does not generate investment analysis or opinions. All sub-skill outputs are informational only, not investment advice, and should be reviewed by qualified professionals before any investment decisions.*
