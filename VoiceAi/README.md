# TCS iON Voice AI -- AI for Every Voice

Accessibility-first multimodal AI prototype for the AI Friday Hackathon 2026, theme *"Voice meets inclusion."* Full PRD: [`docs/PRD.md`](docs/PRD.md).

If a human can understand the speaker, AI should be able to understand them too.

## What this is

Not a single-purpose voice app -- a pipeline that treats voice as one modality among several (mic, camera/sign, text), detects real accessibility barriers (speech impairments, accents, code-mixed language, noise, sign interaction, cognitive load), and grounds every response in retrieved knowledge before presenting it for confirmation. New domain behavior is added as one new file in `src/skills/`, with zero changes to the core pipeline (see "Adding a new skill" below).

**Match-day use case: "Simplified Voice Interaction for Users with Cognitive Challenges."** The pipeline now supports genuine multi-turn, paced, slot-filling dialogue (e.g. setting a reminder by answering one plain question at a time, not one complex sentence) with real backend persistence, not just a stub. See [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) (what it does, for a demo presenter), [`docs/DIALOGUE_MANAGEMENT.md`](docs/DIALOGUE_MANAGEMENT.md) (how it works, for engineers), and [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) (a concrete walkthrough).

**Concrete domain: a classroom assistant.** Education is one of the domains the problem statement names directly. Simple factual lookups ("what classes do I have today," "when's my next class," "show absent students," "what did Priya score in the midterm") answer in one turn against **real, updatable data** -- a SQLite store (`src/integrations/student_records.py`) for students/attendance/marks, and a real date-aware schedule lookup (`src/integrations/class_schedule.py` -- genuinely computes "today"/"tomorrow" against the real date, not a static guess). "Create an assignment for Chapter 5" and "mark Rohan absent" are the domain's paced-dialogue examples -- both reuse the exact same guided-dialogue mechanism as the reminder flow. A teacher's real spreadsheets (student roster, attendance, marks) and PDFs (policies, handbooks) drop into `data/incoming/` and get ingested with one command -- see "Loading real classroom data" below.

## Interaction redesign -- conversational, not a pipeline console

The original UI (both the HTML/JS frontend and Streamlit) exposed the pipeline
directly: separate clicks to enable mic/camera, start recording, stop
recording, click Run, then read a wall of numbered technical sections before
a final confirm click. Real user feedback on it: "it feels very mechanical...
like I'm operating a pipeline, not talking to an assistant." For a
voice-accessibility product, that's a real defect, not a cosmetic one -- the
whole point is that the voice should control the interface, not the other
way around.

What changed (HTML/JS frontend, `frontend/`):
- **One tap starts a turn.** A single "talk orb" replaces the old
  enable/start/stop/Run sequence. Recording auto-stops on its own via a
  client-side RMS silence detector (`frontend/app.js`), then auto-submits --
  no separate Run click anywhere in the app now.
- **The silence window is deliberately generous (5s) with a 25s hard cap,**
  not a snappy ChatGPT-Voice-style cutoff. This app exists partly to handle
  speech with long pauses and repeated sounds (FR-03); an aggressive
  auto-stop would clip off exactly the speech pattern it's supposed to
  support. A second tap always stops it manually too.
- **Gesture capture collapses to one action:** "Use a gesture instead" opens
  the camera and auto-captures on a 3-2-1 countdown -- no separate
  enable/capture/Run clicks.
