# TCS iON Voice AI — "AI for Every Voice"

Product Requirements Document for AI Friday Hackathon 2026

| | |
|---|---|
| **Hackathon Theme** | Voice meets inclusion |
| **Event Date** | 17 July 2026 |
| **Prepared For** | Team of 5 members |
| **Prepared By** | TCS iON Voice AI |
| **Document Version** | v1.0 – Hackathon-ready draft |

This is the authoritative PRD for the build, provided by the team's senior. It supersedes the earlier draft PRD written before this document existed. See `docs/ARCHITECTURE_MAPPING.md` for how this codebase implements each requirement below.

---

## Core Positioning

Most voice AI systems expect users to speak perfectly, listen clearly, remember complex instructions, and interact only through audio. TCS iON Voice AI makes AI adapt to real people, real speech, real environments, and real accessibility needs through live microphone input, live video/sign interaction, visual confirmation, intent analysis, RAG-grounded assistance, clear feedback, and multimodal fallback.

---

## 1. Executive Summary

TCS iON Voice AI is an accessibility-first multimodal AI prototype designed for the AI Friday hackathon theme "Voice meets inclusion." The product enables users to communicate naturally through live microphone input, live video-based sign language interaction, visual transcript review, and confirmable step-by-step assistance when communication is affected by speech impairments, non-native accents, noisy environments, hearing challenges, cognitive load, memory challenges, or temporary/situational impairments.

The differentiator is that TCS iON Voice AI does not treat voice as a perfect single channel. It detects accessibility barriers, supports audio and video input, interprets sign-language-style interaction at prototype level, simplifies complex instructions, normalizes difficult transcripts while preserving meaning, analyzes user intent, retrieves relevant contextual knowledge through a RAG layer, provides clear feedback and error recovery, and gives a transparent accessibility report showing what the system understood and how it supported the user.

**Hackathon Thesis:** If a human can understand the speaker, AI should be able to understand them too.

**Session Alignment Note:** The Vocal Accessibility Awareness session emphasized that voice-only systems can become inaccessible when they fail to understand accents, speech differences, noisy environments, hearing needs, or cognitive load. TCS iON Voice AI aligns with this principle by treating voice as one modality inside a multimodal, adaptive, transparent, and privacy-conscious interaction system.

---

## 2. Product Vision and Objectives

### 2.1 Vision

Build an inclusive multimodal gateway that helps AI systems understand and support diverse users without forcing users to change how they naturally speak, sign, listen, remember, process instructions, or recover from system errors.

### 2.2 Objectives

- Support live microphone input as the primary speech input channel without requiring audio upload.
- Support live camera/video input so users can interact through sign language or gesture-based communication when speech is difficult, unavailable, or not preferred.
- Support Bengali + English and Hindi + English style code-mixed speech, including non-native pronunciation and regional accents.
- Detect common speech impairment patterns such as repeated words, sound repetitions, fillers, long pauses, and disfluency.
- Improve resilience in noisy or reverberant environments by surfacing confidence, uncertainty, retry options, and confirmation prompts.
- Support users with hearing challenges through visual transcripts, automatic captions, summaries, and confirmable action previews.
- Reduce cognitive load and memory pressure by breaking complex multi-step instructions into simple, confirmable steps.
- Provide clear feedback and error recovery so the user can see what the system understood, correct it, retry, switch modality, or confirm before action.
- Analyze user intent from the accessible transcript or sign/gesture interpretation to understand what the user is trying to achieve, not just what they said literally.
- Use a RAG layer to retrieve relevant help content, accessibility guidance, process steps, FAQs, or domain knowledge before generating the final response.
- Generate an accessible transcript that removes disfluency without changing the user's meaning.
- Show transparency through a dashboard: input modality, language mix, speech barrier status, sign/gesture interpretation, noise/confidence status, support applied, inferred intent, retrieved context, and confirmation status.
- Design the demo around live interaction first, with fallback JSON only for recovery if API, microphone, camera, or network issues occur.

