import os

from dotenv import load_dotenv

load_dotenv()

# --- Cost profiles -------------------------------------------------------
# One switch to route every pipeline stage to the cheapest capable backend,
# because the team runs on a fixed ~$25 total budget. Ollama models are
# already installed locally (free); only Whisper ASR and (optionally) the
# final response call cost money. Individual *_BACKEND env vars below still
# override the profile per stage if you need to.
#
#   mock   -- everything offline, $0. No key, no hardware. Dev/plumbing.
#   local  -- ASR via local faster-whisper, everything else Ollama. $0,
#             fully offline. Daily dev/test driver.
#   hybrid -- ASR + final response hosted (accuracy where the judge sees
#             it), everything else local Ollama. ~cents per demo. Match day.
#   hosted -- everything hosted. Max accuracy, highest cost. Fallback if
#             Ollama misbehaves.
PROFILE = os.getenv("PROFILE", "mock").lower()

_PROFILES = {
    "mock": {
        "asr": "mock", "vision": "mock", "embed": "mock", "tts": "mock",
        "llm": {"cleanup": "mock", "reasoning": "mock", "intent": "mock", "response": "mock", "caption": "mock"},
    },
    "local": {
        "asr": "local", "vision": "local", "embed": "ollama", "tts": "local",
        "llm": {"cleanup": "ollama", "reasoning": "ollama", "intent": "ollama", "response": "ollama", "caption": "ollama"},
    },
    "hybrid": {
        # ASR + final response hosted (seen by the judge); everything else
        # free on local Ollama.
        "asr": "event", "vision": "local", "embed": "ollama", "tts": "local",
        "llm": {"cleanup": "ollama", "reasoning": "ollama", "intent": "ollama", "response": "event", "caption": "ollama"},
    },
    "hosted": {
        "asr": "event", "vision": "local", "embed": "event", "tts": "local",
        "llm": {"cleanup": "event", "reasoning": "event", "intent": "event", "response": "event", "caption": "event"},
    },
}

_profile = _PROFILES.get(PROFILE, _PROFILES["mock"])

# --- Backend selection ---------------------------------------------------
# Default from the active profile; each can still be explicitly overridden
# by its own env var (e.g. ASR_BACKEND=event) for one-off experiments.
ASR_BACKEND = os.getenv("ASR_BACKEND", _profile["asr"])  # mock | local | event
VISION_BACKEND = os.getenv("VISION_BACKEND", _profile["vision"])  # mock | local (MediaPipe Hands)
EMBED_BACKEND = os.getenv("EMBED_BACKEND", _profile["embed"])  # mock | ollama | event
TTS_BACKEND = os.getenv("TTS_BACKEND", _profile["tts"])  # mock | local (espeak-ng, offline, optional)
# LLM_BACKEND is a global fallback; per-role routing goes through
# resolve_llm_backend() below so different stages can use different backends.
LLM_BACKEND = os.getenv("LLM_BACKEND", "")


def resolve_llm_backend(role: str) -> str:
    """Which backend (mock|ollama|event) a given LLM role should use.
    Precedence: explicit per-role env var > global LLM_BACKEND override >
    active profile's per-role mapping."""
    env_key = f"LLM_BACKEND_{role.upper()}"
    if os.getenv(env_key):
        return os.getenv(env_key)
    if LLM_BACKEND:
        return LLM_BACKEND
    return _profile["llm"].get(role, "mock")

# --- genailab.tcs.in (match day) -----------------------------------------
# Key is handed out on match day. Model names below are confirmed against
# the live model list, and are split by ROLE per the PRD's model table
# (section 7.1) -- cleanup, reasoning, intent, and final response are
# deliberately different models, not one generic "the LLM".
GENAILAB_BASE_URL = os.getenv("GENAILAB_BASE_URL", "https://genailab.tcs.in")
GENAILAB_API_KEY = os.getenv("GENAILAB_API_KEY", "")
GENAILAB_ASR_MODEL = os.getenv("GENAILAB_ASR_MODEL", "azure/genailab-maas-whisper")
GENAILAB_EMBED_MODEL = os.getenv("GENAILAB_EMBED_MODEL", "azure/genailab-maas-text-embedding-3-large")

