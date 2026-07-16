import json
import os
from dataclasses import dataclass
from typing import Optional

from src import config

# Predefined gesture vocabulary -> candidate intent (FR-14, "prototype-level
# gesture/sign capture through webcam with predefined demo gestures" per the
# PRD's own MVP scope table -- this is deliberately not general sign
# language recognition).
GESTURE_INTENT_MAP = {
    "thumbs_up": "confirm",
    "open_palm": "request_help",
    "fist": "correct_or_cancel",
    "pointing": "select",
    "peace": "switch_modality",
}


@dataclass
class GestureResult:
    gesture: Optional[str]
    confidence: float
    candidate_intent: Optional[str]


class VisionBackend:
    def interpret(self, image_path: str) -> GestureResult:
        raise NotImplementedError


class MockVisionBackend(VisionBackend):
    """
    Dev backend for environments with no camera/model access. Reads a
    sibling .json file next to the image describing the intended gesture,
    e.g. sample.jpg -> sample.json = {"gesture": "thumbs_up"}, so the rest
    of the pipeline is testable before real gesture detection is wired in.
    """

    def interpret(self, image_path: str) -> GestureResult:
        meta_path = os.path.splitext(image_path)[0] + ".json"
        with open(meta_path) as f:
            data = json.load(f)
        gesture = data.get("gesture")
        return GestureResult(
            gesture=gesture,
            confidence=data.get("confidence", 0.8),
            candidate_intent=GESTURE_INTENT_MAP.get(gesture),
        )


_HAND_LANDMARKER_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
)
_MODEL_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".mediapipe_models")
_MODEL_CACHE_PATH = os.path.join(_MODEL_CACHE_DIR, "hand_landmarker.task")


def _ensure_hand_landmarker_model() -> str:
    """
    Downloads the HandLandmarker model bundle on first use (needs real
    internet -- won't work in an offline/sandboxed dev environment, same
    caveat as faster-whisper's Hugging Face download). Cached locally after
    that so it's a one-time cost.
    """
    if os.path.exists(_MODEL_CACHE_PATH):
        return _MODEL_CACHE_PATH
    import urllib.request

    os.makedirs(_MODEL_CACHE_DIR, exist_ok=True)
    urllib.request.urlretrieve(_HAND_LANDMARKER_MODEL_URL, _MODEL_CACHE_PATH)
    return _MODEL_CACHE_PATH


class MediaPipeVisionBackend(VisionBackend):
    """
    Real hand-landmark detection via MediaPipe's Tasks API (HandLandmarker),
    classified against a small predefined gesture set using finger-extension
    geometry. This is a genuine (if intentionally scoped-down)
    implementation of FR-14 -- not a full sign-language recognizer, matching
    the PRD's MVP scope.

    Uses the newer mediapipe.tasks Hand Landmarker API, NOT the old
    mp.solutions.hands API -- that "Solutions" API was removed from the
    mediapipe package entirely as of the version on PyPI when this was
    written (confirmed: `mp.solutions` and `mediapipe.solutions` both raise
    AttributeError/ModuleNotFoundError on mediapipe 0.10.35). If this
    breaks again on a future mediapipe release, check the installed
    version's actual API surface with `python -c "import mediapipe as mp;
    print(dir(mp))"` before assuming the old code was right.

    Works on a single still frame (matches Streamlit's st.camera_input,
    which captures a snapshot rather than a continuous stream). Continuous
    real-time video would need streamlit-webrtc, out of scope for the MVP.
    """

    # MediaPipe Hands landmark indices (unchanged between the old Solutions
    # API and the new Tasks API -- same 21-point hand topology either way).
    _TIP = {"thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20}
    _PIP = {"index": 6, "middle": 10, "ring": 14, "pinky": 18}
    _THUMB_IP = 3
    _WRIST = 0

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        self._mp = mp
        model_path = _ensure_hand_landmarker_model()
        base_options = mp_python.BaseOptions(model_asset_path=model_path)
        options = mp_vision.HandLandmarkerOptions(base_options=base_options, num_hands=1, min_hand_detection_confidence=0.5)
        self._landmarker = mp_vision.HandLandmarker.create_from_options(options)

    def _extended_fingers(self, landmarks) -> dict:
        def dist(a, b):
            return ((landmarks[a].x - landmarks[b].x) ** 2 + (landmarks[a].y - landmarks[b].y) ** 2) ** 0.5

        extended = {
            "thumb": dist(self._TIP["thumb"], self._WRIST) > dist(self._THUMB_IP, self._WRIST),
        }
        for finger in ("index", "middle", "ring", "pinky"):
            # Tip above (smaller y than) the PIP joint => extended, in
            # normalized image coordinates where y grows downward.
            extended[finger] = landmarks[self._TIP[finger]].y < landmarks[self._PIP[finger]].y
        return extended

    def _classify(self, extended: dict) -> Optional[str]:
        count = sum(extended.values())
        if count == 5:
            return "open_palm"
        if count == 0:
            return "fist"
        if extended["thumb"] and count == 1:
            return "thumbs_up"
        if extended["index"] and not extended["middle"] and not extended["ring"] and not extended["pinky"]:
            return "pointing"
        if extended["index"] and extended["middle"] and not extended["ring"] and not extended["pinky"]:
            return "peace"
        return None

    def interpret(self, image_path: str) -> GestureResult:
        import cv2

        image = cv2.imread(image_path)
        if image is None:
            return GestureResult(gesture=None, confidence=0.0, candidate_intent=None)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)
        if not result.hand_landmarks:
            return GestureResult(gesture=None, confidence=0.0, candidate_intent=None)
        landmarks = result.hand_landmarks[0]
        extended = self._extended_fingers(landmarks)
        gesture = self._classify(extended)
        confidence = 0.75 if gesture else 0.3
        return GestureResult(gesture=gesture, confidence=confidence, candidate_intent=GESTURE_INTENT_MAP.get(gesture))


def get_vision_backend() -> VisionBackend:
    if config.VISION_BACKEND == "local":
        return MediaPipeVisionBackend()
    return MockVisionBackend()


def start_live_camera_capture(optional: bool = True):
    """
    Placeholder matching the PRD's Appendix A pseudocode name. Actual
    capture happens via st.camera_input in app.py (browser webcam
    snapshot) -- this function exists so pipeline.py reads the same way
    the PRD pseudocode does.
    """
    raise NotImplementedError("Live capture happens via st.camera_input in app.py, not here.")


def interpret_sign_or_gesture(image_path: Optional[str]) -> Optional[GestureResult]:
    """Alias matching the PRD's Appendix A naming. video_stream is optional
    per FR-14/FR-15 (multimodal fallback) -- returns None if no image was
    captured this turn."""
    if not image_path:
        return None
    return get_vision_backend().interpret(image_path)
