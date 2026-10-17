"""Read-only replay of recorded ASR output; never a fresh held-out evaluation."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal, engine
from app.database.models import AnalysisResult, ClassificationModel, DatasetContent, OutcomeModel
from app.routes.analyze import _build_recommendation
from app.services.analysis_settings import capture_analysis_settings
from app.services.model_management import model_detail
from app.services.outcome_prediction_readiness import reject_database_writes
from scripts.replace_notebooklm_transcripts import snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--recordings", type=Path, required=True)
    parser.add_argument("--expected-model-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output must be new")
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    report = {"captured_at": datetime.now(timezone.utc).isoformat(),
              "evidence_type": "reused recorded ASR regression, not fresh test or new upload",
              "workflow_passed": False, "regressions": [], "integrity": {}}
    expected = {"review_camera.mp4": "camera", "review_laptop.mp4": "laptop",
                "review_phone_m.mp4": "phone", "review_headphone.mp4": "unknown",
                "review_keyboard.mp4": "unknown"}
    try:
        with reject_database_writes(engine), SessionLocal() as db:
            rows = {str(r.dataset_id): snapshot(r) for r in db.query(DatasetContent).all()}
            assert rows.keys() == baseline["datasets"].keys(), "Dataset identity changed"
            changes = []
            for key, before in baseline["datasets"].items():
                differing = [field for field in before if before[field] != rows[key][field]]
                if differing:
                    changes.append({"dataset_id": int(key), "fields": differing})
            report["integrity"]["dataset_changes"] = changes
            assert not changes, "Dataset changed since the final training audit"
            old_results = baseline["analysis_results"]
            for before in old_results:
                current = db.get(AnalysisResult, before["result_id"])
                assert current and snapshot(current) == before, "Existing analysis changed"
            report["integrity"].update(dataset_rows_unchanged=len(rows),
                                        old_analysis_results_unchanged=len(old_results))
            models = db.query(ClassificationModel).filter_by(is_active=True).all()
            assert len(models) == 1 and models[0].model_id == args.expected_model_id
            report["active_model"] = model_detail(db, models[0].model_id)
            settings = capture_analysis_settings(db)
            report["settings"] = settings
            assert settings["classification_model"]["readiness"]["can_accept_predictions"]
            report["outcome_registry_count"] = db.query(OutcomeModel).count()
            for filename, category in expected.items():
                source = args.recordings / f"medium-{filename}.json"
                recorded = json.loads(source.read_text(encoding="utf-8"))
                assert recorded["passed"] and recorded["result"]["raw_transcript"].strip()
                original = recorded["result"]
                pipeline = copy.deepcopy(original["analysis"])
                raw = pipeline["raw_transcript"]
                pipeline["analysis_settings"] = settings
                advice, _ = _build_recommendation(db, filename=filename, result=pipeline,
                                                  settings_snapshot=settings)
                classification = advice["classification"]
                actions = advice.get("actionable_recommendations") or {}
                assessment = advice.get("outcome_assessment") or {}
                assert pipeline["raw_transcript"] == raw, "Replay changed source ASR"
                assert assessment.get("status") != "available" and assessment.get("probability") is None
                if classification["taxonomy_leaf_key"] == "unknown":
                    assert not actions.get("items") and not advice.get("missing_keywords")
                result = {"clip": filename, "expected_category": category,
                    "source_report_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "transcript_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "previous_classification": original["recommendation"]["classification"],
                    "classification": classification,
                    "category_correct": classification["taxonomy_leaf_key"] == category,
                    "actionable_recommendations": actions,
                    "missing_keywords": advice.get("missing_keywords"),
                    "hook_keywords": advice.get("hook_keywords"),
                    "recommended_duration": advice.get("recommended_duration"),
                    "outcome_assessment": assessment}
                report["regressions"].append(result)
                print(json.dumps({"clip": filename, "actual": classification["taxonomy_leaf_key"],
                                  "correct": result["category_correct"],
                                  "advice_count": len(actions.get("items") or []),
                                  "outcome": assessment.get("status")}), flush=True)
            report["all_regression_categories_correct"] = all(r["category_correct"] for r in report["regressions"])
            report["workflow_passed"] = True
            db.rollback()
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
