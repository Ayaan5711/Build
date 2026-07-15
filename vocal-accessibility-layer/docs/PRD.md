# Product Requirements Document

## Vocal Accessibility Layer

| | |
|---|---|
| **Event** | AI Fridays Hackathon — Vocal Accessibility theme |
| **Standard** | PAS 901:2025 — Vocal Accessibility in System Design, Code of Practice |
| **Document status** | Draft — pre-match preparation |
| **Version** | 1.0 |
| **Date** | 2026-07-15 |
| **Owner** | Team (senior/team lead + members) |

---

## 1. Executive Summary

Standard voice interfaces are built and tested against fluent, single-language, quiet-room speech. They routinely fail the people who most need voice as an accessible input method: people who stutter or have speech-motor conditions, people with strong accents or non-native pronunciation, people who naturally code-switch between languages (e.g. Hindi-English), and people in loud or bandwidth-constrained environments.

The **Vocal Accessibility Layer (VAL)** is not a single-purpose voice app. It is a **middleware pipeline plus an extensible agent layer** that sits between raw speech input and any downstream task, normalizing and repairing that input, then routing it to the correct action — while staying transparent about what the AI did and safe about what it acts on. It is designed to be **use-case-agnostic by construction**: the actual hackathon problem statement is not known until match day, so the system is built so that a new use case is a single new file added to a `skills/` registry, with zero changes to the core pipeline.

This document specifies what the system must do, for whom, why, and how success is measured — both as a hackathon submission and as a reusable pattern.

---

## 2. Background & Context

### 2.1 The hackathon format

Per the event handbook, teams do not receive their build problem until match day. The week runs: a real-world AI problem is issued, Monday–Thursday is pre-match coaching, Friday is the live competition. Teams get lab laptops (Python 3.12.8, VS Code, Ollama, offline local SLMs) plus hosted model access via `genailab.tcs.in` (GPT-4o, GPT-4o-mini, DeepSeek-V3, DeepSeek-R1, Llama-3.3-70B, Whisper, text-embedding-3-large, among others), with an API key issued at the event. Each team presents a 5-minute live demo to a jury, judged on innovation, impact, working execution, and teamwork.

### 2.2 The assigned theme

The team lead distributed four reference materials ahead of the match:
1. A feature-exploration brief naming four concrete capabilities: **Speech Equalizer** (disfluency cleanup), **Mixed Language Recognition** (code-switched speech), **Conversational Accessibility** (dialogue over rigid menus), and **Transparency** (visible AI/confidence indicators).
2. Meeting slides summarizing **PAS 901:2025**, its five governing principles, and the categories of users voice systems typically exclude.
3. Reference links to prior art: Google Project Euphonia (personalized ASR for disordered speech), Microsoft Windows Voice Access (fluid dictation, custom word bias), and Apple Voice Control (confirmation feedback, numbered-grid fallback, spelling-mode correction).
4. The event handbook (rules, infra, timelines, evaluation criteria).

### 2.3 The standard: PAS 901:2025

PAS 901:2025, *"Vocal Accessibility in System Design – Code of Practice,"* defines five principles that any compliant voice system must embody:

| Principle | Requirement |
|---|---|
| **Understand** | Do not assume perfect speech. Accommodate speech impairments, accents, age-related changes, and natural variation. |
| **Simplify** | Favor natural conversation over rigid command menus. |
| **Adapt** | Always provide an alternative modality (voice ↔ text ↔ touch); never rely on a single channel. |
| **Assure** | Give clear confirmation, error recovery, and next-step guidance; never fail silently. |
| **Trust** | Be transparent about when AI, ASR, or translation is used, and privacy-respecting by design. |

This PRD treats PAS 901 compliance as a first-class requirement, not an afterthought — every functional requirement below is traceable to one of these five principles (see §12, Traceability Matrix).

---

## 3. Problem Statement

> Voice-enabled systems, as commonly built, silently exclude a large population of users — people with dysarthria, stutters, non-native accents, code-switched speech, or who are in noisy/low-bandwidth environments — because ASR and dialogue design assume fluent, monolingual, quiet-room input. The failure mode is usually silent or confusing (misrecognition, wrong action taken, no explanation), which erodes trust and abandons the very users voice interfaces should help most.

The team needs a system that (a) demonstrably narrows this gap on realistic inputs, (b) is provably standards-compliant against PAS 901, and (c) can absorb an **unknown, live-assigned use case** on match day without a rebuild.

---

## 4. Goals & Objectives

