"use strict";
/* TCS iON Voice AI -- frontend logic.
   Voice input: real audio capture (MediaRecorder) sent to our own Whisper
   pipeline -- deliberately NOT the browser's built-in SpeechRecognition,
   which would auto-clean disfluent speech before our Speech Equalizer ever
   sees it and defeat the whole accessibility-detection story.
   Voice output: browser speechSynthesis -- free, zero backend, works
   offline once the page is loaded. */

// ---------------------------------------------------------------- state --
const state = {
  mode: "mic", // mic | camera | text
  micStream: null,
  micRecorder: null,
  micChunks: [],
  micBlob: null,
  cameraStream: null,
  gestureBlob: null,
  lastRun: { audioBlob: null, imageBlob: null, text: null },
  lastResult: null,
  activeFieldRecorder: null, // {button, recorder, chunks, stream} for push-to-talk fields
};

const $ = (id) => document.getElementById(id);

// -------------------------------------------------------------- backend --
async function loadBackendInfo() {
  const [cost, skills] = await Promise.all([
    fetch("/api/cost").then((r) => r.json()),
    fetch("/api/skills").then((r) => r.json()),
  ]);
  renderCost(cost);
  $("backendCaption").textContent = `Profile: ${cost.profile}`;
  const list = $("skillsList");
  list.innerHTML = "";
  skills.skills.forEach((s) => {
    const li = document.createElement("li");
    li.innerHTML = `<code>${s.name}</code> — ${s.description}`;
    list.appendChild(li);
  });
  loadCorrections();
}

async function loadCorrections() {
  const data = await fetch("/api/corrections").then((r) => r.json());
  const el = $("knownCorrections");
  const entries = Object.entries(data.corrections || {});
  el.textContent = entries.length ? "Currently remembered: " + entries.map(([k, v]) => `${k} -> ${v}`).join(", ") : "";
}

function renderCost(cost) {
  $("costAmount").textContent = `$${cost.total_usd.toFixed(4)}`;
  const pct = cost.cap_usd ? Math.min(100, (cost.total_usd / cost.cap_usd) * 100) : 0;
  $("costProgress").style.width = pct + "%";
  $("costProgressWrap").setAttribute("aria-valuenow", String(Math.round(pct)));
  $("costCaption").textContent = `cap $${cost.cap_usd.toFixed(2)} · profile ${cost.profile}`;
  const byStage = $("costByStage");
  byStage.innerHTML = "";
  Object.entries(cost.by_stage || {}).forEach(([stage, usd]) => {
    const row = document.createElement("div");
    row.innerHTML = `<span>${stage}</span><span>$${usd.toFixed(4)}</span>`;
    byStage.appendChild(row);
  });
}

$("resetCostBtn").addEventListener("click", async () => {
  const cost = await fetch("/api/cost/reset", { method: "POST" }).then((r) => r.json());
  renderCost(cost);
});

// ------------------------------------------------------------ mode tabs --
function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode-tab").forEach((btn) => {
    const active = btn.dataset.mode === mode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", String(active));
  });
  ["mic", "camera", "text"].forEach((m) => {
    $(`mode-${m}`).hidden = m !== mode;
  });
  updateRunEnabled();
}

document.querySelectorAll(".mode-tab").forEach((btn) => {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
});

function updateRunEnabled() {
  let enabled = false;
  if (state.mode === "mic") enabled = !!state.micBlob;
  else if (state.mode === "camera") enabled = !!state.gestureBlob;
  else if (state.mode === "text") enabled = $("textInput").value.trim().length > 0;
  $("runBtn").disabled = !enabled;
}
$("textInput").addEventListener("input", updateRunEnabled);

