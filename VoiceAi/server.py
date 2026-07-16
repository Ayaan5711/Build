"""
FastAPI backend for the custom HTML/CSS/JS frontend. Wraps the exact same
src/pipeline.py used by the Streamlit app (app.py) -- no pipeline logic
lives here, only request/response plumbing. Both UIs can run side by side;
this one exists for full visual control over the dashboard.

Run: uvicorn server:app --host 0.0.0.0 --port 8000
"""
import dataclasses
import os
import tempfile
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src import config
from src.cost import get_cost_tracker, reset_cost_tracker
from src.input.microphone import get_asr_backend
from src.knowledge.personalization import UserMemory
from src.knowledge.rag import KnowledgeBase, seed_default_knowledge_base
from src.pipeline import run_pipeline
from src.response.recovery_intent import match_recovery_intent
from src.skills import get_skills


@asynccontextmanager
async def _lifespan(app: FastAPI):
    kb = KnowledgeBase()
    if kb.collection.count() == 0:
        seed_default_knowledge_base(kb)
    yield


app = FastAPI(title="TCS iON Voice AI API", lifespan=_lifespan)

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
_USER_ID = "demo-user"  # single-user live demo, same convention as app.py

app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")


def _cost_summary() -> dict:
    tracker = get_cost_tracker()
    return {
        "total_usd": tracker.total_usd,
        "cap_usd": config.BUDGET_USD_CAP,
        "by_stage": tracker.summary_by_stage(),
        "profile": config.PROFILE,
    }


async def _save_upload(upload: Optional[UploadFile], suffix: str) -> Optional[str]:
    if upload is None:
        return None
    data = await upload.read()
    if not data:
        return None
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


@app.get("/")
def index():
    return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))


@app.post("/api/run")
async def api_run(
    audio: Optional[UploadFile] = File(None),
    image: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
):
    """Runs the full pipeline (FR-01 through FR-20) on whichever input
    modality was provided. Returns the entire PipelineResult as JSON plus
    the current cost summary."""
    audio_path = None
    image_path = None
    try:
        audio_path = await _save_upload(audio, ".wav")
        image_path = await _save_upload(image, ".jpg")
        if not audio_path and not image_path and not (text and text.strip()):
            raise HTTPException(400, "Provide audio, image, or text input.")

        result = run_pipeline(audio_path=audio_path, image_path=image_path, text_override=text, user_id=_USER_ID)
        payload = dataclasses.asdict(result)
        payload["cost"] = _cost_summary()
        return payload
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 -- surface as a clean API error, not a 500 stack trace
        raise HTTPException(500, f"Pipeline error: {e}")
    finally:
        for p in (audio_path, image_path):
            if p and os.path.exists(p):
                os.remove(p)


@app.post("/api/transcribe")
async def api_transcribe(audio: UploadFile = File(...)):
    """
    Lightweight ASR-only endpoint (no full pipeline) for push-to-talk on
    secondary fields -- the Correct field and the Personalize fields --
    where we just need text, not a full accessibility analysis.
    """
    audio_path = await _save_upload(audio, ".wav")
    if not audio_path:
        raise HTTPException(400, "No audio provided.")
    try:
        result = get_asr_backend().transcribe(audio_path)
        return {"text": result.text, "confidence": result.confidence}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Transcription error: {e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


@app.post("/api/recovery-intent")
async def api_recovery_intent(audio: UploadFile = File(...), options: str = Form(...)):
    """
    Voice-driven recovery (FR-16 completed for a speak-and-listen-only
    user): transcribes a short spoken reply and matches it against the
    recovery actions currently offered (confirm/correct/retry/
    switch_modality), so confirming or retrying never requires a click.
    `options` is a JSON-encoded list of the option strings currently shown
    (matches result.recovery_options.options from the last /api/run).
    """
    import json as _json

    audio_path = await _save_upload(audio, ".wav")
    if not audio_path:
        raise HTTPException(400, "No audio provided.")
    try:
        available = _json.loads(options)
        transcript = get_asr_backend().transcribe(audio_path)
        matched = match_recovery_intent(transcript.text, available)
        return {"heard": transcript.text, "matched_action": matched}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Recovery-intent matching error: {e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


@app.post("/api/correction")
async def api_correction(original: str = Form(...), corrected: str = Form(...)):
    """Personalization (FR-04 support): remember a confirmed correction so
    normalize_transcript() applies it automatically next time."""
    memory = UserMemory(user_id=_USER_ID)
    memory.add_correction(original, corrected)
    return {"status": "ok", "corrections": memory.get_known_corrections()}


@app.get("/api/corrections")
def api_corrections():
    memory = UserMemory(user_id=_USER_ID)
    return {"corrections": memory.get_known_corrections()}


@app.get("/api/cost")
def api_cost():
    return _cost_summary()


@app.post("/api/cost/reset")
def api_cost_reset():
    reset_cost_tracker()
    return _cost_summary()


@app.get("/api/skills")
def api_skills():
    return {"skills": [s.schema() for s in get_skills().values()]}
