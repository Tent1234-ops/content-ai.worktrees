"""LOCAL TEST ONLY: Phase 6 browser fixture backed by temporary SQLite.

The fixture exercises the real revision routes and persistence contract. ASR and
classification are deterministic stubs so browser verification never mutates the
real database, consumes external services, or claims model accuracy.
"""
import atexit
import copy
import shutil
import uuid
from pathlib import Path

import app.routes.analyze as analyze_routes
from app.database.models import UserContent
from tests.test_revision_comparisons import RevisionComparisonTests


fixture = RevisionComparisonTests()
fixture.setUp()

with fixture.sessions() as db:
    parent = db.get(UserContent, fixture.content_id)
    parent.title = "TEST FIXTURE: Original phone review"
    db.commit()


def _settings(_db=None):
    return fixture.settings()


def _save_fixture_upload(file, *, max_duration_seconds=300):
    del max_duration_seconds
    target = Path(fixture.temp.name) / f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    return str(target)


def _child_recommendation():
    payload = copy.deepcopy(fixture.parent_recommendation)
    topic = payload["actionable_recommendations"]["items"][0]
    evidence = topic.get("evidence", {})
    canonical = str(evidence.get("canonical_topic") or topic.get("title") or "battery life")
    transcript = f"รีวิวโทรศัพท์ฉบับแก้ไข ทดสอบ {canonical} ระหว่างใช้งานจริงทั้งวัน"
    payload["evidence_bundle"]["input"].update({
        "raw_transcript": transcript,
        "cleaned_transcript": transcript,
        "availability": "available",
        "scope": "full_clip",
        "segments": [{"start": 4.0, "end": 11.0, "text": transcript}],
        "analysis_settings": fixture.settings(),
    })
    return payload


def _pipeline(*_args, **_kwargs):
    payload = _child_recommendation()
    transcript = payload["evidence_bundle"]["input"]["raw_transcript"]
    return {
        "transcript": transcript,
        "raw_transcript": transcript,
        "cleaned_transcript": transcript,
        "analysis": {"title": "TEST FIXTURE: Revised phone review"},
    }


def _build_recommendation(*_args, **_kwargs):
    return _child_recommendation(), {}


def _run_inline(function, *args, **kwargs):
    job_id = kwargs.pop("_job_id", uuid.uuid4().hex)
    kwargs.pop("_owner_user_id", None)
    function(*args, **kwargs)
    return job_id


analyze_routes.SessionLocal = fixture.sessions
analyze_routes._capture_upload_settings = _settings
analyze_routes._save_validated_upload = _save_fixture_upload
analyze_routes.pipeline_analyze = _pipeline
analyze_routes._build_recommendation = _build_recommendation
analyze_routes.enqueue = _run_inline

app = fixture.app
atexit.register(fixture.tearDown)


@app.get("/verification/info")
def info():
    return {
        "fixture": True,
        "user_id": fixture.owner_id,
        "content_id": fixture.content_id,
        "analysis_id": fixture.analysis_id,
        "title": "TEST FIXTURE: Original phone review",
    }

