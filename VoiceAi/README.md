# TCS iON Voice AI -- AI for Every Voice

Accessibility-first multimodal AI prototype for the AI Friday Hackathon 2026, theme *"Voice meets inclusion."* Full PRD: [`docs/PRD.md`](docs/PRD.md).

If a human can understand the speaker, AI should be able to understand them too.

## What this is

Not a single-purpose voice app -- a pipeline that treats voice as one modality among several (mic, camera/sign, text), detects real accessibility barriers (speech impairments, accents, code-mixed language, noise, sign interaction, cognitive load), and grounds every response in retrieved knowledge before presenting it for confirmation. The actual match-day use case isn't known yet; new domain behavior is added as one new file in `src/skills/`, with zero changes to the core pipeline (see "Adding a new skill" below).

## Architecture

Mirrors the PRD's Appendix A pipeline exactly, stage for stage:

```
Live Mic + Camera/Sign Input (app.py: st.audio_input / st.camera_input)
        │
        ▼
whisper_transcribe_stream()          interpret_sign_or_gesture()
        │                                     │
        └──────────────► merge_inputs() ◄─────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
detect_language_mix   analyze_accent_noise    detect_stammering
        │              _confidence                   │
        └─────────────────────┼─────────────────────┘
                              ▼
                    normalize_transcript()  ──►  generate_caption_summary
                              │                    _action_preview()
                              ▼
                    analyze_accessibility()   (structured barrier report)
                              │
                    simplify_instructions()   (if complex, FR-08)
                              │
                              ▼
                       extract_intent()  ◄── sign candidate_intent
                              │
                              ▼
                        rag_retrieve()  ◄── KnowledgeBase (PAS 901 + FAQs)
                              │
                     select_skill()  (domain-aware assistance, FR-20)
                              │
                              ▼
                  generate_grounded_response()
                              │
                  decide_recovery_or_confirmation()
                              │
                              ▼
                     render_dashboard()  (app.py)
```

Every stage in `src/pipeline.py` is a direct call to the module implementing that PRD pseudocode function -- reading `pipeline.py` next to Appendix A in the PRD should make the mapping obvious.

## Features implemented (traced to PRD requirement IDs)

