import shutil
import subprocess
import tempfile
from typing import Optional

from src import config


class TTSBackend:
    def speak(self, text: str) -> Optional[bytes]:
        raise NotImplementedError


class MockTTSBackend(TTSBackend):
    """No-op -- returns no audio. Default, so the pipeline needs zero
    system dependencies until TTS_BACKEND=local is enabled."""

    def speak(self, text: str) -> Optional[bytes]:
        return None


class EspeakTTSBackend(TTSBackend):
    """
    Offline text-to-speech via espeak-ng. This is the "Text -> Voice
    output" alternative PAS 901's Adapt principle calls for. Degrades to
    no audio (with a warning) instead of crashing if espeak-ng isn't
    installed on the machine -- it wasn't in the hackathon's preinstalled
    software list, so this may need `apt-get install espeak-ng` on the lab
    laptop, or can simply be left off (TTS_BACKEND=mock).
    """

    def __init__(self):
        if shutil.which("espeak-ng") is None:
            raise RuntimeError(
                "TTS_BACKEND=local requires the 'espeak-ng' binary on PATH "
                "(e.g. `apt-get install espeak-ng`). Falls back to TTS_BACKEND=mock "
                "(no spoken output) if unavailable."
            )

    def speak(self, text: str) -> Optional[bytes]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name
        subprocess.run(["espeak-ng", "-w", out_path, text], check=True, capture_output=True)
        with open(out_path, "rb") as f:
            return f.read()


def get_tts_backend() -> TTSBackend:
    if config.TTS_BACKEND == "local":
        return EspeakTTSBackend()
    return MockTTSBackend()
