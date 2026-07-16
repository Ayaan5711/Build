"""
Tests for the real MediaPipe Hands gesture backend (FR-14). These need
actual system graphics libraries (libGLESv2/libEGL) and internet access
(to download the HandLandmarker model bundle on first use) -- present on a
normal machine (including the lab laptop) but not guaranteed in every CI/
sandbox environment. The whole file skips cleanly if unavailable, so
`pytest tests/` still always passes anywhere -- this is the one place in
the suite that exercises a real (non-mock) heavy backend end to end,
rather than mocking it away.

Regression context: mediapipe removed the old `mp.solutions.hands` API
entirely as of the version on PyPI when this was written (0.10.35) --
`MediaPipeVisionBackend` was rewritten to use the newer `mediapipe.tasks`
HandLandmarker API instead. Found via live testing on real hardware.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _mediapipe_vision_available():
    try:
        from src.input.vision import MediaPipeVisionBackend

        MediaPipeVisionBackend()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _mediapipe_vision_available(),
    reason="MediaPipe HandLandmarker unavailable (missing graphics libs, no internet for the model download, or the download failed)",
)


@pytest.fixture(scope="module")
def backend():
    from src.input.vision import MediaPipeVisionBackend

    return MediaPipeVisionBackend()


def test_blank_image_reports_no_gesture(tmp_path, backend):
    import cv2
    import numpy as np

    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    path = str(tmp_path / "blank.jpg")
    cv2.imwrite(path, blank)
    result = backend.interpret(path)
    assert result.gesture is None
    assert result.confidence == 0.0
    assert result.candidate_intent is None


def test_missing_image_file_handled_gracefully(tmp_path, backend):
    result = backend.interpret(str(tmp_path / "does_not_exist.jpg"))
    assert result.gesture is None
    assert result.confidence == 0.0


def test_gesture_classifier_logic(backend):
    """The finger-extension -> gesture mapping is pure geometry logic;
    exercising it directly (not through a real detected hand) confirms the
    classification table itself is still correct after the API rewrite."""
    assert backend._classify({"thumb": True, "index": False, "middle": False, "ring": False, "pinky": False}) == "thumbs_up"
    assert backend._classify({"thumb": True, "index": True, "middle": True, "ring": True, "pinky": True}) == "open_palm"
    assert backend._classify({"thumb": False, "index": False, "middle": False, "ring": False, "pinky": False}) == "fist"
    assert backend._classify({"thumb": False, "index": True, "middle": False, "ring": False, "pinky": False}) == "pointing"
    assert backend._classify({"thumb": False, "index": True, "middle": True, "ring": False, "pinky": False}) == "peace"
