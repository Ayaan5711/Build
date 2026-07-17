"""
Tests for the FastAPI backend (server.py) that powers the custom HTML/CSS/JS
frontend. Uses FastAPI's TestClient -- in-process, no real network, no
running uvicorn needed. Mock backends only.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from server import app
from src.integrations import assignments_store, reminders_store
from src.understanding import dialogue_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_dialogue_and_reminders(tmp_path, monkeypatch):
    """server.py uses one shared user_id ("demo-user") for every /api/run
    call -- correct for a single-demo-laptop deployment, but it means any
    test that leaves a guided dialogue mid-flight (e.g. "book appointment"
    is now genuinely under-specified and starts one) would otherwise bleed
    into whichever test runs next, in this file or any other sharing the
    same pytest process. Reset the in-memory dialogue state and both
    persisted-store DB paths around every test in this file."""
    dialogue_state.reset_all()
    monkeypatch.setattr(reminders_store, "_DB_PATH", str(tmp_path / "server_test_reminders.db"))
    monkeypatch.setattr(assignments_store, "_DB_PATH", str(tmp_path / "server_test_assignments.db"))
    yield
    dialogue_state.reset_all()


def test_index_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "TCS iON Voice AI" in r.text


def test_static_files_serve():
    css = client.get("/static/style.css")
    js = client.get("/static/app.js")
    assert css.status_code == 200
    assert js.status_code == 200
    assert "font-family" in css.text
    assert "speechSynthesis" in js.text


def test_run_with_text_returns_full_pipeline_result():
    r = client.post("/api/run", data={"text": "B-b-b-book appointment tomorrow"})
    assert r.status_code == 200
    body = r.json()
    assert "book appointment tomorrow" in body["accessible_transcript"]["text"].lower()
    assert body["disfluency_report"]["has_disfluency"] is True
    assert "speech_impairment" in body["accessibility_report"]["barriers_detected"]
    assert "cost" in body
    assert "timings_ms" in body and "total_ms" in body


def test_run_includes_agent_trace_in_json():
    r = client.post("/api/run", data={"text": "What is PAS 901?"})
    assert r.status_code == 200
    agent = r.json()["agent_result"]
    assert isinstance(agent["steps"], list)
    assert len(agent["steps"]) >= 1
    assert agent["steps"][0]["action"] in ("call_skill", "clarify", "finish")


def test_run_with_no_input_returns_400():
    r = client.post("/api/run")
    assert r.status_code == 400


def test_run_with_audio_file_upload():
    """A real recorded/uploaded clip has no matching .txt fixture, so
    MockASRBackend returns an honest placeholder explaining the ASR_BACKEND
    setting is wrong for live audio -- it must NOT silently substitute an
    unrelated cached demo scenario (that was a real bug: it always showed
    demo #1 "book appointment" regardless of what was actually said,
    because the NFR-03 outage-fallback path was being triggered by a
    config mismatch, not a real backend failure)."""
    fake_audio = io.BytesIO(b"not a real wav, just exercising upload plumbing")
    r = client.post("/api/run", files={"audio": ("clip.wav", fake_audio, "audio/wav")})
    assert r.status_code == 200
    body = r.json()
    assert body["used_fallback_cache"] is False
    assert "mock ASR" in body["original_input"]["text"]


def test_transcribe_endpoint_requires_audio():
    r = client.post("/api/transcribe")
    assert r.status_code == 422  # FastAPI validation: audio is required


def test_correction_save_and_read_roundtrip():
    r = client.post("/api/correction", data={"original": "Ka-ka-Kiran", "corrected": "Kiran"})
    assert r.status_code == 200
    assert r.json()["corrections"]["Ka-ka-Kiran"] == "Kiran"

    r2 = client.get("/api/corrections")
    assert r2.json()["corrections"]["Ka-ka-Kiran"] == "Kiran"


def test_correction_is_applied_on_next_run():
    client.post("/api/correction", data={"original": "So-soumesh", "corrected": "Soumesh"})
    r = client.post("/api/run", data={"text": "My name is So-soumesh"})
    assert "Soumesh" in r.json()["accessible_transcript"]["text"]


def test_cost_endpoint_shape():
    r = client.get("/api/cost")
    assert r.status_code == 200
    body = r.json()
    for key in ("total_usd", "cap_usd", "by_stage", "profile"):
        assert key in body


def test_cost_reset_endpoint():
    r = client.post("/api/cost/reset")
    assert r.status_code == 200
    assert r.json()["total_usd"] == 0


def test_skills_endpoint_lists_all_registered_skills():
    r = client.get("/api/skills")
    names = [s["name"] for s in r.json()["skills"]]
    assert "faq_lookup" in names
    assert "schedule_reminder" in names
    assert "general_help" in names


def test_guided_reminder_dialogue_across_three_api_run_calls():
    """The real path a browser session takes: three separate POST /api/run
    requests (server.py's shared demo-user), each one a paced question,
    ending in a genuinely persisted reminder -- not three independent,
    unrelated answers."""
    r1 = client.post("/api/run", data={"text": "book appointment"})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["final_response"]["text"] == "What should I remind you about?"
    assert "confirm" not in body1["recovery_options"]["options"]

    r2 = client.post("/api/run", data={"text": "the dentist"})
    body2 = r2.json()
    assert "when" in body2["final_response"]["text"].lower()

    r3 = client.post("/api/run", data={"text": "tomorrow at 4pm"})
    body3 = r3.json()
    assert "the dentist" in body3["final_response"]["text"].lower()
    assert "tomorrow at 4pm" in body3["final_response"]["text"].lower()
    assert body3["agent_result"]["skills_used"] == ["schedule_reminder"]
    assert "confirm" in body3["recovery_options"]["options"]

    saved = reminders_store.list_reminders("demo-user")
    assert len(saved) == 1
    assert saved[0].subject == "the dentist"


def test_classroom_schedule_queries_answer_directly_no_pacing_needed():
    """The read-only classroom lookups (real date logic, not RAG) never
    need clarification -- each is a single /api/run call."""
    r = client.post("/api/run", data={"text": "what classes do I have today"})
    body = r.json()
    assert body["agent_result"]["clarification"] is None
    assert body["agent_result"]["skills_used"] == ["class_schedule"]

    r2 = client.post("/api/run", data={"text": "show absent students"})
    body2 = r2.json()
    assert "absent" in body2["final_response"]["text"].lower()


def test_guided_assignment_dialogue_across_four_api_run_calls():
    """The classroom domain's own flagship paced example, driven through
    the real HTTP surface exactly like the reminder flow above."""
    r1 = client.post("/api/run", data={"text": "create an assignment"})
    assert r1.json()["final_response"]["text"] == "Which chapter or topic is this assignment for?"

    r2 = client.post("/api/run", data={"text": "Chapter 5"})
    assert "class" in r2.json()["final_response"]["text"].lower()

    r3 = client.post("/api/run", data={"text": "Class 8B"})
    assert "due" in r3.json()["final_response"]["text"].lower()

    r4 = client.post("/api/run", data={"text": "next Monday"})
    body4 = r4.json()
    assert "Chapter 5" in body4["final_response"]["text"]
    assert body4["agent_result"]["skills_used"] == ["create_assignment"]

    saved = assignments_store.list_assignments("demo-user")
    assert len(saved) == 1
    assert saved[0].chapter == "Chapter 5"


def test_run_response_is_json_serializable_dataclass_tree():
    """Guards against re-introducing a non-JSON-safe field (e.g. a
    threading.Lock) anywhere in PipelineResult -- this would only surface
    as a 500 here, not at import time."""
    r = client.post("/api/run", data={"text": "hello"})
    assert r.status_code == 200
    # Full round trip through JSON already proves serializability; sanity
    # check a nested structure specifically.
    assert isinstance(r.json()["retrieved_context"], list)
