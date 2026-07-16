"use strict";
/* TCS iON Voice AI -- frontend logic.
   Voice input: real audio capture (MediaRecorder) sent to our own Whisper
   pipeline -- deliberately NOT the browser's built-in SpeechRecognition,
   which would auto-clean disfluent speech before our Speech Equalizer ever
   sees it and defeat the whole accessibility-detection story.
   Voice output: browser speechSynthesis -- free, zero backend, works
   offline once the page is loaded.

   Interaction model: conversational, not a pipeline-operator's console.
   One tap starts a turn; the pipeline stage names, buttons, and "Run"
   click that used to be here are gone -- see README's "Interaction
   redesign" note for the reasoning (real user feedback that the previous
   click-record/click-stop/click-run/click-confirm flow felt mechanical). */

// ---------------------------------------------------------------- state --
const state = {
  mode: "mic", // mic | camera | text
  micStream: null,
  micRecorder: null,
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

// ------------------------------------------------------- sidebar toggle --
$("sidebarToggle").addEventListener("click", () => {
  const willShow = $("sidebar").hidden;
  $("sidebar").hidden = !willShow;
  $("layoutRoot").classList.toggle("sidebar-open", willShow);
  $("sidebarToggle").setAttribute("aria-expanded", String(willShow));
});

// ------------------------------------------------------- details toggle --
$("detailsToggle").addEventListener("click", () => {
  const el = $("resultSection");
  el.hidden = !el.hidden;
  $("detailsToggle").textContent = el.hidden ? "🔍 Show what's happening under the hood" : "🔼 Hide details";
});

// -------------------------------------------------------------- modality --
// Driven by: the "use a gesture / type instead" links, and voice-driven
// "switch modality" recovery. Each mode has exactly one obvious next
// action -- tap the orb, show a gesture, or type and send -- no separate
// enable/arm step before that action is available.
function setMode(mode) {
  state.mode = mode;
  ["mic", "camera", "text"].forEach((m) => {
    $(`stage-${m}`).hidden = m !== mode;
  });
  document.querySelectorAll("#convoAltRow [data-switch]").forEach((btn) => {
    btn.hidden = btn.dataset.switch === mode;
  });
  if (mode === "camera") startGestureCapture();
  else if (mode === "text") $("convoTextInput").focus();
  else setOrbState("idle");
}

document.querySelectorAll("#convoAltRow [data-switch]").forEach((btn) => {
  btn.addEventListener("click", () => setMode(btn.dataset.switch));
});

// --------------------------------------------------------- mic recording --
// One tap starts listening. It stops on its own after a generous silence
// window -- generous on purpose: this app exists partly to handle speech
// with long pauses and repeated sounds (FR-03), so an aggressive "stop as
// soon as it goes quiet" timeout would clip off the exact speech pattern
// we're supposed to support. A second tap always stops it manually too.
const SILENCE_RMS_THRESHOLD = 0.02;
const SILENCE_GRACE_MS = 5000;
const MAX_RECORD_MS = 25000;

let _silenceCtx = null;
let _silenceRAF = null;

function startSilenceWatch(stream, onTimeout) {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return; // no Web Audio support -- MAX record cap / manual tap still stop it
  _silenceCtx = new AudioCtx();
  const source = _silenceCtx.createMediaStreamSource(stream);
  const analyser = _silenceCtx.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);
  const data = new Float32Array(analyser.fftSize);
  const startedAt = Date.now();
  let lastLoudAt = startedAt;
  let hasSpokenYet = false;

  function tick() {
    analyser.getFloatTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
    const rms = Math.sqrt(sum / data.length);
    const now = Date.now();
    if (rms > SILENCE_RMS_THRESHOLD) {
      lastLoudAt = now;
      hasSpokenYet = true;
    }
    if (hasSpokenYet && now - lastLoudAt > SILENCE_GRACE_MS) return onTimeout();
    if (now - startedAt > MAX_RECORD_MS) return onTimeout();
    _silenceRAF = requestAnimationFrame(tick);
  }
  _silenceRAF = requestAnimationFrame(tick);
}

function stopSilenceWatch() {
  if (_silenceRAF) cancelAnimationFrame(_silenceRAF);
  _silenceRAF = null;
  if (_silenceCtx) {
    _silenceCtx.close();
    _silenceCtx = null;
  }
}

function setOrbState(s) {
  const orb = $("talkOrb");
  orb.classList.remove("listening", "processing");
  if (s === "listening") {
    orb.classList.add("listening");
    $("orbCaption").textContent = "Listening… tap again when you're done";
  } else if (s === "processing") {
    orb.classList.add("processing");
    $("orbCaption").textContent = "Working on it…";
  } else {
    $("orbCaption").textContent = "Tap to talk";
  }
}

async function startMicCapture() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.micStream = stream;
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      stopSilenceWatch();
      stream.getTracks().forEach((t) => t.stop());
      state.micBlob = new Blob(chunks, { type: "audio/webm" });
      runPipeline({ audioBlob: state.micBlob });
    };
    recorder.start();
    state.micRecorder = recorder;
    setOrbState("listening");
    startSilenceWatch(stream, () => {
      if (recorder.state === "recording") recorder.stop();
    });
  } catch (err) {
    showFallbackBanner(`Microphone access failed: ${err.message}`);
  }
}