### 4.1 Hackathon goals (primary, time-boxed)
- G1 — Win/place well by demonstrating a working, live, PAS-901-mapped solution to whatever use case is assigned on match day.
- G2 — Demonstrate genuine architectural differentiation (agentic, extensible) versus single-purpose competitor apps.
- G3 — Deliver all required submission artifacts: source + README, notebook walkthrough, presentation deck, working demo.

### 4.2 Product goals (durable, beyond the hackathon)
- G4 — Prove the "accessibility layer" pattern: any voice app can sit downstream of this pipeline and inherit PAS 901 compliance for free.
- G5 — Prove real personalization improves outcomes measurably (word/intent accuracy) versus a generic pipeline.

### 4.3 Non-goals (explicitly out of scope)
- NG1 — Not building a specific vertical product (e.g. "a banking voice assistant") — the match-day use case determines the vertical; VAL is the substrate underneath it.
- NG2 — Not training or fine-tuning a custom ASR/LLM model — hackathon time and infra don't support this; personalization is achieved via prompt-time bias and retrieval, not model training.
- NG3 — Not implementing full multi-turn conversational memory across sessions beyond the correction/FAQ store — session-scoped dialogue state is sufficient for a 5-minute demo.
- NG4 — Not shipping production-grade auth, multi-tenant isolation, or scaled deployment — this is a hackathon MVP, single-user/single-session by design.

---

## 5. Target Users & Personas

| Persona | Description | Primary need |
|---|---|---|
| **Disfluent speaker** (e.g. stutters, dysarthria) | Speech contains repetitions, false starts, prolonged sounds | Accurate intent extraction despite non-fluent input |
| **Code-switching speaker** | Naturally mixes Hindi/Bengali/regional language with English mid-sentence | Correct intent without forced literal translation |
| **Accented / non-native speaker** | Regional accent causes ASR misrecognition (e.g. "Behala" → "Bengaluru") | Graceful correction/clarification instead of silent wrong action |
| **Noisy-environment user** | Background noise (transit, market, factory) degrades ASR confidence | System should recognize and communicate uncertainty rather than confidently act wrong |
| **Cognitively-loaded user** (elderly, memory/learning differences) | Struggles with multi-step menu trees | Conversational, single-question-at-a-time interaction |
| **Hackathon jury / evaluator** | Time-boxed observer, 5 minutes, needs to see innovation + working execution fast | Clear, visible proof points: live demo, transparency badges, extensibility proof |

---

## 6. Core User Stories

1. *As a user with a stutter*, when I say a disfluent sentence, the system should extract my actual intent without me having to repeat myself, and show me what it "heard" so I can trust it got it right.
2. *As a bilingual user*, when I mix languages mid-sentence, the system should understand my intent rather than mistranslating word-for-word or failing.
3. *As any user*, when the system isn't confident it understood me, it should ask a clarifying question in plain language instead of guessing and acting wrong, or presenting a rigid menu.
4. *As a returning user*, once I've corrected a mis-heard word/name once, the system should remember it and stop making the same mistake.
5. *As a user relying on transparency*, I should always be able to see when AI/ASR/translation was used and how confident the system is.
6. *As the development team*, when we receive the live match-day use case, we should be able to add support for it as a single new file, without touching the core pipeline, ASR, or safety logic.
7. *As the jury*, I should be able to see, live, that the system (a) fixes real disfluent/mixed-language input, (b) explains itself, (c) refuses to confidently act on low-confidence input, and (d) is trivially extensible.

---

## 7. Functional Requirements

Requirements are grouped by pipeline stage. Each has an ID, description, and PAS 901 principle it satisfies.

### 7.1 Foundation Layer — Automatic Speech Recognition (ASR)

| ID | Requirement | Principle |
|---|---|---|
| FR-1.1 | System shall transcribe spoken audio input to text via a swappable ASR backend (mock / local Whisper / hosted Whisper). | Understand |
| FR-1.2 | System shall capture per-segment or overall confidence score from the ASR stage and propagate it downstream. | Trust |
| FR-1.3 | System shall accept input via live microphone recording, uploaded audio file, or text (dev/testing fallback). | Adapt |

### 7.2 Foundation Layer — Speech Equalizer

| ID | Requirement | Principle |
|---|---|---|
| FR-2.1 | System shall detect and remove disfluency artifacts (repeated syllables, false starts, filler words) from the raw transcript, preserving original meaning, named entities, and numbers exactly. | Understand |
| FR-2.2 | System shall report whether a correction was made, and what changed, for transparency display. | Trust |
| FR-2.3 | System shall accept a per-user known-corrections map and apply it during cleanup (personalization), sourced from prior confirmed corrections. | Understand |

