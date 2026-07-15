import os

from dotenv import load_dotenv

load_dotenv()

# Backend selection. Each defaults to "mock" so the pipeline runs anywhere
# with zero external dependencies; switch via env vars once real access
# (Ollama, or the genailab.tcs.in event endpoint) is available.
ASR_BACKEND = os.getenv("ASR_BACKEND", "mock")  # mock | local | event
LLM_BACKEND = os.getenv("LLM_BACKEND", "mock")  # mock | ollama | event
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "mock")  # mock | ollama | event
TTS_BACKEND = os.getenv("TTS_BACKEND", "mock")  # mock | local (espeak-ng, offline)

# Event-day (genailab.tcs.in) settings -- key is handed out on match day.
# Model names below are confirmed against the actual model list returned by
# the gateway (not just the handbook doc) -- gpt-4o-mini is the chat default
# because it follows structured-JSON instructions (Orchestrator/Guardrail
# depend on this) more reliably than DeepSeek in practice. Swap
# GENAILAB_CHAT_MODEL to try azure/genailab-maas-gpt-4.1,
# genailab-maas-DeepSeek-V3-0324, or azure_ai/genailab-maas-Llama-3.3-70B-Instruct
# if you want to compare quality once things are working.
GENAILAB_BASE_URL = os.getenv("GENAILAB_BASE_URL", "https://genailab.tcs.in")
GENAILAB_API_KEY = os.getenv("GENAILAB_API_KEY", "")
GENAILAB_CHAT_MODEL = os.getenv("GENAILAB_CHAT_MODEL", "azure/genailab-maas-gpt-4o-mini")
GENAILAB_ASR_MODEL = os.getenv("GENAILAB_ASR_MODEL", "azure/genailab-maas-whisper")
GENAILAB_EMBED_MODEL = os.getenv("GENAILAB_EMBED_MODEL", "azure/genailab-maas-text-embedding-3-large")

# Local dev / lab-laptop offline backends. Model name confirmed against a
# real `ollama list` on the lab hardware -- it is "llama-3.2-3b-it:latest",
# NOT "llama3.2:3b" (that tag doesn't exist on these machines and the call
# would fail). Other locally pulled models seen: qwen-2.5.1-coder-it,
# gemma-3-4b-it, deepseek-r1, gte-large (embeddings), devstral.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama-3.2-3b-it:latest")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "gte-large:latest")
WHISPER_LOCAL_MODEL = os.getenv("WHISPER_LOCAL_MODEL", "base")

# Below this ASR confidence, the guardrail should require user confirmation
# before a skill's action is treated as final.
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", ".chroma")