// --------------------------------------------------------- mic recording --
async function toggleMicRecording() {
  const btn = $("micRecordBtn");
  if (state.micRecorder && state.micRecorder.state === "recording") {
    state.micRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.micStream = stream;
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      state.micBlob = new Blob(chunks, { type: "audio/webm" });
      $("micPreview").src = URL.createObjectURL(state.micBlob);
      $("micPreview").hidden = false;
      $("micStatus").textContent = "Captured. Click Run below.";
      btn.textContent = "🎙 Start recording";
      stream.getTracks().forEach((t) => t.stop());
      updateRunEnabled();
    };
    recorder.start();
    state.micRecorder = recorder;
    btn.textContent = "⏹ Stop recording";
    $("micStatus").textContent = "Recording… speak now.";
  } catch (err) {
    showFallbackBanner(`Microphone access failed: ${err.message}`);
  }
}
$("micRecordBtn").addEventListener("click", toggleMicRecording);

// ------------------------------------------------------------ camera/gesture --
$("cameraStartBtn").addEventListener("click", async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    state.cameraStream = stream;
    $("cameraPreview").srcObject = stream;
    $("cameraCaptureBtn").disabled = false;
  } catch (err) {
    showFallbackBanner(`Camera access failed: ${err.message}`);
  }
});

$("cameraCaptureBtn").addEventListener("click", () => {
  const video = $("cameraPreview");
  const canvas = $("cameraCanvas");
  canvas.width = video.videoWidth || 320;
  canvas.height = video.videoHeight || 240;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.toBlob((blob) => {
    state.gestureBlob = blob;
    const img = $("capturedGesturePreview");
    img.src = URL.createObjectURL(blob);
    img.hidden = false;
    updateRunEnabled();
  }, "image/jpeg");
});

// -------------------------------------------------------- push-to-talk fields --
document.querySelectorAll(".mic-btn").forEach((btn) => {
  btn.addEventListener("click", () => togglePushToTalk(btn));
});

async function togglePushToTalk(btn) {
  const targetId = btn.dataset.target;
  if (state.activeFieldRecorder && state.activeFieldRecorder.button === btn) {
    state.activeFieldRecorder.recorder.stop();
    return;
  }
  if (state.activeFieldRecorder) return; // one field recording at a time
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = async () => {
      btn.classList.remove("recording");
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: "audio/webm" });
      state.activeFieldRecorder = null;
      try {
        const form = new FormData();
        form.append("audio", blob, "field.webm");
        const res = await fetch("/api/transcribe", { method: "POST", body: form });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        $(targetId).value = data.text;
        updateRunEnabled();
      } catch (err) {
        showFallbackBanner(`Transcription failed: ${err.message}`);
      }
    };
    recorder.start();
    state.activeFieldRecorder = { button: btn, recorder, stream };
    btn.classList.add("recording");
  } catch (err) {
    showFallbackBanner(`Microphone access failed: ${err.message}`);
  }
}

// -------------------------------------------------------------- personalize --
$("saveCorrectionBtn").addEventListener("click", async () => {
  const wrong = $("wrongWordInput").value.trim();
  const right = $("rightWordInput").value.trim();
  if (!wrong || !right) return;
  const form = new FormData();
  form.append("original", wrong);
  form.append("corrected", right);
  await fetch("/api/correction", { method: "POST", body: form });
  $("wrongWordInput").value = "";
  $("rightWordInput").value = "";
  loadCorrections();
});

// ------------------------------------------------------------------ run --
$("runBtn").addEventListener("click", () => {
  if (state.mode === "mic") runPipeline({ audioBlob: state.micBlob });
  else if (state.mode === "camera") runPipeline({ imageBlob: state.gestureBlob });
  else runPipeline({ text: $("textInput").value.trim() });
});

async function runPipeline({ audioBlob = null, imageBlob = null, text = null }) {
  state.lastRun = { audioBlob, imageBlob, text };
  $("runBtn").disabled = true;
  $("runBtn").textContent = "Processing…";
  $("fallbackBanner").hidden = true;
  try {
    const form = new FormData();
    if (audioBlob) form.append("audio", audioBlob, "input.webm");
    if (imageBlob) form.append("image", imageBlob, "input.jpg");
    if (text) form.append("text", text);
    const res = await fetch("/api/run", { method: "POST", body: form });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText);
    }
    const result = await res.json();
    state.lastResult = result;
    renderResult(result);
    renderCost(result.cost);
    renderLatency(result);
  } catch (err) {
    showFallbackBanner(`Pipeline error: ${err.message}`);
  } finally {
    $("runBtn").textContent = "Run";
    updateRunEnabled();
  }
}