### 7.3 Foundation Layer — Normalizer (Intent & Language)

| ID | Requirement | Principle |
|---|---|---|
| FR-3.1 | System shall extract structured intent and entities from the cleaned transcript rather than performing literal word-for-word translation. | Understand |
| FR-3.2 | System shall detect and report which language(s) are present in a code-switched utterance. | Understand, Trust |

### 7.4 Agent Layer — Orchestrator

| ID | Requirement | Principle |
|---|---|---|
| FR-4.1 | System shall route a normalized request to exactly one registered skill based on intent, or request clarification if no skill confidently matches. | Simplify |
| FR-4.2 | System shall support adding a new skill via a single new file with zero modification to orchestrator, guardrail, or foundation-layer code. | Adapt |
| FR-4.3 | System shall ask a natural-language clarifying question (not a rigid numbered menu) when input is ambiguous. | Simplify |
| FR-4.4 | System shall fall through to a general-purpose acknowledgement skill rather than failing silently when no specific skill matches. | Assure |

### 7.5 Agent Layer — Guardrail

| ID | Requirement | Principle |
|---|---|---|
| FR-5.1 | System shall withhold/block execution of a skill's action when ASR confidence falls below a configurable threshold, and request user confirmation instead. | Assure |
| FR-5.2 | System shall report the reason an action was held or approved. | Trust |

### 7.6 Agent Layer — Memory

| ID | Requirement | Principle |
|---|---|---|
| FR-6.1 | System shall persist per-user word/name corrections and retrieve them for reuse in future sessions. | Understand |
| FR-6.2 | System shall support a retrievable FAQ/knowledge base via semantic search, used by relevant skills. | Simplify |
| FR-6.3 | System shall allow a user to explicitly teach it a correction via a UI control, with immediate effect on subsequent runs. | Understand, Trust |

### 7.7 Transparency Layer

| ID | Requirement | Principle |
|---|---|---|
| FR-7.1 | System shall display, for every interaction: ASR confidence, whether a correction was made, which language(s) were detected, which action/skill was invoked, and whether the guardrail approved or held the action. | Trust |

### 7.8 Response — Text-to-Speech (optional channel)

| ID | Requirement | Principle |
|---|---|---|
| FR-8.1 | System shall optionally render its response as synthesized speech in addition to on-screen text, satisfying the "text → voice" alternative-modality requirement. | Adapt |
| FR-8.2 | System shall degrade gracefully (text-only, explicit notice) if the TTS engine is unavailable, without failing the interaction. | Assure |

### 7.9 Skills (extensible capability layer)

| ID | Requirement | Principle |
|---|---|---|
| FR-9.1 | Each skill shall declare a name, description, parameter schema, and keyword hints, and implement a `run()` method returning a structured result. | Adapt |
| FR-9.2 | The skill registry shall auto-discover all valid skills in the skills directory at startup with no manual registration step. | Adapt |
| FR-9.3 | Shipped example skills shall include: FAQ lookup, schedule/reminder action, and a general-help fallback. | Simplify, Assure |

---

## 8. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | **Portability** | The entire system must run with zero network access and zero API keys (fully offline "mock" mode), so it is developable and testable before match-day credentials exist. |
| NFR-2 | **Config-driven backend switching** | Swapping between offline/local/hosted backends for ASR, LLM, embeddings, and TTS must require only environment-variable changes — no code changes. |
| NFR-3 | **Fail-fast configuration** | Misconfiguration (e.g. missing API key for a hosted backend) must raise an immediate, readable error at initialization, not an obscure failure mid-request. |
| NFR-4 | **Latency** | End-to-end pipeline (ASR → Equalizer → Normalizer → Orchestrator → Guardrail → Skill) should complete within a few seconds on hosted backends, suitable for live demo pacing. |
| NFR-5 | **Extensibility** | Adding a new skill must not require modifying any file outside `src/skills/`. This is a hard architectural constraint, not a guideline — verified by automated test. |
| NFR-6 | **Privacy** | No API keys or user audio/text may be committed to version control; `.env` must be git-ignored; secrets are never hardcoded. |
| NFR-7 | **Resilience** | Loss of hosted-model connectivity mid-demo must have a rehearsed, working fallback path (local Ollama backend) reachable via a single config change. |
| NFR-8 | **Testability** | Core pipeline logic must be covered by automated tests runnable without network access or a live model, so correctness is verifiable at any time. |

---

## 9. System Architecture

