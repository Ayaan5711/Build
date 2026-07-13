# Vocal Accessibility Layer

A pluggable pipeline + agent layer for building voice interactions that work
for people with speech impairments, accents, mixed-language speech, and
noisy environments — built for the AI Fridays hackathon (Vocal Accessibility
theme, PAS 901:2025).

## Why this design

The actual match-day use case isn't known until the event. Instead of
building one narrow app, this is a **layer**: a fixed foundation pipeline
(ASR → cleanup → intent) feeding an **agent orchestrator** that routes to
pluggable **skills**. A new use case on match day = one new file in
`src/skills/`, with zero changes to the foundation, orchestrator, or
guardrail. `tests/test_pipeline_smoke.py::test_new_skill_can_be_added_without_touching_orchestrator`
proves this claim.

## Architecture

```
Audio/Text Input
      │
      ▼
Foundation layer (deterministic)
  ASR (Whisper)  →  Speech Equalizer (LLM cleanup)  →  Normalizer (intent/language extraction)
                              │
                              ▼
                    Agent Orchestrator (tool-calling / routing)
                 ◄── Memory (Chroma: per-user corrections + FAQ)
                              │
                    routes to one of the registered skills
                              │
                              ▼
                    Guardrail (confidence gate before acting)
                              │
                              ▼
                    Transparency layer (confidence/correction/routing badges) + Response
```

Maps directly to PAS 901's five principles: Equalizer/Normalizer =
**Understand**, Orchestrator's conversational routing = **Simplify**, the
skill/fallback design = **Adapt**, Guardrail = **Assure**, Transparency
layer = **Trust**.

## Backends (dev vs match day)

Nothing here requires the real hackathon API key to develop against. Every
external dependency is swappable via env vars (see `.env.example`):

| Component | `mock` (default, offline) | `local` / `ollama` (offline, lab laptops) | `event` (match day) |
|---|---|---|---|
| ASR | reads a sibling `.txt` transcript | `faster-whisper` | `genailab.tcs.in` Whisper endpoint |
| LLM | deterministic rule-based stand-in | Ollama (`llama3.2:3b` etc.) | `genailab.tcs.in` (DeepSeek-V3, GPT-4o, ...) |
| Embeddings | hashed bag-of-words | — | `genailab.tcs.in` `text-embedding-3-large` |

The `mock` backends exist only to make the pipeline testable with zero
network/model access — they are not real language understanding. Switch
`ASR_BACKEND` / `LLM_BACKEND` / `EMBED_BACKEND` (see `.env.example`) once you
have real access.

## Running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit backend selection / API key when available
streamlit run app.py
```

Run the smoke tests (mock backends only, no network needed):

```bash
python -m pytest tests/ -v
```

## Adding a new skill (match-day workflow)

1. Create `src/skills/your_skill.py`:
   ```python
   from src.skills.base import Skill, SkillResult

   class YourSkill(Skill):
       name = "your_skill"
       description = "What this does, for the orchestrator to route on."
       keywords = ["fallback", "keywords", "for", "the", "mock", "router"]
       parameters = {"some_param": "string"}

       def run(self, params, memory):
           return SkillResult(True, "done", {})
   ```
2. That's it — `src/skills/__init__.py` auto-discovers it. No changes
   needed anywhere else.

## Project layout

```
app.py                      # Streamlit UI, wires the pipeline together
src/
  config.py                 # backend selection + all tunables
  llm.py                    # LLM backend abstraction (mock/ollama/event)
  foundation/
    asr.py                  # ASR backend abstraction (mock/local/event)
    equalizer.py             # disfluency cleanup
    normalizer.py             # intent + language extraction
  agent/
    orchestrator.py          # routes to a skill via the LLM
    guardrail.py              # confidence gate before acting
    memory.py                  # Chroma-backed corrections + FAQ retrieval
  skills/
    base.py                   # Skill interface
    faq_lookup.py, schedule_reminder.py   # example skills
    __init__.py                # auto-registry
  transparency.py            # confidence/correction/routing badges
notebooks/pipeline_demo.ipynb # walkthrough notebook (submission requirement)
data/sample_audio/          # test clips — currently .txt stand-ins, replace
                             # with real recordings before the event
tests/test_pipeline_smoke.py # end-to-end wiring test on mock backends
```

## Known limitations (by design, for now)

- `mock` backends are plumbing stand-ins, not real speech/language
  understanding — swap before the live demo.
- `data/sample_audio/` currently has a `.txt` placeholder instead of real
  audio; record actual stutter / mixed-language / noisy clips before the
  event and switch `ASR_BACKEND` to `local` or `event`.
- Guardrail/orchestrator prompts are a first pass — tune them once running
  against a real LLM backend, responses from `mock` are intentionally
  simplistic.
