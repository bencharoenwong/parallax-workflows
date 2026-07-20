# Folder Mode — Inventory, Classification, Confirmation

Folder mode is NOT a blind iteration. The operator's folder may contain a mix of branded marketing material (newsletters, decks, brochures), voice-only material (memos, white papers, blog exports, transcripts), and irrelevant files (logos as standalone images, spreadsheets, raw data). The LLM must inventory and classify before extracting, and confirm with the operator when the folder is mixed or ambiguous.

## Step F-1 — Inventory the folder

List every file (recursive one level by default; ask the operator if deeper recursion is wanted for large structures). Capture filename, extension, and size. Group by type:

| Group | Extensions | Extraction path |
|---|---|---|
| **OOXML branded** | `.pptx`, `.docx` | `extract_from_pptx` / `extract_from_docx` — visual (theme XML) + voice corpus |
| **PDF branded** | `.pdf` | `extract_from_pdf` — visual (heuristic, low confidence) + voice corpus |
| **Text-only voice** | `.md`, `.markdown`, `.txt`, `.html`, `.htm`, `.rtf`, `.eml` | Read tool → strip markup if HTML/EML → append to supplementary voice corpus (no visual extraction) |
| **Visual asset** | `.png`, `.jpg`, `.jpeg`, `.svg`, `.ico`, `.webp` | Treat as candidate logo / brand asset; offer to use as logo path if naming or count suggests it |
| **Out of scope** | everything else (`.xlsx`, `.csv`, `.zip`, etc.) | Skip; report skip count to operator |

## Step F-2 — Classify each in-scope file by likely role

Read the filename + (for OOXML/PDF) sample the first few hundred chars of body text. Categorize:

| Role | Heuristic signals | Treatment |
|---|---|---|
| **Branded marketing** | filenames like `newsletter`, `quarterly`, `letter`, `brochure`, `pitch`, `deck`; cover slide / first page mentions client name + tagline | Extract visual + voice. High weight in voice corpus. |
| **Internal memo / whitepaper** | filenames like `memo`, `internal`, `notes`, `research`, `whitepaper`, `analysis`; body text is dense prose without marketing framing | Extract voice only. Skip visual (theme is generic Office default; would mislead). |
| **Client-policy / compliance** | filenames like `policy`, `compliance`, `disclosure`, `terms`; body text is legal boilerplate | Skip voice (legal language is a different register). Optionally pull explicit disclaimer text into the `disclaimers[]` section if found. |
| **Transcript / interview** | filenames like `transcript`, `interview`, `Q&A`, `call`; body text is conversational with multiple speakers | Voice only, but flag in notes — interview voice is unrepresentative of written voice. Lower-weight or ask operator. |
| **Ambiguous** | filename gives no signal AND first-page sample is inconclusive | Surface to operator: show filename, file size, first 200 chars of text, ask "Include this for visual + voice / voice only / skip?" |

## Step F-3 — Operator confirmation gate

Before extraction, present the inventory + classification:

```
Folder: <path>  (depth: 1)

In-scope files (8):
  ✓ newsletters/2026-Q1.pptx           — branded marketing  (visual + voice)
  ✓ newsletters/2026-Q2.pptx           — branded marketing  (visual + voice)
  ✓ letters/2026-jan-client-letter.docx — branded marketing  (visual + voice)
  ✓ research/macro-outlook-2026.docx   — internal memo      (voice only)
  ✓ research/credit-views.md            — text voice         (voice only)
  ? misc/agm-transcript.txt             — transcript         (ASK: include?)
  - misc/holdings-2026q1.xlsx           — out of scope       (skipped)
  - misc/portfolio-data.csv             — out of scope       (skipped)

Visual assets (2):
  ✓ assets/logo.png                     — candidate logo
  - assets/team-photo.jpg                — skipped (not logo-shaped naming)

Confirm? Or change classification for any file?
```

For ambiguous items (the `?` rows), ask one `AskUserQuestion` per file with the choices: include for visual + voice / include for voice only / skip.

## Step F-4 — Extract per classification

Iterate `classified_files`, dispatching `.pptx`/`.docx`/`.pdf` to their extractors for branded items, calling extractors then discarding visual fields for voice-only OOXML, and using the Read tool for text-only voice files. Merge OOXML drafts via `merge_drafts(drafts) + cross_validate_visual(drafts)` when there are 2+; for voice-only folders, seed an empty visual draft with `source.type = "folder-voice-only"`. Append voice-only corpus chunks to the merged draft's `voice_corpus` and re-truncate at the 3000-word cap.

> Full Python (F-4 loop + voice-only corpus append + 3000-word truncation): see `workflow-code.md` § Step 1 — Folder extraction.

## Background frameworks (cited inline so an LLM reading this skill has the grounding)

The voice extraction in Step 1.5 follows three named patterns documented in `DECISIONS.md` 2026-05-06:

- **Lago voice template** (`getlago/inside-lago-voice-skill`): 7 sections — Voice / Core Rules / Anti-Filler / Audience Adaptation / Channel Notes / Drafted-vs-Sent / Company Context. Calibration is via *Drafted vs Sent* example pairs.
- **Rezvani brand audit** (`alirezarezvani/claude-skills/marketing-skill/brand-guidelines`): 7-dimension audit (colors, fonts, logo, body text, imagery, tone, prohibited uses) and Tone Matrix (voice × context).
- **Genesys 4-phase extraction** (`matteotitta/genesys-claude-code-pmm-quickstart/.claude/skills/brand-guidelines`): Fetch & Detect → Extract Tokens → Visual Description → Generate Output → Review, with confidence scoring 0–5 and explicit gap documentation.

The skill blends them: Genesys 4-phase backbone → Rezvani schema as the output target → Lago voice section embedded inside.
