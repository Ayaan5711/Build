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
skill/fallback design + text↔voice alternatives = **Adapt**, Guardrail =
**Assure**, Transparency layer = **Trust**.

## Features (all working end-to-end today)

- **Live microphone input** — `st.audio_input` in the Streamlit app records
  directly in the browser, no plugins needed. File upload and a text box
  (dev/testing) are also available as input modes.
- **Speech Equalizer** — cleans disfluent/stuttered transcripts.
- **Personalization loop** — confirm a correction once ("So-soumesh" →
  "Soumesh") via the "Personalize" panel in the app, and it's applied
  automatically on every future run, for this user, without retraining
  anything.
- **Mixed-language / intent extraction** — structured intent + detected
  languages, not word-for-word translation.
- **Agentic routing with a real fallback** — the orchestrator routes to a
  skill; if nothing matches, it falls through to `general_help` instead of
  failing silently (PAS 901 "Assure": always give feedback).
- **Guardrail** — blocks/holds an action when ASR confidence is low and
  asks for confirmation instead of guessing.
- **Transparency badges** — confidence %, what was corrected, what
  languages were detected, what action was taken.
- **Spoken response (optional)** — offline text-to-speech via `espeak-ng`
  reads the result back, so the interaction can be voice-in/voice-out, not
  just voice-in/text-out. Degrades gracefully (skips audio, shows a clear
  error) if `espeak-ng` isn't installed rather than crashing the app.

## Backends (dev vs match day)

Nothing here requires the real hackathon API key to develop against. Every
external dependency is swappable via env vars (see `.env.example`) —
**change the config, the same app runs against real models with no code
changes**:

| Component | `mock` (default, offline) | `local` / `ollama` (offline, lab laptops) | `event` (match day) |
|---|---|---|---|
| ASR | reads a sibling `.txt` transcript | `faster-whisper` | `genailab.tcs.in` — `azure/genailab-maas-whisper` |
| LLM | deterministic rule-based stand-in | Ollama — `llama-3.2-3b-it:latest` (confirmed via `ollama list` on the lab hardware; also available: `qwen-2.5.1-coder-it`, `gemma-3-4b-it`, `deepseek-r1`) | `genailab.tcs.in` — `azure/genailab-maas-gpt-4o-mini` default |
| Embeddings | hashed bag-of-words | Ollama — `gte-large:latest` | `genailab.tcs.in` — `azure/genailab-maas-text-embedding-3-large` |
| TTS | off (no audio) | `espeak-ng` (offline) | — (no TTS model in the provided list) |

Ollama model names are confirmed against the actual `ollama list` output on
the lab machines — they don't match the upstream Ollama Hub tags (it's
`llama-3.2-3b-it:latest`, not `llama3.2:3b`). Always sanity-check with
`ollama list` on the machine you're on before assuming a tag exists.

The `mock` backends exist only to make the pipeline testable with zero
network/model access — they are not real language understanding. Switch
`ASR_BACKEND` / `LLM_BACKEND` / `EMBED_BACKEND` / `TTS_BACKEND` (see
`.env.example`) once you have real access. Every `event`-backend class
fails fast with a clear `RuntimeError` if `GENAILAB_API_KEY` is missing,
instead of crashing deep inside a request — the app catches this and shows
it as a readable error instead of a stack trace.

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
app.py                      # Streamlit UI: mic/file/text input, personalize
                             # panel, pipeline run, transparency badges, TTS
src/
  config.py                 # backend selection + all tunables
  llm.py                    # LLM backend abstraction (mock/ollama/event)
  foundation/
    asr.py                  # ASR backend abstraction (mock/local/event)
    equalizer.py             # disfluency cleanup + personalization
    normalizer.py             # intent + language extraction
    tts.py                    # TTS backend abstraction (mock/local)
  agent/
    orchestrator.py          # routes to a skill via the LLM, general_help fallback
    guardrail.py              # confidence gate before acting
    memory.py                  # Chroma-backed corrections + FAQ retrieval
  skills/
    base.py                   # Skill interface
    faq_lookup.py, schedule_reminder.py, general_help.py   # example skills
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
- `espeak-ng` (TTS) wasn't in the hackathon's preinstalled software list —
  if it's not available on the lab laptop, leave `TTS_BACKEND=mock` and the
  app runs exactly the same, just without spoken responses.
- `LocalWhisperBackend` (faster-whisper) and `OllamaLLMBackend` are written
  but unverified in this dev environment specifically — it has no route to
  Hugging Face (to download Whisper weights) or a running Ollama server.
  Verify these once on a machine that has both.