```
                    Audio / Text Input (mic, file upload, or text)
                                    │
                                    ▼
                 ┌────────────────────────────────────┐
                 │      FOUNDATION LAYER (fixed)        │
                 │                                       │
                 │  ASR  →  Speech Equalizer  →  Normalizer
                 │ (Whisper)  (disfluency fix)  (intent/lang) │
                 └──────────────────┬───────────────────┘
                                    │ normalized intent + entities + languages
                                    ▼
                 ┌────────────────────────────────────┐
                 │     AGENT LAYER (decision-making)    │
                 │                                       │
                 │   Orchestrator ◄──── Memory (Chroma)  │
                 │   (routes to a skill or clarifies)    │
                 │           │                            │
                 │           ▼                            │
                 │      Registered Skills                 │
                 │  (auto-discovered, pluggable)           │
                 │           │                            │
                 │           ▼                            │
                 │       Guardrail                         │
                 │ (confidence gate before acting)          │
                 └──────────────────┬───────────────────┘
                                    │
                                    ▼
                 ┌────────────────────────────────────┐
                 │        RESPONSE LAYER                │
                 │  Transparency badges + optional TTS   │
                 └────────────────────────────────────┘
```

**Design rationale:** the Foundation Layer is deterministic and use-case-agnostic — it never changes regardless of what problem is assigned. The Agent Layer is where match-day specificity lives, isolated entirely inside the Skills registry. This separation is the core architectural bet of this PRD: it converts "we don't know the use case yet" from a risk into a non-issue.

---

## 10. Technical Approach & Backend Matrix

Every external dependency (ASR, LLM, embeddings, TTS) is implemented behind a common interface with multiple interchangeable backends, selected via environment variables:

| Component | `mock` (offline dev) | `local` / `ollama` (offline, lab laptop) | `event` (match day) |
|---|---|---|---|
| ASR | Reads a paired transcript file | `faster-whisper` | `genailab.tcs.in` Whisper endpoint |
| LLM | Deterministic rule-based stand-in | Ollama (local SLM, e.g. Llama-3.2-3B) | `genailab.tcs.in` hosted model (e.g. DeepSeek-V3) |
| Embeddings | Hashed bag-of-words | — | `genailab.tcs.in` text-embedding-3-large |
| TTS | Off (no audio) | `espeak-ng` (offline) | — (no TTS model provided) |

The `mock` tier exists solely so the system is buildable and testable with zero credentials and zero network — it intentionally does not represent real language understanding, and is never used for the live demo.

**Personalization mechanism:** rather than fine-tuning a model (out of scope, NG2), personalization is achieved by (a) injecting a per-user known-corrections map into the Equalizer's prompt context, and (b) semantic retrieval of prior resolved ambiguities from a per-user memory store. This is a deliberate scope-appropriate substitute for the "personalized ASR model" approach used by prior art (Project Euphonia), chosen because it's achievable within hackathon time constraints while preserving the same user-facing benefit.

---

## 11. Data & Privacy Considerations

- No raw audio or transcripts are sent anywhere beyond the configured ASR/LLM backend for the current session; there is no third-party analytics or logging layer.
- Per-user correction and FAQ data is stored locally (Chroma, on-disk) — not transmitted elsewhere.
- API keys are supplied via `.env`, which is git-ignored; keys are never hardcoded, logged, printed, or included in commands that would place them in shell history.
- Confidence/transparency indicators are shown for every AI-mediated step, satisfying the "Trust" principle's disclosure requirement.

---

## 12. Traceability Matrix — PAS 901 Principles → Features

| PAS 901 Principle | Implementing Feature(s) |
|---|---|
| **Understand** | Speech Equalizer, per-user correction personalization, mixed-language intent extraction |
| **Simplify** | Conversational clarifying questions (Orchestrator), FAQ skill, no rigid command menus |
| **Adapt** | Multi-modal input (mic/file/text), skill extensibility, optional TTS output alongside text |
| **Assure** | Guardrail confidence gating, general-help fallback (never fails silently), clear error messages on misconfiguration |
| **Trust** | Transparency badges (confidence %, corrections made, languages detected, action taken, guardrail verdict) |

---

## 13. Success Metrics

### 13.1 Hackathon judging criteria (as defined by event rules)
| Criterion | How this system addresses it |
|---|---|
| Innovation | Agentic, pluggable architecture vs. single-purpose competitor apps; genuine safety/guardrail layer |
| Impact | Directly serves named excluded user groups (speech-impaired, accented, multilingual, noisy-environment) |
| Working execution | Fully wired, tested pipeline; live mic demo; automated extensibility proof |
| Teamwork | Clear module ownership boundaries (foundation / agent / skills / UI) enabling parallel work |

