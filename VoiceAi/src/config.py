import os

from dotenv import load_dotenv

load_dotenv()

# --- Backend selection ---------------------------------------------------
# Every stage defaults to "mock" so the full pipeline is buildable and
# testable with zero network access, zero API key, and no microphone/camera
# hardware. Flip these via .env once real access exists -- no code changes.
ASR_BACKEND = os.getenv("ASR_BACKEND", "mock")  # mock | local | event
VISION_BACKEND = os.getenv("VISION_BACKEND", "mock")  # mock | local (MediaPipe Hands)
LLM_BACKEND = os.getenv("LLM_BACKEND", "mock")  # mock | ollama | event
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "mock")  # mock | ollama | event
TTS_BACKEND = os.getenv("TTS_BACKEND", "mock")  # mock | local (espeak-ng, offline, optional)

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