### 2.3 Alignment with Vocal Accessibility Session and PAS 901 Principles

| Principle | Product Alignment |
|---|---|
| Understand diverse users | Supports speech impairments, accents, multilingual/code-mixed speech, sign interaction, noisy environments, hearing challenges, and cognitive load. |
| Simplify interactions | Converts complex multi-step instructions into short, plain-language, confirmable steps. |
| Adapt to alternatives | Offers live mic, live video/sign interaction, visual transcript, text-style confirmation, retry, and fallback modality. |
| Provide clear feedback and recovery | Shows what was heard, what was understood, what action will be taken, and where the user can correct or retry. |
| Build trust and privacy by design | Avoids unnecessary storage of raw audio/video, uses explicit confirmation before action, and keeps accessibility analysis supportive rather than diagnostic. |
| Inclusive by default | Accessibility is part of the core workflow, not a separate optional add-on. |

---

## 3. Users and Accessibility Needs

| Accessibility Need | Example Scenario | Primary Barrier | TCS iON Voice AI Support |
|---|---|---|---|
| Speech impairments | "B-b-b-book appointment tomorrow" or "Call Ka-ka-ka-Kiran" | Sound repetition, word repetition, fillers, pauses, atypical speech patterns | Detect and normalize disfluency while preserving meaning and confirming intent visually |
| Non-native speakers and accents | User says "eleven" with a regional accent, or speaks Bengali-English/Hindi-English mixed speech | Accent mismatch, dialect variation, code-mixing, pronunciation variation | Detect language mix, preserve original intent, avoid accent bias, and confirm uncertain words |
| Noisy or reverberant environments | User speaks while train noise, office chatter, or background sound affects audio clarity | Low-confidence words, missing context, distorted audio | Surface confidence, ask confirmation, offer retry, and allow user to switch modality |
| Hearing challenges | User cannot rely on voice-only output or needs to verify what the system understood | Voice-only feedback is hard to hear or verify | Show visual transcript, captions, concise summary, and confirmable action preview |
| Cognitive load and memory challenges | System gives long IVR-style instructions such as "press one, then go to three, then enter account number" | High memory demand, long instructions, unclear next step, reduced processing comfort | Break tasks into short steps, summarize, reduce distractions, and confirm one step at a time |
| Sign language and gesture-based communication | User uses hand signs or gestures through live camera input | Speech may not be available, preferred, or practical | Capture video, extract gesture/sign cues, map to intent, and confirm visually before response |
| Temporary or situational impairments | User has an injured arm, eye strain, temporary voice issue, noisy workspace, or privacy-sensitive environment | User cannot use the usual modality comfortably | Allow multimodal switching between mic, video/sign, visual transcript, text-style confirmation, and retry |
| Motor accessibility and hands-free usage | User is cooking, driving, or unable to use keyboard/mouse easily | Touch or typing is inconvenient or unavailable | Enable live voice-first interaction with simple confirmation and fallback alternatives |

---

## 4. Scope: MVP vs Stretch Goals

| Area | MVP for Hackathon | Stretch Goal |
|---|---|---|
| Input | Live microphone capture and live camera/video capture from the user's device | Optional prepared audio/video fallback only for demo recovery |
| Transcription | Whisper-based near-real-time transcription for live speech | Timestamped segments, speaker diarization, and streaming captions |
| Sign interaction | Prototype-level gesture/sign capture through webcam with predefined demo gestures | Broader sign-language vocabulary and continuous sign recognition |
| Language handling | Detect Bengali/English/Hindi presence using LLM/rules | Full translation and localized output |
| Speech impairment support | Rule-based + LLM normalization for repetitions, fillers, pauses, and sound repetitions | User-specific speech profile and adaptive learning |
| Noise handling | Confidence markers, retry, clarification, and confirmation prompts | Noise classification and adaptive microphone enhancement |
| Cognitive support | Step-by-step simplification of complex instructions | Personalized cognitive load preference profile |
| Feedback and recovery | Show original input, interpreted meaning, correction path, retry option, and confirmation before action | Multi-turn recovery journey with user preference memory |
| Dashboard | Static metrics, intent JSON, retrieved context, accessibility report, and confirmation state | Interactive accessibility score trend and session comparison |
| Knowledge base | RAG layer for PAS/accessibility guidance, FAQs, process steps, and user-support knowledge | Personalized or enterprise knowledge retrieval using GTE-large embeddings and vector search |
| Privacy and trust | No unnecessary storage of raw audio/video; user confirmation before action | Consent dashboard and configurable retention controls |