### 13.2 Product-level metrics (directional, for internal validation)
- **Correction accuracy uplift**: % of disfluent inputs where Equalizer output intent matches ground truth, with vs. without personalization.
- **Silent-failure rate**: % of interactions where the system takes no action and gives no explanation — target: 0% (by design, via FR-4.4).
- **Time-to-new-skill**: elapsed time to add and demo a new capability — target: single-digit minutes, one file.
- **Guardrail precision**: % of low-confidence interactions correctly held for confirmation vs. incorrectly blocked when they were actually fine.

---

## 14. Demo Plan (5-Minute Live Presentation)

| Time | Segment | What's shown |
|---|---|---|
| 0:00–0:30 | Problem framing | Who voice systems exclude today, and why |
| 0:30–2:00 | Foundation layer live | Speak a disfluent sentence into the mic → raw transcript shown → Equalizer output shown clean, correction badge lights up |
| 2:00–3:30 | Agent layer live | Speak a mixed-language request → structured intent shown → Orchestrator routes to the correct skill live |
| 3:30–4:30 | Safety moment | Trigger a deliberately low-confidence input → Guardrail holds the action and asks for confirmation instead of guessing |
| 4:30–5:00 | Extensibility + close | Show a new skill file being added live (or referenced), map the demo back to the five PAS 901 principles |

---

## 15. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Match-day use case doesn't fit any pre-built skill pattern | Medium | High | Core architecture is designed so a new skill is a single file; rehearse the "add a skill" workflow before the event |
| `genailab.tcs.in` endpoint is slow/unavailable during demo | Medium | High | Ollama local backend as a rehearsed one-line fallback |
| API key issued late / typo'd | Low | High | Fail-fast error messages catch this immediately during setup, not mid-demo |
| No real audio samples tested before event | Medium | Medium | Record real stutter/mixed-language/noisy clips as early as possible in lab time, before the live use case is issued |
| Team unfamiliar with codebase under time pressure | Medium | Medium | README documents the exact skill-addition workflow; module boundaries are intentionally clean for parallel onboarding |
| Over-scoping during limited match time | Medium | Medium | Foundation layer + 2 skills is the must-have baseline (§4.3 NG2–NG4 define firm scope boundaries) |

---

## 16. Open Questions / Dependencies

- OQ-1: Actual match-day use case — unknown until event, by design (see §2.1).
- OQ-2: Whether `espeak-ng` (TTS) is available/installable on the lab laptop image — not in the documented preinstalled software list; system degrades gracefully if absent.
- OQ-3: Whether lab laptops have outbound access to GitHub for pulling the repo, or whether the hackathon's shared drive is the only transfer path.
- OQ-4: Final confidence threshold tuning for the Guardrail — current default is a starting point, should be validated against real ASR confidence distributions once hosted Whisper is reachable.

---

## 17. Milestones

| Phase | Deliverable | Status |
|---|---|---|
| Pre-event | Foundation + Agent + Skills architecture scaffolded, tested offline | Complete |
| Pre-event | Live mic input, personalization loop, TTS, fallback skill wired | Complete |
| Pre-event | Real audio samples recorded and tested against local/hosted ASR | Pending (needs lab hardware) |
| Match day | Real backend connectivity verified (`event` + `ollama` fallback) | Pending (needs event API key) |
| Match day | New skill added for the assigned use case | Pending (use case unknown) |
| Match day | Live demo rehearsed end-to-end on lab wifi | Pending |
| Submission | README, notebook, deck, source finalized | In progress |

---

## 18. Appendix

### 18.1 Glossary
- **ASR** — Automatic Speech Recognition (speech-to-text).
- **Disfluency** — Involuntary speech interruptions: repetitions, prolongations, false starts.
- **Code-switching** — Mixing two or more languages within a single utterance.
- **Guardrail** — A verification step that withholds an action pending confirmation rather than executing on uncertain input.
- **Skill** — A self-contained, pluggable unit of capability the Orchestrator can route to.

### 18.2 Reference material
- PAS 901:2025, *Vocal Accessibility in System Design – Code of Practice* (internal slide summary).
- Google Project Euphonia — personalized ASR for atypical speech.
- Microsoft Windows Voice Access — fluid dictation, custom word bias.
- Apple Voice Control — confirmation feedback, numbered-grid and spelling-mode correction.
- AI Fridays Hackathon Handbook (event rules, infra, evaluation criteria).

### 18.3 Related project artifacts
- `README.md` — setup instructions and architecture summary.
- `notebooks/pipeline_demo.ipynb` — executable end-to-end walkthrough.
- `tests/test_pipeline_smoke.py` — automated verification, including the extensibility proof.