function showFallbackBanner(msg) {
  const el = $("fallbackBanner");
  el.textContent = msg;
  el.hidden = false;
}

// -------------------------------------------------------------- render --
function renderResult(r) {
  $("resultSection").hidden = false;

  if (r.used_fallback_cache) {
    showFallbackBanner(`FALLBACK MODE: ${r.fallback_reason}`);
  }

  $("originalInputOut").value = r.original_input.text;
  $("accessibleTranscriptOut").value = r.accessible_transcript.text;
  $("modalityConfidence").textContent =
    `Modality: ${r.original_input.modality} · Confidence: ${Math.round(r.original_input.confidence * 100)}%`;

  const clarify = $("clarifyingQuestion");
  if (r.accent_noise_report.clarifying_question) {
    clarify.textContent = `Clarifying question: ${r.accent_noise_report.clarifying_question}`;
    clarify.hidden = false;
  } else {
    clarify.hidden = true;
  }

  fillList("barriersList", r.accessibility_report.barriers_detected);
  fillList("supportList", r.accessibility_report.support_applied);

  const langLine = $("languagesLine");
  if (r.language_report.code_mixed) {
    langLine.textContent = `Languages detected: ${r.language_report.languages_detected.join(", ")}`;
    langLine.hidden = false;
  } else {
    langLine.hidden = true;
  }

  const stepsSection = $("stepsSection");
  if (r.simplified_steps.was_simplified) {
    fillOrderedList("stepsList", r.simplified_steps.steps);
    stepsSection.hidden = false;
  } else {
    stepsSection.hidden = true;
  }

  $("intentJson").textContent = JSON.stringify(
    {
      goal: r.intent.goal,
      action_type: r.intent.action_type,
      entities: r.intent.entities,
      constraints: r.intent.constraints,
      urgency: r.intent.urgency,
      missing_information: r.intent.missing_information,
    },
    null,
    2
  );

  $("ragSummary").textContent = `View Retrieved Context (${r.retrieved_context.length} snippets)`;
  const ragEl = $("ragContext");
  ragEl.innerHTML = "";
  r.retrieved_context.forEach((s) => {
    const div = document.createElement("div");
    div.innerHTML = `<strong>${s.title}</strong> <span class="muted">(${s.source})</span><p>${s.content}</p>`;
    ragEl.appendChild(div);
  });

  renderAgentTrace(r.agent_result);

  $("actionPreview").textContent = r.visual_equivalent.action_preview;
  $("captionLine").textContent = `Caption: ${r.visual_equivalent.caption}`;
  $("finalResponse").textContent = r.final_response.text;

  renderRecovery(r.recovery_options);

  $("confirmedBanner").hidden = true;
  $("correctPanel").hidden = true;
  $("recoveryListenStatus").textContent = "";

  // --- Voice output: speak the response (and any clarifying question), in
  // the language the user actually used, if a matching voice exists. If
  // voice-driven confirmation is enabled, auto-listen for a spoken reply
  // once speaking finishes, so a speak-and-listen-only user never has to
  // click Confirm/Correct/Retry/Switch Modality. ---
  const toSpeak = r.accent_noise_report.clarifying_question || r.final_response.text;
  const options = r.recovery_options.options || [];
  const voiceRecoveryOn = $("voiceRecoveryToggle").checked;
  speakText(toSpeak, r.language_report.languages_detected, () => {
    if (voiceRecoveryOn && options.length) autoListenForRecovery(options);
  });
}

function fillList(id, items) {
  const el = $(id);
  el.innerHTML = "";
  (items || []).forEach((i) => {
    const li = document.createElement("li");
    li.textContent = i;
    el.appendChild(li);
  });
}
function fillOrderedList(id, items) {
  const el = $(id);
  el.innerHTML = "";
  (items || []).forEach((i) => {
    const li = document.createElement("li");
    li.textContent = i;
    el.appendChild(li);
  });
}