---

## 5. Functional Requirements

| ID | Requirement | Description | Priority |
|---|---|---|---|
| FR-01 | Live Microphone Input | User speaks directly into the microphone; the system captures live audio for processing without requiring file upload. | Must Have |
| FR-02 | Speech-to-Text | System transcribes live microphone audio using azure/genailab-maas-whisper or a streaming/near-real-time speech pipeline. | Must Have |
| FR-03 | Speech Impairment and Disfluency Detection | System detects repeated words, sound repetition, filler words, long pauses, and other disfluency markers. | Must Have |
| FR-04 | Transcript Normalization | System creates an accessible transcript without changing meaning. | Must Have |
| FR-05 | Accent and Language Mix Detection | System identifies Bengali + English / Hindi + English patterns and supports non-native pronunciation variation. | Should Have |
| FR-06 | Noise-Aware Confirmation | System surfaces low-confidence or noisy input and asks for confirmation before action. | Should Have |
| FR-07 | Visual Transcript and Action Preview | System shows what it heard, what it understood, and what action it plans to take for user confirmation. | Must Have |
| FR-08 | Step-by-Step Simplification | System breaks complex multi-step instructions into short, confirmable steps to reduce cognitive load. | Should Have |
| FR-09 | Accessibility Analysis | System returns a structured report with detected barriers and support applied. | Must Have |
| FR-10 | Dashboard | UI displays original transcript, accessible transcript, confidence, barrier type, support applied, and report. | Must Have |
| FR-11 | User Intent Analysis | System extracts the user's goal, action type, entities, constraints, urgency, and missing information from the accessible transcript. | Must Have |
| FR-12 | RAG-Based Context Retrieval | System retrieves relevant knowledge snippets from indexed accessibility guidance, FAQs, workflow documents, and domain content before generating the final answer. | Must Have |
| FR-13 | Context-Aware Response Generation | System combines cleaned transcript, intent, accessibility report, and retrieved context to produce a clearer, more useful user response. | Must Have |
| FR-14 | Live Video Input for Sign Interaction | User can interact through the device camera using hand signs or gesture-based communication without requiring audio. | Should Have |
| FR-15 | Multimodal Fallback | System allows the user to switch between voice, video/sign, visual transcript, and text-style confirmation when one modality fails or is unsuitable. | Must Have |
| FR-16 | Clear Feedback and Error Recovery | System shows what was heard, what was understood, what is uncertain, and how the user can correct, retry, or confirm before action. | Must Have |
| FR-17 | Live Captions and Visual Equivalence | Every voice output or spoken interaction should have a visual equivalent such as transcript, caption, summary, or action preview. | Must Have |
| FR-18 | Privacy and Trust Controls | System avoids unnecessary storage of raw audio/video, clearly separates accessibility support from diagnosis, and asks confirmation before taking action. | Must Have |
| FR-19 | Real-World Scenario Testing | System includes test scenarios for stammering, accents, noisy environments, hearing needs, cognitive load, sign interaction, and modality switching. | Should Have |
| FR-20 | Domain-Aware Assistance | System uses RAG and intent analysis to adapt the final response to the user's domain context, such as banking, healthcare, education, travel, smart spaces, or support workflows. | Should Have |

