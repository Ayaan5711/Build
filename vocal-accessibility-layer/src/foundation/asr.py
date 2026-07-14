import os
from dataclasses import dataclass, field
from typing import List

from src import config


@dataclass
class TranscriptSegment:
    text: str
    confidence: float  # 0-1


@dataclass
class ASRResult:
    text: str
    confidence: float
    segments: List[TranscriptSegment] = field(default_factory=list)


class ASRBackend:
    def transcribe(self, audio_path: str) -> ASRResult:
        raise NotImplementedError


class MockASRBackend(ASRBackend):
    """
    Dev backend for environments with no audio/model access. Reads a
    transcript from a sibling .txt file next to the audio, so the rest of
    the pipeline (Equalizer, Normalizer, Orchestrator, Guardrail) can be
    built and tested before real ASR is wired in.
    """

    def transcribe(self, audio_path: str) -> ASRResult:
        transcript_path = os.path.splitext(audio_path)[0] + ".txt"
        with open(transcript_path) as f:
            text = f.read().strip()
        return ASRResult(text=text, confidence=0.75, segments=[TranscriptSegment(text, 0.75)])


class LocalWhisperBackend(ASRBackend):
    """
    Runs faster-whisper locally (offline, matches the lab laptops' stack).
    Requires model weights to be downloaded once (needs Hugging Face
    access) before this will work.
    """

    def __init__(self, model_size: str = None):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model_size or config.WHISPER_LOCAL_MODEL, device="cpu", compute_type="int8")

    def transcribe(self, audio_path: str) -> ASRResult:
        segments, _info = self.model.transcribe(audio_path)
        segs = []
        for seg in segments:
            # avg_logprob is a log-probability; convert to an approximate
            # 0-1 confidence for the transparency layer.
            approx_conf = float(min(1.0, max(0.0, 2**seg.avg_logprob)))
            segs.append(TranscriptSegment(seg.text.strip(), approx_conf))
        text = " ".join(s.text for s in segs)
        avg_conf = sum(s.confidence for s in segs) / len(segs) if segs else 0.0
        return ASRResult(text=text, confidence=avg_conf, segments=segs)


class GenAILabASRBackend(ASRBackend):
    """Event-day backend: calls the hackathon-provided Whisper endpoint."""

    def __init__(self):
        import httpx

        if not config.GENAILAB_API_KEY:
            raise RuntimeError(
                "ASR_BACKEND=event requires GENAILAB_API_KEY to be set (in .env or the "
                "environment) -- this is the key handed out on match day."
            )
        self.client = httpx.Client(verify=False)

    def transcribe(self, audio_path: str) -> ASRResult:
        with open(audio_path, "rb") as f:
            resp = self.client.post(
                f"{config.GENAILAB_BASE_URL}/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {config.GENAILAB_API_KEY}"},
                files={"file": f},
                data={"model": config.GENAILAB_ASR_MODEL},
            )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("text", "")
        # The transcription endpoint may not return confidence; default to
        # a neutral value rather than fabricating precision.
        confidence = data.get("confidence", 0.85)
        return ASRResult(text=text, confidence=confidence, segments=[TranscriptSegment(text, confidence)])


def get_asr_backend() -> ASRBackend:
    if config.ASR_BACKEND == "local":
        return LocalWhisperBackend()
    if config.ASR_BACKEND == "event":
        return GenAILabASRBackend()
    return MockASRBackend()
