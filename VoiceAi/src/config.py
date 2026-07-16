import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _valid_env(env_key: str, valid_values: set, default: str) -> str:
    """
    Reads an env var, but falls back to `default` (with a loud warning) if
    the raw value isn't one of the recognized options.

    Real bug this guards against: python-dotenv does NOT strip a trailing
    "# comment" on a line whose value is blank (e.g. "KEY=   # mock | local"
    parses as KEY="# mock | local", the ENTIRE comment) -- it only strips
    inline comments correctly when a real value precedes them. .env.example
    used to have exactly that pattern on blank "leave this to use the
    profile default" lines, so leaving them un-edited silently set the
    backend to a garbage string that matched nothing, which (worse) is
    *truthy*, so it could silently override profile-based per-role routing
    entirely. Any typo/stray whitespace/comment now gets caught here
    instead of being used literally.
    """
    raw = os.getenv(env_key, "").strip().lower()
    if not raw:
        return default
    if raw not in valid_values:
        print(
            f"[voiceai] WARNING: {env_key}={raw!r} is not one of {sorted(valid_values)} -- "
            f"ignoring it (likely a stray comment or typo in .env) and using {default!r} instead.",
            file=sys.stderr,
        )
        return default
    return raw

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
PROFILE = _valid_env("PROFILE", {"mock", "local", "hybrid", "fast", "hosted"}, "mock")

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
        # free on local Ollama. Cheapest live option -- but only fast enough
        # if the laptop runs Ollama acceptably; MEASURE first (see timings).
        "asr": "event", "vision": "local", "embed": "ollama", "tts": "local",
        "llm": {"cleanup": "ollama", "reasoning": "ollama", "intent": "ollama", "response": "event", "caption": "ollama"},
    },
    "fast": {
        # Everything hosted on server GPUs -> fastest live option, immune to
        # a slow laptop. Uses lightweight hosted models (see GENAILAB_MODELS
        # 'fast' defaults) and avoids the slow reasoning model. Recommended
        # for the live demo if the lab laptop is sluggish. Still only cents
        # per demo -- the budget cap protects you.
        "asr": "event", "vision": "local", "embed": "event", "tts": "local",
        "llm": {"cleanup": "event", "reasoning": "event", "intent": "event", "response": "event", "caption": "event"},
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
# Validated via _valid_env -- an invalid/garbled value (stray comment, typo)
# is ignored with a warning rather than used literally (see docstring above).
ASR_BACKEND = _valid_env("ASR_BACKEND", {"mock", "local", "event"}, _profile["asr"])
VISION_BACKEND = _valid_env("VISION_BACKEND", {"mock", "local"}, _profile["vision"])
EMBED_BACKEND = _valid_env("EMBED_BACKEND", {"mock", "ollama", "event"}, _profile["embed"])
TTS_BACKEND = _valid_env("TTS_BACKEND", {"mock", "local"}, _profile["tts"])
# LLM_BACKEND is a global fallback; per-role routing goes through
# resolve_llm_backend() below so different stages can use different backends.
# Default "" (not a profile default) is intentional -- "" means "let the
# profile decide per role", validated the same way so garbage can't leak in.
LLM_BACKEND = _valid_env("LLM_BACKEND", {"mock", "ollama", "event"}, "")


def resolve_llm_backend(role: str) -> str:
    """Which backend (mock|ollama|event) a given LLM role should use.
    Precedence: explicit per-role env var > global LLM_BACKEND override >
    active profile's per-role mapping."""
    env_key = f"LLM_BACKEND_{role.upper()}"
    per_role = _valid_env(env_key, {"mock", "ollama", "event"}, "")
    if per_role:
        return per_role
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

# Final-response model depends on profile: 'fast' uses the lightweight mini
# (server-GPU fast, cents cheap); other hosted profiles use full gpt-4o for
# top answer quality. Override either with GENAILAB_RESPONSE_MODEL.
_default_response_model = "azure/genailab-maas-gpt-4o-mini" if PROFILE == "fast" else "azure/genailab-maas-gpt-4o"

GENAILAB_MODELS = {
    # Transcript cleanup (Speech Equalizer / normalize_transcript)
    "cleanup": os.getenv("GENAILAB_CLEANUP_MODEL", "azure/genailab-maas-gpt-4o-mini"),
    # Accessibility barrier analysis + error-recovery reasoning. NOTE:
    # default is gpt-4o-mini, NOT DeepSeek-R1 -- a reasoning model emits a
    # long chain-of-thought and is the single slowest thing in the pipeline,
    # which matters on a slow laptop and in a 5-minute live demo. Barrier
    # classification and confirm/retry decisions don't need CoT. Set
    # GENAILAB_REASONING_MODEL=azure_ai/genailab-maas-DeepSeek-R1 if you
    # specifically want deeper reasoning and can afford the latency.
    "reasoning": os.getenv("GENAILAB_REASONING_MODEL", "azure/genailab-maas-gpt-4o-mini"),
    # Intent/entity/constraint extraction
    "intent": os.getenv("GENAILAB_INTENT_MODEL", "azure/genailab-maas-gpt-4o-mini"),
    # Final user-facing grounded response
    "response": os.getenv("GENAILAB_RESPONSE_MODEL", _default_response_model),
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
    # Default is the small llama, NOT local deepseek-r1: a reasoning model on
    # a CPU-only laptop can take minutes per call. Opt into deepseek-r1 via
    # OLLAMA_REASONING_MODEL only if you've measured it's fast enough.
    "reasoning": os.getenv("OLLAMA_REASONING_MODEL", "llama-3.2-3b-it:latest"),
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

# Max iterations of the agent loop per turn. Each step is one LLM call, so
# this directly bounds latency and cost -- keep it small (2-4) for a live
# demo, especially on slow hardware.
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "3"))

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
