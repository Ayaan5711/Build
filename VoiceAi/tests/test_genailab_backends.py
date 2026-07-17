"""
Tests for the hosted (event-day) genailab.tcs.in backends -- ASR, LLM, and
embeddings. No real network calls: a custom httpx transport intercepts the
outgoing request and raises before anything is actually sent, so these
tests verify the exact URL/headers/body being constructed, deterministically
and offline.

Context for the LLM backend test specifically: a real ReadTimeout on the
lab network turned out to have two independent causes. (1) httpx.Client()
defaults to a 5s timeout when none is given -- too short for real hosted
inference -- fixed by passing config.GENAILAB_TIMEOUT_S explicitly
everywhere. (2) GenAILabLLMBackend used to delegate URL construction to
langchain_openai's ChatOpenAI, which built requests against
"{base_url}/chat/completions" with "Authorization: Bearer <key>" -- but a
real curl test directly against the gateway's own API docs proved the
actual working route is "/litellm/openai/deployments/<model>/
chat/completions" with an "x-litellm-api-key" header instead. Fixed by
calling the endpoint directly via httpx with the proven request shape.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import pytest

from src import config


class _CaptureTransport(httpx.BaseTransport):
    """Records the outgoing request and raises instead of sending it, so
    these tests never touch a real network -- deterministic and offline,
    same guarantee as the rest of this suite."""

    def __init__(self):
        self.request = None

    def handle_request(self, request):
        self.request = request
        raise RuntimeError("intercepted before send -- test transport, not a real failure")


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    monkeypatch.setattr(config, "GENAILAB_API_KEY", "sk-test-key-123")


def test_genailab_llm_backend_hits_the_proven_working_url_and_header(monkeypatch):
    from src.llm import GenAILabLLMBackend

    backend = GenAILabLLMBackend(role="cleanup")
    capture = _CaptureTransport()
    backend.client = httpx.Client(transport=capture)

    with pytest.raises(RuntimeError, match="intercepted"):
        backend.complete("system prompt", "user message", task="cleanup")

    req = capture.request
    assert req is not None
    # Exactly the route confirmed working via a direct curl test against
    # the gateway's own API docs -- NOT "{base}/chat/completions" (what
    # langchain_openai's ChatOpenAI used to build), which is a different,
    # non-working route on this specific LiteLLM proxy.
    assert str(req.url) == "https://genailab.tcs.in/litellm/openai/deployments/azure%2Fgenailab-maas-gpt-4o-mini/chat/completions"
    assert req.headers["x-litellm-api-key"] == "sk-test-key-123"
    assert "authorization" not in req.headers


def test_genailab_llm_backend_url_encodes_the_model_name(monkeypatch):
    """The model name contains a literal '/' (e.g. "azure/genailab-maas-
    gpt-4o") which must be percent-encoded as part of the URL path segment,
    not left as a literal slash (which would change the path structure)."""
    from src.llm import GenAILabLLMBackend

    backend = GenAILabLLMBackend(role="response")  # azure/genailab-maas-gpt-4o
    capture = _CaptureTransport()
    backend.client = httpx.Client(transport=capture)

    with pytest.raises(RuntimeError):
        backend.complete("s", "u")

    assert "azure%2Fgenailab-maas-gpt-4o" in str(capture.request.url)
    assert "/azure/genailab-maas-gpt-4o/" not in str(capture.request.url)


def test_genailab_clients_have_an_explicit_generous_timeout_not_httpxs_default():
    """httpx.Client() defaults to 5s if no timeout is given -- too short
    for real hosted inference. Every genailab.tcs.in client must set one
    explicitly (regression lock for the real ReadTimeout this caused)."""
    from src.input.microphone import GenAILabASRBackend
    from src.knowledge.embeddings import GenAILabEmbeddingFunction
    from src.llm import GenAILabLLMBackend

    asr = GenAILabASRBackend()
    # ASR gets its own longer read timeout (see config.GENAILAB_ASR_TIMEOUT_S)
    # -- a real log showed transcription itself hanging the full 60s ceiling,
    # not some later stage. Connect stays short so a dead endpoint fails fast.
    assert asr.client.timeout.read == config.GENAILAB_ASR_TIMEOUT_S
    assert asr.client.timeout.read > config.GENAILAB_TIMEOUT_S
    assert asr.client.timeout.connect == 10.0

    embed = GenAILabEmbeddingFunction()
    assert embed.client.timeout.read == config.GENAILAB_TIMEOUT_S
    assert embed.client.timeout.read > 5.0

    llm = GenAILabLLMBackend(role="cleanup")
    assert llm.client.timeout.read == config.GENAILAB_TIMEOUT_S
    assert llm.client.timeout.read > 5.0


def test_genailab_asr_backend_still_uses_the_v1_path_with_bearer_auth():
    """Unlike chat completions, this exact request shape (/v1/audio/
    transcriptions + Authorization: Bearer) mirrors the embeddings call
    that was directly confirmed working (200 OK) on the real gateway in a
    live server log -- no evidence this path itself is wrong, so it's left
    unchanged. Only the missing timeout was the proven bug here."""
    from src.input.microphone import GenAILabASRBackend

    backend = GenAILabASRBackend()
    capture = _CaptureTransport()
    backend.client = httpx.Client(transport=capture)

    with pytest.raises(RuntimeError, match="intercepted"):
        backend.transcribe(__file__)  # any real file works, content unused before intercept

    req = capture.request
    assert str(req.url) == f"{config.GENAILAB_BASE_URL}/v1/audio/transcriptions"
    assert req.headers["authorization"] == f"Bearer sk-test-key-123"