GENAILAB_MODELS = {
    # Transcript cleanup (Speech Equalizer / normalize_transcript)
    "cleanup": os.getenv("GENAILAB_CLEANUP_MODEL", "azure/genailab-maas-gpt-4o-mini"),
    # Accessibility barrier analysis + error-recovery reasoning
    "reasoning": os.getenv("GENAILAB_REASONING_MODEL", "azure_ai/genailab-maas-DeepSeek-R1"),
    # Intent/entity/constraint extraction
    "intent": os.getenv("GENAILAB_INTENT_MODEL", "azure/genailab-maas-gpt-4o-mini"),
    # Final user-facing grounded response
    "response": os.getenv("GENAILAB_RESPONSE_MODEL", "azure/genailab-maas-gpt-4o"),
    # Captions / summaries / action previews (visual equivalence)
    "caption": os.getenv("GENAILAB_CAPTION_MODEL", "azure/genailab-maas-gpt-4o-mini"),
}

# --- Local / lab-laptop offline backends ----------------------------------
# Model names confirmed against a real `ollama list` on the lab hardware --
# they do NOT match the upstream Ollama Hub tags (e.g. it's
# "llama-3.2-3b-it:latest", not "llama3.2:3b"). Re-verify with `ollama list`
# on whatever machine you're actually on before trusting these.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODELS = {
    "cleanup": os.getenv("OLLAMA_CLEANUP_MODEL", "llama-3.2-3b-it:latest"),
    "reasoning": os.getenv("OLLAMA_REASONING_MODEL", "deepseek-r1:latest"),
    "intent": os.getenv("OLLAMA_INTENT_MODEL", "llama-3.2-3b-it:latest"),
    "response": os.getenv("OLLAMA_RESPONSE_MODEL", "gemma-3-4b-it:latest"),
    "caption": os.getenv("OLLAMA_CAPTION_MODEL", "llama-3.2-3b-it:latest"),
}
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "gte-large:latest")
WHISPER_LOCAL_MODEL = os.getenv("WHISPER_LOCAL_MODEL", "base")

# --- Thresholds ------------------------------------------------------------
# Below this ASR/gesture confidence, recovery/confirmation is required
# before an action is treated as final (FR-06, FR-16).
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", ".chroma")

# --- Resilience (NFR-03) ---------------------------------------------------
# If true, and a live backend call raises, the pipeline falls back to the
# cached scenario output in data/demo_scenarios.json that best matches the
# input, instead of failing the demo outright.
FALLBACK_TO_CACHED_SCENARIOS = os.getenv("FALLBACK_TO_CACHED_SCENARIOS", "true").lower() == "true"

# --- Budget / cost tracking ------------------------------------------------
# Hard ceiling on estimated hosted spend for the whole event. When the
# running total crosses this, hosted calls are refused (the pipeline then
# falls back per FALLBACK_TO_CACHED_SCENARIOS) so a runaway loop can never
# drain the budget. Set a little under the real cap for safety margin.
BUDGET_USD_CAP = float(os.getenv("BUDGET_USD_CAP", "20.0"))
COST_LOG_PATH = os.getenv("COST_LOG_PATH", ".cost_log.json")

# Estimated USD per 1M tokens for hosted models (input, output), and per
# minute for Whisper. These are ESTIMATES for budgeting only -- genailab's
# actual billing may differ; treat the running total as a guardrail, not an
# invoice. Keyed by substring match against the model name.
COST_PER_1M_TOKENS = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-35-turbo": (0.50, 1.50),
    "deepseek": (0.50, 2.00),
    "llama": (0.20, 0.60),
    "phi": (0.10, 0.40),
    "text-embedding-3-large": (0.13, 0.0),
    "_default": (1.00, 3.00),
}
WHISPER_COST_PER_MINUTE = float(os.getenv("WHISPER_COST_PER_MINUTE", "0.006"))