---

## 6. Non-Functional Requirements

| ID | Category | Requirement | Priority |
|---|---|---|---|
| NFR-01 | Performance | Near-real-time feedback for live mic/video interactions, with visible progress states when processing takes longer than expected. | Must Have |
| NFR-02 | Reliability | Graceful degradation if microphone, camera, model API, network, or RAG retrieval fails, with clear recovery options. | Must Have |
| NFR-03 | Availability | Demo remains usable even if live model services are unavailable, using cached scenario outputs and a clearly marked fallback mode. | Must Have |
| NFR-04 | Accessibility | Visual equivalents for voice output, readable contrast, avoid voice-only confirmation, plain language instructions. | Must Have |
| NFR-05 | Usability | Understandable without training; clear labels: Start Listening, Start Camera, Retry, Confirm, Correct, Switch Modality, View Retrieved Context. | Must Have |
| NFR-06 | Privacy | No unnecessary storage of raw audio/video; temporary processing communicated clearly. | Must Have |
| NFR-07 | Security | API keys/secrets stored outside source code via env vars; logs avoid sensitive user input. | Must Have |
| NFR-08 | Transparency | Show original input, cleaned transcript/sign interpretation, inferred intent, confidence/uncertainty, retrieved context, support applied — before confirmation. | Must Have |
| NFR-09 | Maintainability | Modular separation: input capture, transcription, sign interpretation, accessibility analysis, intent extraction, RAG retrieval, response generation, UI. | Should Have |
| NFR-10 | Testability | Repeatable testing via predefined demo scenarios, cached outputs, unit-style detector checks, manual validation checklists. | Should Have |
| NFR-11 | Scalability | Future versions can add broader sign vocabulary, more languages, more knowledge bases, personalized profiles, without redesigning the core pipeline. | Should Have |
| NFR-12 | Responsible AI | No diagnostic labels, no ranking users, expose uncertainty, preserve meaning during normalization, supportive not medical framing. | Must Have |

---

## 7. Model and Architecture Plan

### 7.1 Model Usage

| Component | Preferred Model | Purpose |
|---|---|---|
| Speech transcription | azure/genailab-maas-whisper | Convert audio to text; automatic language detection. |
| Transcript cleanup | azure/genailab-maas-gpt-4o-mini | Remove disfluencies; preserve original meaning. |
| Accessibility reasoning | azure_ai/genailab-maas-DeepSeek-R1 or Phi-4-reasoning | Analyze accessibility barriers and severity. |
| User intent analysis | azure/genailab-maas-gpt-4o-mini or Llama-3.2-3b-it | Extract intent, entities, constraints, urgency, missing slots, next best action. |
| Final conversational response | azure/genailab-maas-gpt-4o | Generate user-facing response after intent is understood. |
| Knowledge retrieval | Gte-large or text-embedding-3-large | Embed and retrieve relevant accessibility guidance, FAQs, workflow steps, domain knowledge. |
| Coding assistant during build | Qwen-2.5.1-coder-it | Generate/repair code snippets during hackathon development. |
| Live video/sign interpretation | MediaPipe Hands / lightweight vision model / predefined gesture classifier | Detect hand landmarks or predefined sign gestures from live camera input, map to candidate intents. |
| Caption and visual equivalence generation | azure/genailab-maas-gpt-4o-mini | Generate concise captions, summaries, action previews. |
| Error recovery reasoning | azure_ai/genailab-maas-DeepSeek-R1 or Phi-4-reasoning | Decide whether to ask for confirmation, retry, clarification, modality switch, or next-step simplification. |
| Privacy and trust guardrails | Rule layer + LLM policy prompt | Avoid diagnostic labeling, minimize raw data retention, require confirmation before action. |

### 7.2 Architecture Flow

