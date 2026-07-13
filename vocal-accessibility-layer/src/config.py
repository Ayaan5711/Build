import os

# Backend selection. Each defaults to "mock" so the pipeline runs anywhere
# with zero external dependencies; switch via env vars once real access
# (Ollama, or the genailab.tcs.in event endpoint) is available.
ASR_BACKEND = os.getenv("ASR_BACKEND", "mock")  # mock | local | event
LLM_BACKEND = os.getenv("LLM_BACKEND", "mock")  # mock | ollama | event
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "mock")  # mock | event

# Event-day (genailab.tcs.in) settings -- key is handed out on match day.
GENAILAB_BASE_URL = os.getenv("GENAILAB_BASE_URL", "https://genailab.tcs.in")
GENAILAB_API_KEY = os.getenv("GENAILAB_API_KEY", "")
GENAILAB_CHAT_MODEL = os.getenv("GENAILAB_CHAT_MODEL", "azure_ai/genailab-maas-DeepSeek-V3-0324")
GENAILAB_ASR_MODEL = os.getenv("GENAILAB_ASR_MODEL", "azure/genailab-maas-whisper")
GENAILAB_EMBED_MODEL = os.getenv("GENAILAB_EMBED_MODEL", "azure/genailab-maas-text-embedding-3-large")

# Local dev backends (match the lab laptops' offline stack).
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
WHISPER_LOCAL_MODEL = os.getenv("WHISPER_LOCAL_MODEL", "base")

# Below this ASR confidence, the guardrail should require user confirmation
# before a skill's action is treated as final.
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", ".chroma")
