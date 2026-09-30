"""Read-only scope audit and ASR replay. Never train, relabel or activate a model."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.db import SessionLocal
from app.database.models import DatasetContent
from app.routes.analyze import _build_recommendation
from app.services.analysis_evaluation import diagnose_transcript_pair
from app.services.classification import get_active_classification_model
from app.services.classification_acceptance import (
    MIN_UNKNOWN_CHANNELS, MIN_UNKNOWN_TEST, MIN_UNKNOWN_VALIDATION, MIN_VALIDATION_PER_LABEL,
    acceptance_summary,
)
from app.services.classification_training import (
    classification_artifact_sha256, classify_with_artifact, load_classification_artifact,
    prepare_classification_dataset,
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def file_hash(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, help="Audio-verified transcript/label review JSON")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    baseline = read(args.baseline_report)
    reviews = read(args.reviews).get("cases", []) if args.reviews else []
    if len({r["case_id"] for r in reviews}) != len(reviews):
        raise ValueError("Duplicate transcript review IDs")
    by_id = {r["case_id"]: r for r in reviews}
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "status": "incomplete_evaluation",
              "baseline_sha256": file_hash(args.baseline_report), "new_test_sample_count": 0,
              "new_in_scope_metrics": None, "new_unknown_metrics": None, "cases": []}
    templates = []
    with SessionLocal() as db:
        model = get_active_classification_model(db)
        if model is None:
            raise ValueError("No active model")
        artifact = load_classification_artifact(model.artifact_path)
        prepared = prepare_classification_dataset(db, required_leaf_keys=tuple(artifact["labels"]))
        report["active_model"] = {"model_id": model.model_id, "model_key": model.model_key,
                                  "artifact_sha256": classification_artifact_sha256(model.artifact_path),
                                  "acceptance_policy": acceptance_summary(artifact.get("scope_policy"))}
        report["data_readiness"] = prepared.report
        report["unknown_partitions"] = dict(Counter(r.split for r in prepared.out_of_scope_examples))
        report["collection_requirements"] = {
            "in_scope_validation_minimum_per_label": MIN_VALIDATION_PER_LABEL,
            "unknown_validation_minimum": MIN_UNKNOWN_VALIDATION,
            "unknown_test_minimum": MIN_UNKNOWN_TEST, "unknown_channels_per_partition": MIN_UNKNOWN_CHANNELS,
            "note": "These are minimum coverage gates, not statistical proof. Reserve new test channels before collection."}
        report["outside_scope_review_candidates"] = [
            {"dataset_id": r.dataset_id, "existing_leaf": r.taxonomy_leaf_key, "split": r.data_split,
             "title": r.title, "source_youtube_id": r.source_youtube_id,
             "usage": "candidate_only_requires_review_no_automatic_relabel"}
            for r in db.query(DatasetContent).filter(DatasetContent.taxonomy_leaf_key.notin_(artifact["labels"]),
                DatasetContent.verification_status == "human_verified", DatasetContent.deleted_at.is_(None)).all()]
        for entry in baseline["cases"]:
            case_id = str(entry["case_id"])
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", case_id):
                raise ValueError("Invalid case ID")
            original_path = args.baseline_report.parent / f"{case_id}.json"
            original = read(original_path)
            result = copy.deepcopy(original["result"])
            result.pop("recommendation", None)
            asr = str(result.get("cleaned_transcript") or result.get("transcript") or "")
            spec = original["spec"]
            review = by_id.get(case_id, {})
            if review and review.get("media_sha256") != spec["media_sha256"]:
                raise ValueError("Transcript review refers to a different media file")
            old = classify_with_artifact(model.artifact_path, text=asr, require_scope_validation=False)
            diagnostic = diagnose_transcript_pair(asr, review,
                lambda text: classify_with_artifact(model.artifact_path, text=text))
            recommendation, _ = _build_recommendation(db, filename="evaluation.mp4", result=result)
            result["recommendation"] = recommendation
            row = {"case_id": case_id, "role": "regression", "media_sha256": spec["media_sha256"],
                   "source_result_sha256": file_hash(original_path), "video_path": spec["video_path"],
                   "raw_model_label": old["raw_taxonomy_leaf_key"], "raw_model_confidence": old["confidence"],
                   "final_label": recommendation["classification"]["taxonomy_leaf_key"],
                   "acceptance": recommendation["classification"].get("acceptance"),
                   "recommendation_count": len(recommendation["missing_keywords"]) + len(recommendation["hook_keywords"]),
                   "reference_count": recommendation["dataset_profile"]["sample_size"], "diagnostic": diagnostic}
            write(args.out / f"{case_id}.json", {**row, "result": result, "review": review})
            report["cases"].append(row)
            templates.append({"case_id": case_id, "media_sha256": spec["media_sha256"],
                              "video_path": spec["video_path"], "expected_label": None,
                              "label_reviewed_by": "", "listened_to_audio": False,
                              "transcript_reviewed_by": "", "verified_transcript": "",
                              "asr_transcript_for_comparison_only": result.get("raw_transcript", asr)})
        db.rollback()
    write(args.out / "report.json", report)
    write(args.out / "transcript-review-template.json", {"cases": templates})
    lines = ["# Classification scope regression", "", "Status: incomplete; no new test clips were supplied.",
             "No training, activation, relabel or analysis save was performed.",
             "Existing clips are regression checks, not a new accuracy/Unknown benchmark.", "",
             f"Active model: {report['active_model']['model_id']}",
             f"Unknown partitions: {report['unknown_partitions']}", "",
             "| Case | Raw model label | Confidence | Final label | Suggestions |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {r['case_id']} | {r['raw_model_label']} | {r['raw_model_confidence']:.4f} | "
              f"{r['final_label']} | {r['recommendation_count']} |" for r in report["cases"]]
    lines += ["", "An unvalidated model is withheld in strict mode, including valid in-scope clips.",
              "This is a safety policy, not evidence that the classifier learned Unknown.",
              "ASR/classifier attribution is pending until a person listens and verifies the transcript and label.",
              "Fill the review template and rerun into a NEW output directory; original evidence is never replaced."]
    (args.out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.out), "regression_cases": len(report["cases"]),
                      "unknown_partitions": report["unknown_partitions"], "new_test_samples": 0}))


if __name__ == "__main__":
    raise SystemExit(main())