```
Live Mic + Video/Sign Input
Speech-to-Text / Gesture Interpretation
Language + Accent + Noise + Gesture Analysis
Cleanup + Accessibility Detection + Intent
RAG Retrieval
Grounded Response + Recovery
Dashboard + Confirmation + Modality Switch
```

---

## 8. User Experience and Demo Flow

### 8.1 Screen Flow

1. User chooses "Start Listening" for live microphone input or "Start Camera" for live video/sign interaction.
2. System captures live audio/video and shows live status indicators (listening, camera active, confidence, uncertainty).
3. Show original transcript or interpreted sign/gesture output.
4. Show accessible transcript, caption, or simplified interpretation after normalization.
5. Show detected accessibility barrier: speech impairment, accent/code-mixing, noise, hearing support need, cognitive load, sign interaction, or temporary/situational impairment.
6. Show support applied: cleanup, clarification, visual summary, live caption, retry prompt, modality switch, or step-by-step simplification.
7. Show detected user intent, extracted entities, missing information, recommended next action.
8. Show RAG context used: relevant FAQ, accessibility guidance, workflow step, domain knowledge.
9. Show what action the system plans to take and ask for confirmation before proceeding.
10. If the user rejects or corrects the interpretation, offer recovery: retry, edit text, switch to sign/video, switch to voice, or proceed step by step.
11. Generate a grounded response using transcript/sign interpretation, intent, accessibility support, retrieved knowledge, and confirmation status.

### 8.2 Demo Samples

| # | Input Scenario | Expected Output | Why It Matters |
|---|---|---|---|
| 1 | "B-b-b-book appointment tomorrow" | "Book appointment tomorrow"; speech impairment support applied; confirmation shown | Handles stammering/disfluency without changing meaning |
| 2 | "Call Ka-ka-ka-Kiran" | "Call Kiran"; repeated syllables cleaned; user confirms before action | Demonstrates support for speech differences in contact/action workflows |
| 3 | "eleven" with a strong regional accent | System detects possible accent-related uncertainty and asks "Did you mean floor 11?" | Prevents the voice-activated elevator-style failure where accent blocks task completion |
| 4 | Bengali-English or Hindi-English mixed query | Language mix detected; intent extracted; response generated in clear language | Supports non-native speakers, accents, and multilingual users |
| 5 | Speech while train noise/background chatter | Low-confidence words highlighted; retry or confirmation requested | Prevents incorrect action in noisy real-world environments |
| 6 | System needs payment or sensitive confirmation | Visual action preview shown; user confirms through available modality | Avoids voice-only confirmation barriers for users with hearing challenges |
| 7 | Complex IVR-style instructions | Instructions broken into short steps, one confirmation at a time | Reduces cognitive load and memory pressure |
| 8 | Live camera with predefined sign/gesture | Gesture mapped to candidate intent; visual confirmation requested | Demonstrates multimodal-by-design support |
| 9 | Voice unavailable (privacy/temporary condition) | User switches to visual/text confirmation or sign/video pathway | Handles situational impairment and modality switching |
| 10 | Domain-specific query | Intent analyzed; RAG retrieves relevant workflow/FAQ; grounded answer generated | Shows accessibility plus context improves usefulness |

---

## 9. Team Roles and Work Allocation

| Member | Role | Responsibilities | Deliverables | Definition of Done |
|---|---|---|---|---|
| Member 1 | Team Lead / Integration Lead | Own architecture, repo, environment, final integration, demo orchestration. | End-to-end pipeline and final demo script. | All modules run together from UI. |
| Member 2 | Speech AI Engineer | Integrate live microphone capture, stream/chunk audio, format transcript output. | `transcribe_audio()`, audio validation. | Live microphone input returns transcript reliably, with fallback JSON available only for demo recovery. |
| Member 3 | Accessibility AI Engineer | Implement accessibility barrier detection: speech impairments, noise/confidence, accents/language mix, cognitive load, modality switching, accessibility scoring. | `detect_stammering()`, `calculate_score()`. | Report flags repetition/fillers correctly. |
| Member 4 | LLM Engineer | Prompt engineering for cleanup, reasoning, intent extraction, RAG-grounded response generation. | `normalize_transcript()`, `extract_intent()`, `retrieve_context()`, `generate_response()`. | Cleaned transcript preserves meaning. |
| Member 5 | Frontend & Demo Engineer | Streamlit UI, live mic control, live camera/sign demo screen, dashboard, visual transcript, confirmation flow, fallback modality options, demo narrative. | Working live interaction screens, dashboard, session-aligned demo scenarios. | Judges can understand workflow visually. |