- **Live mic input** (FR-01, FR-02) -- `st.audio_input`, Whisper ASR.
- **Live camera/gesture input** (FR-14) -- `st.camera_input` + real MediaPipe Hands landmark detection, classified against a predefined 5-gesture vocabulary (thumbs_up, open_palm, fist, pointing, peace), each mapped to a candidate intent. Deliberately scoped to match the PRD's own MVP definition ("prototype-level... predefined demo gestures"), not full sign-language recognition.
- **Disfluency detection + normalization** (FR-03, FR-04) -- rule-based detector (repeated syllables/words, fillers, pause markers) feeds an LLM cleanup pass that preserves meaning exactly.
- **Language mix detection** (FR-05) -- rule-based (native script + romanized Hindi/Bengali keyword heuristics), catches code-switching like "Kal meeting ache at 5 PM".
- **Accent/noise-aware confirmation** (FR-06) -- low ASR confidence triggers a reasoning-model clarifying question (e.g. "eleven" -> "Did you mean floor 11?").
- **Visual transcript + action preview** (FR-07, FR-17) -- caption/summary/action-preview generated for every interaction, never voice-only.
- **Step-by-step simplification** (FR-08) -- complex/IVR-style instructions broken into short confirmable steps.
- **Structured accessibility report** (FR-09) -- explicit barrier classification + support applied, framed as supportive assistance, never diagnostic (Appendix B).
- **Dashboard** (FR-10) -- `app.py`, all of the above rendered together.
- **Rich intent extraction** (FR-11) -- goal, action type, entities, constraints, urgency, missing information.
- **RAG-grounded responses** (FR-12, FR-13) -- Chroma-backed knowledge base seeded with PAS 901 principles + accessibility FAQs; retrieval happens on every turn, not as an optional add-on.
- **Multimodal fallback** (FR-15) -- voice / camera-sign / text, switchable per turn.
- **Clear feedback and recovery** (FR-16) -- confirm / correct / retry / switch_modality buttons that actually re-run the pipeline (Correct re-runs on your edited text and remembers the fix; Retry re-runs; Switch Modality cycles the input mode); never fails silently.
- **Privacy note in the UI, no raw audio/video persisted** (FR-18, NFR-06).
- **Domain-aware assistance** (FR-20) -- pluggable Skills (`faq_lookup`, `schedule_reminder`, `general_help`) feed into the grounded response rather than being the final answer themselves.
- **Cached fallback scenarios** (NFR-03) -- if every live backend call fails, the pipeline falls back to a precomputed output from `data/demo_scenarios.json` (the PRD's own 10 demo samples) instead of crashing the demo.
- **Cost tracking + budget cap** -- every hosted call's estimated USD is tracked and shown live in the sidebar; hosted calls are refused once estimated spend crosses `BUDGET_USD_CAP` (then falls back to cached scenarios), so a runaway loop can never drain the ~$25 event budget.
- **Personalization** -- confirmed corrections are remembered per user and auto-applied on future turns (not a PRD requirement, but compatible with FR-04 and low-cost to keep).

## Cost profiles -- one switch controls spend

The team runs on a fixed ~$25 total budget. Ollama models are already installed on the lab laptop (free); only Whisper ASR and (optionally) the final response call cost money. `PROFILE` in `.env` routes every stage to the cheapest capable backend:

| `PROFILE` | ASR | Cleanup / intent / reasoning / caption | Final response | Embeddings | Est. cost | Speed |
|---|---|---|---|---|---|---|
| `mock` (default) | mock | mock | mock | mock | $0 | instant |
| `local` | local faster-whisper | Ollama (free) | Ollama (free) | Ollama `gte-large` | **$0, offline** | **as fast as the laptop** ⚠ |
| `hybrid` | hosted Whisper | Ollama (free) | hosted `gpt-4o` | Ollama `gte-large` | ~cents/demo | limited by local Ollama |
| `fast` | hosted Whisper | hosted `gpt-4o-mini` | hosted `gpt-4o-mini` | hosted | ~cents/demo | **fastest (server GPUs)** |
| `hosted` | hosted | hosted | hosted `gpt-4o` | hosted | highest | fast |

The only unavoidable spend is Whisper ASR (~$0.006/min ≈ $0.50 for hundreds of demo utterances). The real budget risk is an accidental loop, which the budget cap prevents. Override any single stage with per-stage env vars (e.g. `LLM_BACKEND_RESPONSE=event` on an otherwise-local profile).

### Speed matters more than cost -- measure it

Cost is a solved problem (~cents); the binding constraint on a slow lab laptop is **latency**. Each turn makes 6–8 LLM calls, so slow local models can push a single turn to minutes. Two guards:

- The default reasoning model is **not** a reasoning model (`gpt-4o-mini`, not DeepSeek-R1) — a chain-of-thought model is the slowest thing in the pipeline and unnecessary for barrier classification / confirm-retry decisions. Opt back into DeepSeek-R1 via `GENAILAB_REASONING_MODEL` / `OLLAMA_REASONING_MODEL` only if you've measured it's fast enough.
- The app sidebar shows **per-stage latency for the last run**, with a red/amber/green verdict for live-demo suitability. Run once on the actual lab laptop in each profile and read the numbers — don't guess. If `local`/`hybrid` are slow, use `PROFILE=fast` (all hosted, server-GPU speed, still cents).

## Backends -- change config, not code

| Component | `mock` (default, offline) | `local` / `ollama` (lab laptop, offline) | `event` (match day) |
|---|---|---|---|
| ASR | reads a sibling `.txt` transcript | `faster-whisper` | `genailab.tcs.in` -- `azure/genailab-maas-whisper` |
| Vision/gesture | reads a sibling `.json` gesture label | MediaPipe Hands (real landmark detection) | -- (no hosted gesture model; local only) |
| LLM (cleanup/intent/caption) | deterministic rule-based stand-in | Ollama -- `llama-3.2-3b-it:latest` | `genailab.tcs.in` -- `azure/genailab-maas-gpt-4o-mini` |
| LLM (reasoning/recovery) | rule-based stand-in | Ollama -- `deepseek-r1:latest` | `genailab.tcs.in` -- `azure_ai/genailab-maas-DeepSeek-R1` |
| LLM (final response) | rule-based stand-in | Ollama -- `gemma-3-4b-it:latest` | `genailab.tcs.in` -- `azure/genailab-maas-gpt-4o` |
| Embeddings (RAG) | hashed bag-of-words | Ollama -- `gte-large:latest` | `genailab.tcs.in` -- `azure/genailab-maas-text-embedding-3-large` |
| TTS (optional, not a PRD focus) | off | `espeak-ng` | -- |

Ollama model names are confirmed against a real `ollama list` on the lab hardware -- always re-verify with `ollama list` on the machine you're actually on, tags don't match the upstream Ollama Hub.

Every `event`-backend class fails fast with a clear `RuntimeError` if `GENAILAB_API_KEY` is missing, instead of crashing deep inside a request.

## Running

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate.bat
pip install -r requirements.txt
cp .env.example .env    # edit backend selection / API key when available -- never commit .env
streamlit run app.py
```

Run the smoke tests (mock backends only, no network needed):

```bash
python -m pytest tests/ -v
```

## Adding a new skill (match-day workflow, FR-20)

```python
# src/skills/your_skill.py
from src.skills.base import Skill, SkillResult

class YourSkill(Skill):
    name = "your_skill"
    description = "What this does, for the router to match on."
    keywords = ["fallback", "keywords", "for", "the", "mock", "router"]
    parameters = {"some_param": "string"}

    def run(self, params, ctx):
        return SkillResult(True, "done", {})
```
`src/skills/__init__.py` auto-discovers it. Nothing else changes -- proven by `tests/test_pipeline_smoke.py::test_new_skill_can_be_added_without_touching_orchestrator`.

## Adding new RAG knowledge (match-day domain content)

Same pattern -- add entries to `src/knowledge/seed_data/accessibility_knowledge.json` (or call `KnowledgeBase.seed()` directly with real domain FAQs/workflow docs), no code changes needed.

## Project layout

```
app.py                          # Streamlit dashboard (PRD's 11-screen flow)
src/
  config.py                     # backend selection + model-per-role routing
  llm.py                        # LLM backend abstraction (mock/ollama/event)
  pipeline.py                   # wires the full Appendix A flow + NFR-03 fallback
  input/
    microphone.py                 # ASR (mock/local/event)
    vision.py                       # gesture capture (mock/MediaPipe)
    merge.py                          # merge_inputs()
  analysis/
    disfluency.py                    # detect_stammering() -- rule-based
    language.py                        # detect_language_mix() -- rule-based
    accent_noise.py                      # analyze_accent_noise_confidence()
    accessibility_report.py                # analyze_accessibility()
  transcript/
    normalize.py                           # normalize_transcript()
    visual_equivalent.py                     # generate_caption_summary_action_preview()
  understanding/
    intent.py                                 # extract_intent()
    simplify.py                                 # step-by-step simplification (FR-08)
  knowledge/
    rag.py                                       # KnowledgeBase, rag_retrieve()
    embeddings.py                                  # embedding backend abstraction
    personalization.py                               # per-user correction memory
    seed_data/accessibility_knowledge.json             # PAS 901 + FAQ content
  response/
    generate.py                                        # generate_grounded_response()
    recovery.py                                          # decide_recovery_or_confirmation()
  skills/                                                 # domain-aware assistance (FR-20)
    base.py, faq_lookup.py, schedule_reminder.py, general_help.py, __init__.py
data/
  sample_audio/                  # .txt transcript stand-ins until real clips exist
  sample_gestures/                # .json gesture-label stand-ins until real photos exist
  demo_scenarios.json              # cached fallback outputs for the PRD's 10 demo samples
notebooks/pipeline_demo.ipynb    # executable walkthrough, stage by stage
tests/test_pipeline_smoke.py     # 18 tests, every module, mock backends only
docs/PRD.md                      # the actual PRD, verbatim
```

## Known limitations (by design, for now)

- `mock` backends are plumbing stand-ins, not real understanding -- swap before the live demo.
- `data/sample_audio/` and `data/sample_gestures/` have placeholder stand-ins, not real recordings/photos -- capture real ones on the lab hardware before the event.
- `LocalWhisperBackend`, `MediaPipeVisionBackend`, and `OllamaLLMBackend` are written correctly but unverified in the dev sandbox this was built in (no route to Hugging Face for model weights, no camera/mic hardware, no running Ollama server there) -- verify each on the actual lab laptop.
- `st.camera_input`/`st.audio_input` capture a snapshot/recording per turn, not a continuous stream -- matches the PRD's own "predefined gesture capture" MVP scope; true continuous video would need `streamlit-webrtc`, out of scope.
- The mock LLM's cleanup pass is a regex heuristic, not real disfluency repair -- it's there so the pipeline is testable offline, not to demo quality. Use `LLM_BACKEND=ollama` or `event` for anything you'd actually show a judge.