$("talkOrb").addEventListener("click", () => {
  if (state.micRecorder && state.micRecorder.state === "recording") {
    state.micRecorder.stop(); // manual stop, always available
    return;
  }
  setMode("mic");
  startMicCapture();
});

// ------------------------------------------------------------ camera/gesture --
// One action ("use a gesture instead") opens the camera and captures on a
// short countdown automatically -- no separate enable/capture/run clicks.
async function startGestureCapture() {
  $("gestureCountdown").textContent = "Starting camera…";
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    state.cameraStream = stream;
    $("convoCameraPreview").srcObject = stream;
    runGestureCountdown();
  } catch (err) {
    showFallbackBanner(`Camera access failed: ${err.message}`);
  }
}

function runGestureCountdown() {
  let n = 3;
  $("gestureCountdown").textContent = `Hold your gesture… capturing in ${n}`;
  const timer = setInterval(() => {
    n -= 1;
    if (n <= 0) {
      clearInterval(timer);
      captureGestureFrame();
    } else {
      $("gestureCountdown").textContent = `Hold your gesture… capturing in ${n}`;
    }
  }, 1000);
}

function captureGestureFrame() {
  const video = $("convoCameraPreview");
  const canvas = $("convoCameraCanvas");
  canvas.width = video.videoWidth || 320;
  canvas.height = video.videoHeight || 240;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.toBlob((blob) => {
    state.gestureBlob = blob;
    if (state.cameraStream) state.cameraStream.getTracks().forEach((t) => t.stop());
    runPipeline({ imageBlob: blob });
  }, "image/jpeg");
}