---

## 10. Hackathon Execution Plan

| Phase | Focus | Owner | Output |
|---|---|---|---|
| Phase 1 | Repo setup, secrets, environment, skeleton UI | Member 1 + 5 | Working app shell |
| Phase 2 | Live microphone transcription, live camera/video capture, fallback JSON setup | Member 2 | Live transcript output and video/sign demo input path |
| Phase 3 | Accessibility barrier detection: speech, accent, noise, cognitive load, hearing support, sign interaction, modality switching | Member 3 | Accessibility metrics JSON and support-applied report |
| Phase 4 | LLM cleanup, intent analysis, RAG grounding | Member 4 | Cleaned transcript + intent JSON + retrieved context |
| Phase 5 | Integration, live scenario testing, error recovery, privacy/trust checks, demo narrative | All | Final demo and pitch |

---

## 11. Evaluation and Success Metrics

| Metric | Target for Demo | Measurement Method |
|---|---|---|
| Live transcription availability | Transcript produced from live microphone input | Speak demo scenarios directly into mic |
| Sign/video interaction availability | Predefined sign/gesture input captured and mapped to candidate intent | Use webcam demo gesture scenario |
| Meaning preservation | Cleaned transcript does not change intent | Manual comparison by team |
| Speech impairment support | Flags repeated words, fillers, sound repetitions, long pauses | Rule test cases |
| Accent and language mix visibility | Shows accent uncertainty and Bengali+English/Hindi+English language mix | Dashboard JSON |
| Noise confidence handling | Low-confidence/noisy input triggers retry or confirmation | Noisy scenario walkthrough |
| Visual equivalence support | Voice output has transcript, caption, summary, or action preview | UI walkthrough |
| Cognitive load reduction | Complex instructions broken into short confirmable steps | IVR-style scenario walkthrough |
| Intent analysis quality | Correctly identifies user goal, entities, missing information | Compare output JSON with expected demo scenarios |
| RAG usefulness | Retrieved context improves answer relevance, reduces generic responses | Show retrieved snippets and grounded response |
| Error recovery | User can correct, retry, confirm, or switch modality after uncertainty | Demo correction flow |
| Privacy and trust | Raw audio/video not unnecessarily stored; action requires confirmation | Review UI and responsible AI notes |
| Real-world scenario coverage | Demo covers speech, accent, noise, hearing, cognitive, sign/video, situational cases | Checklist against session-inspired scenarios |

---

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Live microphone or camera fails during demo | Demo may fail | Keep fallback JSON responses for UI demonstration while clearly positioning live input as primary |
| Whisper output already removes stammering | Hard to prove detector value | Show original transcript, simulated disfluency case, and support-applied report |
| API latency or quota issue | Demo may fail | Cache fallback outputs for each demo scenario |
| LLM paraphrases too much | Meaning may change | Use strict prompt: remove disfluencies only, do not change user intent |
| Sign-language recognition scope becomes too large | Incomplete demo | Use predefined gesture/sign vocabulary for MVP; broader sign recognition as stretch goal |
| Too many features attempted | Incomplete demo | Prioritize live mic, live camera/sign demo, accessibility report, intent analysis, RAG, confirmation, fallback |
| Mixed language output inconsistent | Judges may question reliability | Position as accessibility assistive prototype with transparent confidence and confirmation |
| Voice-only design accidentally remains in flow | Accessibility gap | Ensure every voice output has visual equivalent and every action has non-voice confirmation option |
| Raw audio/video privacy concern | Reduced trust | Avoid unnecessary storage, show privacy note, use explicit confirmation before action |
| RAG retrieval returns irrelevant content | Poor answer quality | Use curated mini knowledge base and show retrieved snippets transparently |

