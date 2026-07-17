# Demo Script — Simplified Voice Interaction for Users with Cognitive Challenges

A concrete walkthrough for showing the cognitive-friendly guided-dialogue
workflow live. Written for `PROFILE=mock` (works with zero setup, zero
cost, zero internet) — swap to `local`/`hybrid`/`fast` for real ASR/LLM per
[`README.md`](../README.md#cost-profiles----one-switch-controls-spend) if
the venue network allows it.

## Setup (once)

```bash
cd VoiceAi
source .venv/bin/activate      # or venv\Scripts\activate on Windows
uvicorn server:app --port 8000
```

Open `http://localhost:8000` in a browser. Confirm the greeting screen
shows a single "Tap to talk" orb — no dashboard, no configuration panel.

## Part 1 — The failure mode this solves (say this out loud)

*"A typical voice assistant expects one complete sentence with every detail
packed in — a name, a time, sometimes more. For someone with a cognitive or
processing difficulty, that's exactly the kind of rapid multi-step command
that causes the task to fail. Watch what this assistant does instead."*

## Part 2 — The paced conversation

Speak (or type, via "Type instead") each line and pause for the response
before continuing — that pause **is** the demo:

| # | Say | Expect |
|---|---|---|
| 1 | *"Set a reminder"* / *"book appointment"* | *"What should I remind you about?"* — one short question, nothing else. Point out: only **Correct** is offered, not Confirm — there's nothing to confirm yet. |
| 2 | *"Call the pharmacy"* | *"When should I remind you? For example, 'tomorrow at 5pm'."* — the assistant did **not** re-ask what the reminder is about; it remembered. |
| 3 | *"Tomorrow at 4:30"* | *"Saved. I'll remind you about 'call the pharmacy' at tomorrow at 4:30."* — **Confirm** now appears, because there's finally something to confirm. |

**Say:** *"Three short exchanges, one question at a time, instead of one
overwhelming sentence. And it isn't just saying it saved something —"*

## Part 3 — Prove it's real, not a script

Say *"What are my reminders?"* → the assistant reads back the reminder
from Part 2. This is a genuine SQLite-backed store (`.reminders.db`), not
an in-memory illusion — kill and restart the server, ask again, it's still
there.

*(Optional, if you want to show the file directly:)*
```bash
python -c "from src.integrations.reminders_store import list_reminders; print(list_reminders('demo-user'))"
```

## Part 4 — Contrast: when pacing gets out of the way

Say the whole thing in one sentence: *"Remind me to call the pharmacy
tomorrow at 4:30."* Point out that no extra questions are asked this time —
pacing only appears when something is actually missing, so the assistant
never feels slower than it needs to be. (Under `PROFILE=mock` this
specific one-shot case will still pace, since the mock planner never
extracts named fields from free text — see the "Known scope limits" note
in `DIALOGUE_MANAGEMENT.md`. On `PROFILE=local`/`hybrid`/`fast` with a real
LLM, this line completes in one turn with no questions, which is a better
version of this specific beat to show if the network/local Ollama is
available.)

## Part 5 — Recovery, still one tap or one word

Deliberately answer a question wrong (e.g. answer "9pm" during the subject
question), then tap **Correct** and give the right answer, or just say
"that's wrong" — the voice-driven recovery loop listens for it
automatically. Show that this corrects the *current* slot, not the whole
conversation from scratch.

## Part 6 — Under the hood (only if asked)

Click "Show what's happening under the hood" to reveal: the accessibility
barriers detected, the intent extracted, retrieved knowledge context, and
the full agent reasoning trace (each turn shows exactly one step —
`clarify` or `call_skill` — proving the dialogue state, not a hidden
multi-step replan, is what's driving the pacing).

## Timing

Parts 1–3 alone run under two minutes and are the complete story. Parts 4–6
are there if there's time or a specific question comes up — don't feel
obligated to run the whole script.

## If something breaks live

- **A turn suddenly restarts the whole reminder from scratch:** the
  dialogue exceeded its 6-turn safety cap (`MAX_DIALOGUE_TURNS` in
  `src/understanding/dialogue_state.py`) and reset intentionally — say so,
  it's a deliberate guardrail, not a bug.
- **Response looks generic ("Understood: ...") instead of confirming the
  reminder:** check `PROFILE` in the startup log — this was a real bug in
  the mock LLM (fixed; see `DIALOGUE_MANAGEMENT.md`), so if it recurs on a
  real backend, that's worth flagging, not expected.
- **Nothing responds / a cached-looking demo answer appears regardless of
  what was said:** check the server log for `### FALLBACK TO CACHED
  SCENARIO ###` — this means a live backend genuinely failed (network,
  SSL, missing model). See the README's "Known limitations" section.