// ---------------------------------------------------------------- text --
$("convoTextSend").addEventListener("click", () => {
  const text = $("convoTextInput").value.trim();
  if (!text) return;
  runPipeline({ text });
  $("convoTextInput").value = "";
});
$("convoTextInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("convoTextSend").click();
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

// ------------------------------------------------- humanized status ticker --
// /api/run is a single blocking call -- there's no live per-stage progress
// feed (that would need websockets/SSE, out of scope tonight). This ticker
// is a best-effort, timer-driven approximation so the wait feels like
// something is happening rather than a dead spinner; it is NOT wired to
// real server-side stage completion. The real per-stage timings are shown
// afterwards in the (opt-in) latency panel, which is accurate.
const STATUS_PHRASES = [
  "Got it, one moment…",
  "Understanding what you said…",
  "Checking what I can do about that…",
  "Putting together a response…",
];
let _tickerInterval = null;

function startStatusTicker() {
  const el = $("convoStatus");
  el.hidden = false;
  let i = 0;
  el.textContent = STATUS_PHRASES[0];
  _tickerInterval = setInterval(() => {
    i = (i + 1) % STATUS_PHRASES.length;
    el.textContent = STATUS_PHRASES[i];
  }, 2200);
}

function stopStatusTicker() {
  if (_tickerInterval) clearInterval(_tickerInterval);
  _tickerInterval = null;
  $("convoStatus").hidden = true;
}

// ------------------------------------------------------------------ run --
async function runPipeline({ audioBlob = null, imageBlob = null, text = null }) {
  state.lastRun = { audioBlob, imageBlob, text };
  $("fallbackBanner").hidden = true;
  if (state.mode === "mic") setOrbState("processing");
  if (state.mode !== "text") speakText("Got it, one moment.", null);
  startStatusTicker();
  try {
    const form = new FormData();
    if (audioBlob) form.append("audio", audioBlob, "input.webm");
    if (imageBlob) form.append("image", imageBlob, "input.jpg");
    if (text) form.append("text", text);
    const res = await fetch("/api/run", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    const result = await res.json();
    state.lastResult = result;
    renderResult(result);
    renderCost(result.cost);
    renderLatency(result);
  } catch (err) {
    showFallbackBanner(`Something went wrong: ${err.message}`);
    speakText("Sorry, something went wrong. Please try again.", null);
  } finally {
    stopStatusTicker();
    if (state.mode === "mic") setOrbState("idle");
  }
}

function showFallbackBanner(msg) {
  const el = $("fallbackBanner");
  el.textContent = msg;
  el.hidden = false;
}

// -------------------------------------------------------------- render --
function renderResult(r) {
  $("detailsToggle").hidden = false;

  if (r.used_fallback_cache) {
    showFallbackBanner(`Using a cached example response — live processing failed (${r.fallback_reason}).`);
  }

  // ---- primary, conversational view --------------------------------
  $("convoResult").hidden = false;
  $("convoHeard").textContent = `I heard: "${r.original_input.text}"`;
  $("convoResponse").textContent = r.final_response.text;
  $("captionLine").textContent = r.visual_equivalent.caption;
  $("actionPreview").textContent = r.visual_equivalent.action_preview;

  const clarify = $("clarifyingQuestion");
  if (r.accent_noise_report.clarifying_question) {
    clarify.textContent = `Clarifying question: ${r.accent_noise_report.clarifying_question}`;
    clarify.hidden = false;
  } else {
    clarify.hidden = true;
  }

  renderRecovery(r.recovery_options, r.original_input.confidence * 100, r.accessibility_report.barriers_detected);
  $("confirmedBanner").hidden = true;
  $("correctPanel").hidden = true;
  $("recoveryListenStatus").textContent = "";

  // ---- secondary, technical detail view (collapsed by default) ------
  $("originalInputOut").value = r.original_input.text;
  $("accessibleTranscriptOut").value = r.accessible_transcript.text;
  $("modalityConfidence").textContent =
    `Modality: ${r.original_input.modality} · Confidence: ${Math.round(r.original_input.confidence * 100)}%`;

  fillList("barriersList", r.accessibility_report.barriers_detected);
  fillList("supportList", r.accessibility_report.support_applied);

  const langLine = $("languagesLine");
  if (r.language_report.code_mixed) {
    langLine.textContent = `Languages detected: ${r.language_report.languages_detected.join(", ")}`;
    langLine.hidden = false;
  } else {
    langLine.hidden = true;
  }

  renderDetectionEvidence(r.disfluency_report, r.language_report);

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

  $("ragSummary").textContent = `View retrieved context (${r.retrieved_context.length} snippets)`;
  const ragEl = $("ragContext");
  ragEl.innerHTML = "";
  r.retrieved_context.forEach((s) => {
    const div = document.createElement("div");
    div.innerHTML = `<strong>${s.title}</strong> <span class="muted">(${s.source})</span><p>${s.content}</p>`;
    ragEl.appendChild(div);
  });

  renderAgentTrace(r.agent_result);

  // ---- voice output ---------------------------------------------------
  // Speak the response (or clarifying question) in the language the user
  // actually used, if a matching voice exists. Voice-driven recovery is on
  // by default -- the whole point of a voice-first tool is that the voice
  // controls the interface, not the other way around -- but stays an easy
  // opt-out for anyone who'd rather always tap a button.
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

// Raw detector output -- the actual evidence behind the "speech_impairment" /
// "multilingual_code_mixing" barrier labels shown above, not just the
// synthesized conclusion. Matters for demo credibility: shows the detector
// really found something specific, not a vague category.
function renderDetectionEvidence(disfluency, language) {
  const rows = [];
  rows.push(`Has disfluency: ${disfluency.has_disfluency}`);
  if (disfluency.repeated_syllables.length) rows.push(`Repeated syllables: ${disfluency.repeated_syllables.join(", ")}`);
  if (disfluency.repeated_words.length) rows.push(`Repeated words: ${disfluency.repeated_words.join(", ")}`);
  if (disfluency.filler_words_found.length) rows.push(`Filler words: ${disfluency.filler_words_found.join(", ")}`);
  if (disfluency.long_pause_markers) rows.push(`Long pause markers: ${disfluency.long_pause_markers}`);
  if (language.romanized_markers.length) rows.push(`Language markers: ${language.romanized_markers.join(", ")}`);
  $("detectionEvidence").innerHTML = rows.map((r) => `<div>${r}</div>`).join("");
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

function renderRecovery(recovery, confidencePct, barriers) {
  const container = $("recoveryButtons");
  container.innerHTML = "";
  recovery.options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-pill";
    btn.textContent = RECOVERY_LABELS[opt] || opt;
    btn.addEventListener("click", () => handleRecoveryAction(opt));
    container.appendChild(btn);
  });

  const explainer = $("recoveryExplainer");
  if (recovery.needs_confirmation) {
    explainer.className = "banner banner-warning";
    explainer.innerHTML = `<strong>Please review before continuing.</strong> ${explainWhyReviewIsNeeded(confidencePct, barriers, recovery.reason)}`;
  } else {
    explainer.className = "banner banner-success";
    explainer.textContent = "This looks good — tap Confirm to proceed, or use another option if something's off.";
  }
}

// Turns the recovery decision into a specific, plain-language reason
// instead of a bare "confirmation requested" -- so it's clear WHY, not
// just that a tap is required.
function explainWhyReviewIsNeeded(confidencePct, barriers, fallbackReason) {
  const parts = [];
  if (confidencePct < 60) {
    parts.push(`speech confidence was only ${Math.round(confidencePct)}% (often background noise, an accent, or unclear audio)`);
  }
  if (barriers.includes("speech_impairment")) parts.push("a disfluency (repeated words/sounds) was detected and cleaned up");
  if (barriers.includes("multilingual_code_mixing")) parts.push("mixed languages were detected");
  if (barriers.includes("noise_or_accent_uncertainty") && confidencePct >= 60) parts.push("the system wasn't fully certain it heard you correctly");
  if (barriers.includes("sign_or_gesture_interaction")) parts.push("a gesture was interpreted, not spoken words");
  if (!parts.length) parts.push(fallbackReason || "the system wants to double-check before acting");
  return "Why: " + parts.join("; ") + ".";
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
// tap. On by default (see #voiceRecoveryToggle) -- voice should control the
// interface, not the other way around -- but it's a one-tap opt-out for
// anyone who'd rather always use the buttons.
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