---

## 13. Final Pitch

**30-Second Pitch:** TCS iON Voice AI is an accessibility-first multimodal AI gateway. It helps AI understand and support users affected by speech impairments, non-native accents, noisy environments, hearing challenges, cognitive load, memory challenges, sign-language interaction needs, and temporary or situational impairments. Instead of asking people to adapt to AI, TCS iON Voice AI makes AI adapt to people through live mic input, live video/sign interaction, clearer transcripts, visual confirmation, intent analysis, RAG-grounded knowledge retrieval, confidence-aware recovery, and step-by-step assistance.

**Closing Message for Judges:** TCS iON Voice AI is not just another voice chatbot. It demonstrates the future of inclusive AI: systems that understand diverse voices, support sign and visual interaction, infer user intent, retrieve relevant knowledge, remain usable in noisy or privacy-sensitive conditions, provide clear feedback and recovery, and reduce cognitive load by making complex tasks easier to follow. The goal is simple: every voice, every context, every user.

---

## Appendix A: MVP Pipeline Pseudocode

```
audio_stream = start_live_microphone_capture()
video_stream = start_live_camera_capture(optional=True)

transcript = whisper_transcribe_stream(audio_stream)
sign_result = interpret_sign_or_gesture(video_stream)

input_context = merge_inputs(
    transcript=transcript,
    sign_result=sign_result
)

language_report = detect_language_mix(input_context)
accent_noise_report = analyze_accent_noise_confidence(input_context)
disfluency_report = detect_stammering(input_context)

accessible_transcript = normalize_transcript(input_context)
visual_equivalent = generate_caption_summary_action_preview(accessible_transcript)

accessibility_report = analyze_accessibility(
    original=input_context,
    cleaned=accessible_transcript,
    language_report=language_report,
    accent_noise_report=accent_noise_report,
    disfluency_report=disfluency_report,
    sign_result=sign_result
)

intent = extract_intent(accessible_transcript, sign_result)
retrieved_context = rag_retrieve(intent, accessible_transcript)

final_response = generate_grounded_response(
    accessible_transcript=accessible_transcript,
    intent=intent,
    retrieved_context=retrieved_context,
    accessibility_report=accessibility_report
)

recovery_options = decide_recovery_or_confirmation(
    confidence=accent_noise_report.confidence,
    missing_slots=intent.missing_information,
    accessibility_report=accessibility_report
)

render_dashboard(
    original_input=input_context,
    accessible_transcript=accessible_transcript,
    visual_equivalent=visual_equivalent,
    intent=intent,
    retrieved_context=retrieved_context,
    final_response=final_response,
    accessibility_report=accessibility_report,
    recovery_options=recovery_options
)
```

---

## Appendix B: Responsible AI Notes

- Do not label the user negatively; describe only processing challenges and support applied.
- Treat accessibility analysis as supportive guidance, not medical diagnosis.
- Always show original input, accessible transcript or sign interpretation, and final understood intent for transparency.
- Allow user confirmation before taking action from normalized transcript, sign interpretation, or inferred intent.
- Provide non-voice alternatives for confirmation, including visual review, text-style confirmation, and sign/video pathway where available.
- Avoid unnecessary storage of raw audio/video; use temporary processing wherever possible for demo.
- Make uncertainty visible through confidence markers, clarification prompts, and retry options.
- Do not assume perfect speech, perfect hearing, perfect memory, or perfect environment.
- Keep RAG sources curated and show retrieved snippets transparently in the dashboard.
- Use plain language and step-by-step guidance to reduce cognitive load.
