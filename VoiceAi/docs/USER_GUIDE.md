# User Guide — Adaptive, Cognitive-Friendly Interaction

This guide describes how TCS iON Voice AI paces conversations for users who
find fast, multi-step voice commands overwhelming (the "Simplified Voice
Interaction for Users with Cognitive Challenges" scenario) — written for
whoever is demoing or evaluating the assistant, not for developers. For the
underlying architecture, see [`DIALOGUE_MANAGEMENT.md`](DIALOGUE_MANAGEMENT.md).

## The problem this solves

Aditi wants to set a reminder. A typical voice assistant expects one
complete sentence with every detail packed in: *"remind me to call the
pharmacy about my prescription refill tomorrow at four thirty in the
afternoon."* If Aditi can't hold all of that in her head at once, or gets
partway through and loses her train of thought, the request fails and she
has to start over — often more than once. That failure isn't a speech
problem; it's an interaction-design problem.

## How the assistant paces itself

The assistant only ever asks for **one thing at a time**, and it remembers
where it is in the conversation across turns — it doesn't forget what was
already said and doesn't demand everything up front.

**Example conversation:**

| Turn | Aditi says | The assistant says |
|---|---|---|
| 1 | "Set a reminder" | *"What should I remind you about?"* |
| 2 | "Call the pharmacy" | *"When should I remind you? For example, 'tomorrow at 5pm'."* |
| 3 | "Tomorrow at 4:30" | *"Saved. I'll remind you about 'call the pharmacy' at tomorrow at 4:30."* |

Nothing is scheduled until every piece has been gathered and confirmed —
there's no risk of a half-heard command silently doing the wrong thing.

If Aditi already says everything in one go — *"remind me to call the
pharmacy tomorrow at 4:30"* — the assistant recognizes that and confirms
directly, with no extra questions. The pacing only appears when it's
actually needed, so the assistant never feels slower than it has to be.

## What's on screen (or spoken) at each step

- **The current question is the whole response** — short, plain language,
  nothing else competing for attention. It's spoken aloud and shown as
  large on-screen text at the same time (see the caption/visual-equivalent
  guidance below).
- **A "Correct" option is always available** instead of "Confirm" while a
  question is still open — there's nothing to confirm yet, only an answer
  to give, so the buttons on screen only offer choices that actually make
  sense at that moment.
- **Once every detail is gathered**, the assistant reads back exactly what
  it understood and offers **Confirm / Correct / Retry / Switch Modality**
  before anything is actually scheduled.
- **"Show what's happening under the hood"** (collapsed by default) reveals
  the technical detail — the accessibility barriers detected, the intent
  extracted, retrieved knowledge, and the agent's reasoning trace — for
  anyone who wants to see how the answer was produced, without cluttering
  the default view.

## Checking it actually worked

Reminders are genuinely saved (a real local database, not a claim the
assistant makes and forgets) — ask *"what are my reminders?"* and it will
read back everything that's actually been scheduled. This matters for
demonstrating real task completion, not just a plausible-sounding response.

## If something goes wrong mid-conversation

- **Wrong answer given** — use **Correct** to re-say or re-type the answer
  to the current question; it doesn't restart the whole reminder.
  Voice-driven recovery listens for a spoken correction automatically.
- **Taking too long / stuck** — after six exchanges without completing a
  task, the assistant resets on its own and asks what you'd like to do,
  rather than looping indefinitely.
- **Want to do something else entirely** — Switch Modality (mic ↔ gesture
  ↔ text) is always available, and starting a new, unrelated request will
  simply begin a new conversation.

## Accessibility notes

- Every spoken prompt has a visual equivalent shown on screen at the same
  time — nothing is voice-only.
- The assistant never guesses silently on low-confidence input; it always
  asks, using the same plain-language, one-question-at-a-time pattern
  described above.
- Nothing is diagnostic or judgmental — the system describes support it
  applied ("paced this into smaller steps"), never a label about the user.