function renderAgentTrace(agent) {
  $("agentCaption").textContent =
    `${agent.steps.length} step(s) · tools used: ${agent.skills_used.join(", ") || "none"}` +
    (agent.hit_max_steps ? " · hit step cap" : "");
  const container = $("agentTrace");
  container.innerHTML = "";
  const icons = { call_skill: "🔧", clarify: "❓", finish: "✅" };
  agent.steps.forEach((step) => {
    const details = document.createElement("details");
    const icon = icons[step.action] || "•";
    const summary = document.createElement("summary");
    summary.textContent = `${icon} Step ${step.step}: ${step.action}` + (step.skill ? ` → ${step.skill}` : "");
    details.appendChild(summary);
    const body = document.createElement("div");
    let html = `<p><strong>Thought:</strong> ${step.thought}</p>`;
    if (step.skill) html += `<p><strong>Tool:</strong> <code>${step.skill}</code> · <strong>Params:</strong> <code>${JSON.stringify(step.params)}</code></p>`;
    if (step.observation) html += `<p><strong>Observation:</strong> ${step.observation}</p>`;
    if (step.question) html += `<p><strong>Clarifying question:</strong> ${step.question}</p>`;
    body.innerHTML = html;
    details.appendChild(body);
    container.appendChild(details);
  });
  const clarifyBanner = $("agentClarification");
  if (agent.clarification) {
    clarifyBanner.textContent = `Agent needs clarification: ${agent.clarification}`;
    clarifyBanner.hidden = false;
  } else {
    clarifyBanner.hidden = true;
  }
}

function renderLatency(r) {
  const panel = $("latencyPanel");
  panel.hidden = false;
  const totalS = r.total_ms / 1000;
  $("latencyTotal").textContent = `${totalS.toFixed(1)} s`;
  const verdict = $("latencyVerdict");
  if (r.total_ms > 12000) {
    verdict.textContent = "Slow for a live demo (>12s). Try PROFILE=fast.";
    verdict.className = "verdict bad";
  } else if (r.total_ms > 6000) {
    verdict.textContent = "A bit slow (>6s). PROFILE=fast will be snappier.";
    verdict.className = "verdict warn";
  } else {
    verdict.textContent = "Snappy enough for a live demo.";
    verdict.className = "verdict good";
  }
  const byStage = $("latencyByStage");
  byStage.innerHTML = "";
  Object.entries(r.timings_ms)
    .sort((a, b) => b[1] - a[1])
    .forEach(([stage, ms]) => {
      const row = document.createElement("div");
      row.innerHTML = `<span>${stage}</span><span>${(ms / 1000).toFixed(2)} s</span>`;
      byStage.appendChild(row);
    });
}

// -------------------------------------------------------- recovery/FR-16 --
const RECOVERY_LABELS = { confirm: "Confirm", correct: "Correct", retry: "Retry", switch_modality: "Switch Modality" };

function renderRecovery(recovery) {
  const container = $("recoveryButtons");
  container.innerHTML = "";
  recovery.options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn";
    btn.textContent = RECOVERY_LABELS[opt] || opt;
    btn.addEventListener("click", () => handleRecoveryAction(opt));
    container.appendChild(btn);
  });
  $("recoveryReason").textContent = recovery.needs_confirmation ? `Confirmation requested: ${recovery.reason}` : "";
}

function handleRecoveryAction(action) {
  if (action === "confirm") {
    $("confirmedBanner").hidden = false;
  } else if (action === "retry") {
    runPipeline(state.lastRun);
  } else if (action === "switch_modality") {
    const order = ["mic", "camera", "text"];
    setMode(order[(order.indexOf(state.mode) + 1) % order.length]);
  } else if (action === "correct") {
    $("correctPanel").hidden = false;
    $("correctionText").value = state.lastResult ? state.lastResult.accessible_transcript.text : "";
  }
}

$("applyCorrectionBtn").addEventListener("click", async () => {
  const corrected = $("correctionText").value.trim();
  if (!corrected || !state.lastResult) return;
  const original = state.lastResult.original_input.text;
  if (original && corrected !== original) {
    const form = new FormData();
    form.append("original", original);
    form.append("corrected", corrected);
    await fetch("/api/correction", { method: "POST", body: form });
    loadCorrections();
  }
  runPipeline({ text: corrected });
});

