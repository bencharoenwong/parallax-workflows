# Step 1.5 — Voice Extraction Prompt & Self-Check

Drive voice extraction via in-skill prompting (no Python — this is LLM-native work). Read the corpus from `draft["voice_corpus"]["text"]` and prompt yourself with the structure below, then write the resulting fields into `draft["voice"]`.

> Skip / floor logic and the post-extraction draft writes stay in SKILL.md Step 1.5. This file is the prompt template + self-check detail.

## Voice extraction prompt structure (Lago 7-section + Rezvani tone matrix)

```
You are reading {N} words of body text from {client_name}'s recent client-facing
material ({source_descriptor}). Your task: extract their writing voice into a
structured profile that downstream skills will use to draft new material that
sounds like them.

Produce a YAML block with these fields. Be specific. "Write clearly" is useless;
"Cut any sentence that announces the smart thing before saying it" is actionable.

positioning: |  # 1-2 sentences: who they are, what they do, who they serve
tone:
  register: # one phrase, e.g., "formal-institutional", "warm-advisory", "technical-direct"
  primary_attributes: [3-5 attributes observed in the corpus]
  avoid_attributes:   [words/tones that would clearly NOT fit the corpus]
core_rules: [3-7 non-negotiables derived from observed patterns — e.g., "Never make
            forward-looking statements without a 'subject to' clause"]
anti_filler: [5+ phrase patterns to delete from AI drafts — e.g., "leverage our
              expertise", "best-in-class", "we believe that we believe"]
audience_adaptation:  # optional; only if the corpus shows clear differentiation
  - audience: ...
    notes: ...
channel_notes:        # optional; only if the corpus spans multiple channels
  - channel: ...
    notes: ...
company_context: |    # how they describe themselves, competitors, positioning
disclaimers:          # only include if explicit disclaimers appear in the corpus
  - jurisdiction: ...
    text: ...
    placement: ...
```

Set `draft["voice"]["enabled"] = True`, `draft["voice"]["source_corpus"]["word_count"] = N`, `draft["voice"]["source_corpus"]["documents"] = [list of source references]`, `draft["voice"]["source_corpus"]["confidence"] = your_self_assessed_confidence_0_to_1`.

## Self-check before writing into draft

- [ ] Did I derive `core_rules` and `anti_filler` from the corpus, or am I producing generic asset-management boilerplate? Generic = bad. Re-do.
- [ ] If I claim `tone.register` is "formal-institutional", can I quote 2 specific phrases from the corpus that prove it? If not, soften the claim.
- [ ] Did I leave any field as `""` or `[]` because the corpus genuinely doesn't show it, or because I didn't look? Be honest — empty is better than fabricated.

## Drafted-vs-Sent pairs are not auto-extractable

They require comparison between an AI draft and a human-edited version. Leave `drafted_vs_sent: []` in the initial extraction. Document in `voice.source_corpus.notes` that this should be populated incrementally as the client uses downstream skills (we save the draft + sent pair after each session).