- **Technical detail is opt-in, not the default view.** Original transcript,
  barriers, intent JSON, RAG snippets, and the agent trace still exist
  (PRD's own NFR-08 transparency requirement), just behind a "Show what's
  happening under the hood" toggle instead of being the first thing shown.
  The cost/latency/skills panel moved the same way, behind a small ⚙ toggle.
- **Status narration is humanized** ("Understanding what you said…" instead
  of stage names) and voice-driven recovery (auto-listening for a spoken
  "yes"/"retry"/"switch" reply) is now **on by default** instead of opt-in --
  matching "voice controls the interface," with an easy one-tap opt-out.
- Two real bugs were found while verifying this in a real browser (Playwright
  + Chromium's fake-media-device flags, driving actual `MediaRecorder`/
  `getUserMedia` capture, not just unit tests) -- see "Known limitations"
  below for both.

Streamlit (`app.py`) got the same philosophy applied within its real
platform constraints: `st.audio_input`/`st.camera_input` always show their
own native record/stop controls (a Streamlit limitation, not something this
codebase can remove without a custom component, out of scope tonight) --
what moved is the separate "Run" click (capture now auto-triggers the
pipeline) and the wall of numbered sections (now a confirmation-first
summary with the full technical detail collapsed into one expander).

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
                     run_agent()  ── multi-step loop ──┐
                       plan → call skill → observe ─────┘ (domain tools, FR-20)
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
- **Agentic flow** (FR-20) -- a real multi-step agent loop (`src/agent/agent.py`): the LLM plans, calls pluggable Skills as *tools*, observes each result, and decides to call another tool, ask a clarifying question, or finish. Not one-shot routing. The full reasoning trace (thought → action → observation per step) is shown in the dashboard and captured in `agent_result`. A step cap (`AGENT_MAX_STEPS`, default 3) and a "never call the same tool twice" loop guard bound latency/cost. Skills (`faq_lookup`, `schedule_reminder`, `general_help`) are the tools; adding a new one is still one new file.
- **Cached fallback scenarios** (NFR-03) -- if every live backend call fails, the pipeline falls back to a precomputed output from `data/demo_scenarios.json` (the PRD's own 10 demo samples) instead of crashing the demo.
- **Multilingual, output side, not just detection** -- `detect_language_mix()` was always real (rule-based, catches native script + romanized Hindi/Bengali), but the response used to silently default to English regardless. `generate_grounded_response()` now passes the detected language(s) into the prompt and instructs the LLM to reply in the same language(s) the user used. Voice output follows: `speechSynthesis` sets `utterance.lang`/`voice` to match (`en`→`en-US`, `hi`→`hi-IN`, `bn`→`bn-IN`), falling back to the browser default if no matching voice is installed.
- **Voice-driven recovery loop** (FR-16, completing the loop for a speak-and-listen-only user) -- opt-in toggle in the HTML/JS UI ("🎙 Voice-driven confirmation"): after the response is spoken, auto-listens for a short reply and matches it against confirm/correct/retry/switch_modality via keyword matching (`src/response/recovery_intent.py`, `POST /api/recovery-intent`) -- deliberately rule-based, not an LLM call, so it's instant and works identically on every backend profile. Falls back silently to the on-screen buttons if nothing matches or the mic is unavailable/denied -- never guesses, never blocks the manual path.
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

Setup (same for both UIs below):

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate.bat
pip install -r requirements.txt
cp .env.example .env    # edit backend selection / API key when available -- never commit .env
```

**Two UIs, same unmodified pipeline underneath -- pick either, or run both:**

```bash
# Option A: Streamlit (original, zero extra moving parts)
streamlit run app.py

# Option B: custom HTML/CSS/JS + FastAPI (full visual control)
uvicorn server:app --host 0.0.0.0 --port 8000
# then open http://localhost:8000
```

The FastAPI option (`server.py` + `frontend/`) is a thin API wrapper around the exact same `src/pipeline.py` -- no pipeline logic lives in `server.py`, only request/response plumbing, so both UIs stay behaviorally identical and share every backend/cost/latency feature.

**Voice in this UI:** input is real microphone audio (`MediaRecorder`) sent to our own Whisper pipeline -- deliberately *not* the browser's built-in speech recognition, which would auto-clean disfluent speech before the Speech Equalizer ever sees it and defeat the disfluency-detection story. Output is the browser's built-in `speechSynthesis` (free, zero backend dependency, works offline once the page loads) -- auto-speaks the final response or clarifying question after every run, with a "Replay voice response" button as a manual fallback if a browser blocks autoplay. Push-to-talk mic buttons (🎙) are also wired onto the Correct and Personalize fields, not just the main input.

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

Same pattern -- add entries to `src/knowledge/seed_data/accessibility_knowledge.json` (or call `KnowledgeBase.seed()` directly with real domain FAQs/workflow docs), no code changes needed. This is for genuinely unstructured/narrative content (policy text, FAQs) -- see the next section for structured data like attendance and marks, which deliberately does **not** go through RAG.

## Loading real classroom data (Excel + PDF, one command)

A real school hands over spreadsheets (student roster, attendance, marks) and PDFs (handbooks, policies), not a clean schema. The importer is built to cope with that without being told column names in advance:

```bash
# 1. Drop files in (any mix of .xlsx/.xls/.pdf, any reasonable header names):
#    data/incoming/student_master.xlsx, attendance_july.xlsx, marks_midterm.xlsx,
#    faculty_class_schedule.xlsx, attendance_policy.pdf, ...
# 2. Run the importer:
python scripts/import_classroom_data.py
```

**Why this needs two different storage engines, not one:** attendance/marks/schedule are exact, row-level, and *change over time* (someone corrects a mark, a student is marked absent today) -- that needs real database semantics (upsert-not-duplicate, exact JOIN queries), not semantic-similarity retrieval. RAG/embeddings can't correctly answer "who is absent **today**" (a computation over live rows), only "what does the policy say about absences" (a genuinely unstructured document). So: structured/exact/updatable data -> SQLite (`src/integrations/student_records.py`, `.student_records.db`); unstructured/narrative content (PDFs) -> the existing RAG knowledge base (`src/integrations/pdf_import.py`).

**How the importer copes with real-world spreadsheets** (`src/integrations/excel_import.py`):
- **File type is auto-detected** from the filename first (`attendance_july.xlsx` -> attendance), falling back to which columns are present (a `Date`+`Status` pair implies attendance even with an unrecognized filename).
- **Column headers are fuzzy-matched** against a synonym list per field (e.g. a `name` column matches `"Student Name"`, `"Full Name"`, `"Name"`, ...) -- you don't need to rename anything in the source file.
- **Every import prints an `ImportReport`**: which columns it mapped to what, which it couldn't place, how many rows imported vs. skipped, and why (unrecognized status value, unparseable score, missing required column, ...). **Always read this after an import** -- it never silently guesses; anything it can't confidently map is reported, not dropped quietly.
- **Re-running an import updates, not duplicates** -- attendance/marks upsert on `(student, date)`/`(student, subject, exam)`, so a corrected spreadsheet or a re-export just overwrites the old values.
- **Live voice updates work the same store**: "mark Rohan absent" (a paced `mark_attendance` dialogue) writes to the exact same SQLite tables a bulk Excel re-import would, so a query turn afterward ("who's absent today") sees it immediately -- either update path is safe to mix with the other.

**Privacy:** real student names/attendance/marks are genuine PII. `data/incoming/*` (except its own `README.md`) and `.student_records.db` are gitignored -- source files and the resulting database never get committed. Only synthetic data is used in tests and fixtures.

**Not yet done:** this has only been verified against synthetic fixtures generated in code (see `tests/test_excel_import.py`), not the team's actual spreadsheet files -- run the importer against the real files and read the printed `ImportReport` before the demo to confirm the fuzzy header matching handles their real column names.

## Project layout

```
app.py                          # Streamlit dashboard (PRD's 11-screen flow)
server.py                       # FastAPI backend for the HTML/CSS/JS UI -- thin wrapper, no pipeline logic
frontend/
  index.html                      # HTML/CSS/JS dashboard (same 11-screen flow as app.py)
  style.css                         # accessible-by-default styling (contrast, focus states)
  app.js                              # mic/camera capture, API calls, rendering, speechSynthesis TTS
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
    dialogue_state.py                             # guided, paced multi-turn slot-filling (cognitive-load use case)
  knowledge/
    rag.py                                       # KnowledgeBase, rag_retrieve()
    embeddings.py                                  # embedding backend abstraction
    personalization.py                               # per-user correction memory
    seed_data/accessibility_knowledge.json             # PAS 901 + FAQ content
    seed_data/classroom_knowledge.json                   # classroom domain content (absent students, etc.)
  response/
    generate.py                                        # generate_grounded_response()
    recovery.py                                          # decide_recovery_or_confirmation()
  agent/
    agent.py                                              # multi-step agent loop (run_agent) + trace + dialogue continuation
  skills/                                                 # the agent's tools (FR-20)
    base.py, faq_lookup.py, schedule_reminder.py, list_reminders.py, class_schedule.py, assignment.py, list_assignments.py, mark_attendance.py, attendance_query.py, marks_query.py, general_help.py, __init__.py
  integrations/
    reminders_store.py                                    # real SQLite-backed scheduling persistence
    assignments_store.py                                    # real SQLite-backed assignment persistence
    class_schedule.py                                         # real date-aware weekly timetable lookups (not RAG)
    student_records.py                                          # real SQLite-backed students/attendance/marks store
    excel_import.py                                               # fuzzy-matching Excel importer -> student_records/schedule
    pdf_import.py                                                   # PDF text extraction + chunking -> RAG knowledge base
scripts/
  import_classroom_data.py       # CLI: import every file in data/incoming/ (see "Loading real classroom data")
data/
  sample_audio/                  # .txt transcript stand-ins until real clips exist
  sample_gestures/                # .json gesture-label stand-ins until real photos exist
  demo_scenarios.json              # cached fallback outputs for the PRD's 10 demo samples
  class_schedule.json                # seeded weekly class timetable for the classroom domain
  incoming/                            # drop real Excel/PDF files here (gitignored -- real student PII)
notebooks/pipeline_demo.ipynb    # executable walkthrough, stage by stage
tests/                            # 168 tests total: pipeline, agent, dialogue state, reminders, assignments, class schedule, student records, Excel/PDF import, classroom query skills, cost/profiles, server API
docs/
  PRD.md                          # the actual PRD, verbatim
  STATUS_VS_PRD.md                  # FR/NFR trace against the code
  USER_GUIDE.md                       # adaptive/paced interaction, for a demo presenter
  DIALOGUE_MANAGEMENT.md                # slot-filling dialogue architecture, for engineers
  DEMO_SCRIPT.md                          # concrete walkthrough of the cognitive-friendly flow
```

## Known limitations (by design, for now)

- `mock` backends are plumbing stand-ins, not real understanding -- swap before the live demo. **Important:** `ASR_BACKEND=mock` (the `mock` profile's default) can only "transcribe" the pre-made fixture files in `data/sample_audio/` (it reads a matching `.txt` sidecar) -- it cannot handle a real microphone recording or uploaded clip. If you record real audio while on `ASR_BACKEND=mock`, you'll get a clear placeholder message telling you to switch to `local` or `event`, instead of a real transcript. (Earlier builds silently substituted an unrelated cached demo scenario here instead -- that was a real bug, fixed.) Use `ASR_BACKEND=local` (or the `local`/`fast`/`hybrid`/`hosted` profiles) to actually transcribe live speech.
- `data/sample_audio/` and `data/sample_gestures/` have placeholder stand-ins, not real recordings/photos -- capture real ones on the lab hardware before the event.
- `LocalWhisperBackend` is now **confirmed working on real hardware** -- live-tested transcribing a real mic recording (`ASR_BACKEND=local`, `faster-whisper-base`, downloaded from Hugging Face on first run). One real data point from that test: transcription alone took ~13.8s on that laptop's CPU. That's slow for a 5-minute live demo -- if the lab laptop is similarly slow, either try `WHISPER_LOCAL_MODEL=tiny` (faster, less accurate) or use `PROFILE=fast`/`hybrid` (hosted Whisper) for the actual demo instead of `local`. Always check the latency panel, don't assume. `OllamaLLMBackend` is still unverified (no Ollama server in this dev sandbox) -- verify it on the lab laptop too.
- **Two real bugs found and fixed against the actual `genailab.tcs.in` gateway** (`PROFILE=hosted`), found via a real `ReadTimeout` on the lab network: (1) `httpx.Client()` defaults to a 5-second timeout on every request phase when none is given -- far too short for real hosted Whisper transcription or LLM inference. None of the three genailab clients (ASR, LLM, embeddings) set one explicitly. Fixed by adding `config.GENAILAB_TIMEOUT_S` (default 60s, override via env var) to all three. (2) Separately, the LLM backend (`GenAILabLLMBackend`) was hitting the *wrong URL entirely* -- it delegated request-building to `langchain_openai`'s `ChatOpenAI`, which constructs `{base_url}/chat/completions` with an `Authorization: Bearer` header, but a direct curl test against the gateway's own API docs proved the actual working route is `/litellm/openai/deployments/<url-encoded-model>/chat/completions` with an `x-litellm-api-key` header instead -- a completely different path/auth convention (genailab.tcs.in is a LiteLLM proxy in front of Azure OpenAI deployments). Rewritten to call the endpoint directly via `httpx` with the proven request shape; `langchain-openai` is no longer a dependency. The ASR (`/v1/audio/transcriptions`) and embeddings (`/v1/embeddings`) endpoints were left unchanged -- the embeddings call was directly confirmed working (`200 OK`) in a real server log using that exact path/header shape, so there's no evidence that convention is wrong for those two, only that it was never given enough time to respond. Regression-tested offline (`tests/test_genailab_backends.py`) by intercepting the outgoing request before it's sent and asserting on the exact URL/headers/timeout -- **not verified against the real gateway from this sandbox** (no network route to `genailab.tcs.in` here); re-test on the lab machine. **Update, confirmed via a real lab-network log with the stage-entry/exit diagnostic logging:** the mystery ~60-77s hang mentioned above was ASR transcription itself timing out at the 60s ceiling -- not a hidden later stage, as originally suspected. It happened twice in the same run (both the main pipeline's ASR call and the separate `/api/recovery-intent` ASR call), consistent with the shared hackathon gateway sometimes needing more than 60s under concurrent load from other teams. Fixed by giving ASR its own longer timeout (`config.GENAILAB_ASR_TIMEOUT_S`, default 120s, overridable via env) separate from the 60s used for text LLM calls -- the *connect* timeout stays short (10s) so a genuinely dead endpoint still fails fast instead of always waiting the full ceiling. Still worth watching on the lab network: if 120s still isn't enough during the actual event, bump `GENAILAB_ASR_TIMEOUT_S` further rather than guessing at a root cause on our end -- there's no evidence of a client-side bug here, only gateway load.
- **`MediaPipeVisionBackend` fixed, found via live testing:** mediapipe removed the old `mp.solutions.hands` "Solutions" API entirely as of the version on PyPI when this was tested (0.10.35) -- it was replaced by the newer `mediapipe.tasks` `HandLandmarker` API, which needs a downloadable `.task` model bundle instead of being bundled in the package. Real symptom on the lab-testing laptop: every camera-modality turn silently fell back to the cached demo scenario, logged as `module 'mediapipe' has no attribute 'solutions'`. Fixed by rewriting `MediaPipeVisionBackend` (`src/input/vision.py`) onto the Tasks API, with the model bundle auto-downloaded to `.mediapipe_models/` on first use (needs real internet once, then cached -- same shape as the Whisper model download). Verified in this sandbox: real `HandLandmarker` detection running end-to-end through `/api/run` on a real image with no crash (confirmed `used_fallback_cache: False`), plus `tests/test_mediapipe_vision.py` (skips cleanly if graphics libs/internet aren't available, so `pytest tests/` still always passes). **Confirmed working on a real webcam, too**: live-tested on the personal Windows laptop with an actual open-palm gesture -- correctly classified and mapped to the `request_help` intent (`confidence=75%`, `fallback=False`, ~1.2s), no crash. Only that one gesture has been exercised on real hardware so far; still worth a quick spot-check of thumbs_up/fist/pointing/peace before the event, but the pipeline itself (model download, detection, classification, end-to-end wiring) is proven.
- **`.env` gotcha, found via live testing:** don't put a value and a trailing `# comment` on the same line when the value is meant to be blank (e.g. `VISION_BACKEND=   # mock | local`) -- `python-dotenv` does NOT strip the comment in that case; it treats the entire comment as the literal value. `.env.example` was fixed to put comments on their own line instead, and `config.py` now validates every `*_BACKEND`/`PROFILE` value and ignores (with a clear warning printed at startup) anything that isn't a recognized option, so a stray comment or typo can no longer silently break backend routing.
- `st.camera_input`/`st.audio_input` capture a snapshot/recording per turn, not a continuous stream -- matches the PRD's own "predefined gesture capture" MVP scope; true continuous video would need `streamlit-webrtc`, out of scope.
- The mock LLM's cleanup pass is a regex heuristic, not real disfluency repair -- it's there so the pipeline is testable offline, not to demo quality. Use `LLM_BACKEND=ollama` or `event` for anything you'd actually show a judge.
- The HTML/CSS/JS frontend (`frontend/` + `server.py`) is verified via FastAPI's `TestClient`, a live `uvicorn` boot with `curl`, **and now a real headless-Chromium session (Playwright, launched with `--use-fake-device-for-media-stream`/`--use-fake-ui-for-media-stream` and a real WAV fed to `--use-file-for-fake-audio-capture`)** driving actual `MediaRecorder`/`getUserMedia` capture end to end -- tap-to-talk, real-audio silence auto-stop, auto-submit, gesture auto-capture, and the details/sidebar toggles all confirmed working in an actual browser, not just via API calls. What's still **not** verified: real human speech/gestures and `speechSynthesis` autoplay/voice-pack behavior, since this sandbox has no real mic/camera/speakers. If `speechSynthesis` gets blocked by an autoplay policy, the "Replay voice response" button is the manual fallback.
- **Two real bugs found via that Playwright verification, both fixed:** (1) `.result-section { display: block; }` in `style.css` was unconditionally overriding the `hidden` attribute on the technical-details panel -- meaning it was visibly rendering (empty) on page load even before any interaction, which likely contributed to the original "feels like a monitor/log screen" complaint. Removed; visibility is now purely driven by the `hidden` attribute and the "Show details" toggle. (2) `MockVisionBackend.interpret()` had the exact same failure shape the mock ASR backend used to have: it raised `FileNotFoundError` for a real captured gesture image (no sidecar `.json` fixture), which the pipeline's NFR-03 resilience layer silently caught and replaced with an unrelated cached demo scenario -- meaning the redesigned one-tap gesture flow would have silently shown a fake "book an appointment" response for *any* real gesture captured under `VISION_BACKEND=mock` (the default profile's setting). Fixed the same way the ASR bug was: return an honest "no gesture detected" result instead of raising. Both have regression tests (`test_gesture_mock_backend_real_capture_gives_no_gesture_not_a_crash` in `tests/test_pipeline_smoke.py`).
- Language-matched replies depend on the LLM backend actually following the instruction -- only meaningful with `LLM_BACKEND=ollama` or `event`; the `mock` backend always ignores it (plumbing stub, documented above). Language-matched TTS voice depends on the OS/browser having a Hindi/Bengali voice pack installed -- if not, `speechSynthesis` falls back to the default voice and pronunciation of non-Latin-script text won't be accurate. Neither of these is something the code can fix; both are real hardware/OS constraints, verify on the lab machine.
- Voice-driven recovery's keyword phrase lists (`src/response/recovery_intent.py`) are a first pass, not user-tested -- tune the phrase lists if real users phrase confirm/retry/correct/switch differently than expected. It's rule-based specifically so this is a five-minute edit, not a prompt-engineering exercise.
- **Guided-dialogue slot-filling** (`src/understanding/dialogue_state.py`) is in-memory, single-server-process, single-demo-user scope, matching `server.py`'s existing `_USER_ID = "demo-user"` convention -- a server restart loses an in-progress question (deliberately; see `docs/DIALOGUE_MANAGEMENT.md`) but never a completed reminder (that's persisted separately in `.reminders.db`). Not built for multiple concurrent users.
- **Another mock-backend bug found and fixed while building the above:** `MockLLMBackend._response()` (`src/llm.py`) silently ignored `skill_output` entirely and always echoed `"Understood: {transcript}"`, even when a skill had already produced a real result -- meaning a completed reminder under the free/offline `mock` profile looked like nothing happened. Fixed to surface `skill_output` when present, matching what the response system prompt already instructs a real LLM to do.
- **Real classroom data (Excel/PDF importer, `src/integrations/excel_import.py` + `pdf_import.py`) is untested against the team's actual files.** The fuzzy column-matching and file-type detection were built and verified against synthetic fixtures generated in test code (deliberately nonstandard headers like `"Roll No"`, `"Present/Absent"`, `"Class/Section"`), not the real spreadsheets -- run `python scripts/import_classroom_data.py` against the real files in `data/incoming/` and read the printed `ImportReport` before the demo; it will tell you exactly which columns it couldn't map instead of guessing. A related routing bug was found and fixed while building this: the mock LLM router used to always match `faq_lookup`'s bare "what"/"how" keywords before a more specific skill's own keywords (first-match-wins), so "what did Priya score" would always route to the FAQ skill instead of `marks_query`. Fixed by switching to longest-matching-keyword-wins routing (`src/llm.py`'s `MockLLMBackend._agent_step`), which generalizes correctly to any future skill with natural question-phrased keywords.