$("replayVoiceBtn").addEventListener("click", () => {
  if (state.lastResult) speakText(state.lastResult.final_response.text, state.lastResult.language_report.languages_detected);
});

// --------------------------------------------------------- voice output --
// BCP-47 tags for the language codes our detector emits (src/analysis/language.py).
const LANG_BCP47 = { en: "en-US", hi: "hi-IN", bn: "bn-IN" };

let _voicesCache = [];
function refreshVoices() {
  _voicesCache = window.speechSynthesis.getVoices();
}
if ("speechSynthesis" in window) {
  refreshVoices();
  window.speechSynthesis.onvoiceschanged = refreshVoices; // Chrome loads voices async
}

function speakText(text, languagesDetected, onend) {
  if (!text || !("speechSynthesis" in window)) {
    if (onend) onend();
    return;
  }
  window.speechSynthesis.cancel(); // don't stack utterances across turns
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = 1.0;

  // Prefer the non-English detected language (the one worth voicing
  // correctly); fall back to English if that's all that was detected.
  const langs = languagesDetected && languagesDetected.length ? languagesDetected : ["en"];
  const primary = langs.find((l) => l !== "en") || langs[0] || "en";
  const bcp47 = LANG_BCP47[primary] || "en-US";
  utter.lang = bcp47;

  const voices = _voicesCache.length ? _voicesCache : window.speechSynthesis.getVoices();
  const match = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith(primary));
  if (match) utter.voice = match;
  // If no matching voice is installed on this machine/browser, speechSynthesis
  // falls back to its default voice automatically -- pronunciation of
  // non-Latin-script text won't be accurate, but nothing breaks. That's a
  // real OS/voice-pack constraint, not something JS can work around.

  if (onend) {
    utter.onend = onend;
    utter.onerror = onend; // still try to listen even if TTS itself failed
  }
  window.speechSynthesis.speak(utter);
}

// ------------------------------------------- voice-driven recovery (FR-16) --
// Completes the loop for a speak-and-listen-only user: after the response is
// spoken, auto-listen for a short reply ("yes", "retry", "that's wrong",
// "switch") and match it via /api/recovery-intent, instead of requiring a
// click. Opt-in (see #voiceRecoveryToggle) so the mic doesn't activate
// unexpectedly for someone using text/camera mode.
const AUTO_LISTEN_MS = 4000;

async function autoListenForRecovery(options) {
  const statusEl = $("recoveryListenStatus");
  statusEl.textContent = "Listening for your reply (yes / retry / that's wrong / switch)…";
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    statusEl.textContent = ""; // mic denied/unavailable -- silently fall back to manual buttons
    return;
  }
  try {
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    const stopped = new Promise((resolve) => {
      recorder.onstop = resolve;
    });
    recorder.start();
    setTimeout(() => {
      if (recorder.state === "recording") recorder.stop();
    }, AUTO_LISTEN_MS);
    await stopped;
    stream.getTracks().forEach((t) => t.stop());

    statusEl.textContent = "Processing your reply…";
    const blob = new Blob(chunks, { type: "audio/webm" });
    const form = new FormData();
    form.append("audio", blob, "recovery.webm");
    form.append("options", JSON.stringify(options));
    const res = await fetch("/api/recovery-intent", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    if (data.matched_action) {
      statusEl.textContent = `Heard "${data.heard}" → ${RECOVERY_LABELS[data.matched_action] || data.matched_action}`;
      handleRecoveryAction(data.matched_action);
    } else if (data.heard) {
      statusEl.textContent = `Heard "${data.heard}" — didn't match an action, use a button below if needed.`;
    } else {
      statusEl.textContent = "Didn't catch a reply — use a button below if needed.";
    }
  } catch (err) {
    stream.getTracks().forEach((t) => t.stop());
    statusEl.textContent = ""; // background convenience feature -- fail quietly, buttons remain
  }
}

// ------------------------------------------------------------------ init --
setMode("mic");
loadBackendInfo();
