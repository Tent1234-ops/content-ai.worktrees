"""Report reused Test results AFTER activation; never select or qualify a model."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from app.database.db import SessionLocal, engine
from app.database.models import ClassificationModel
from app.services.classification_training import classify_with_artifact, load_classification_artifact
from app.services.classification_presentation import presentation_authorization
from app.services.outcome_prediction_readiness import reject_database_writes


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output must be new")
    with reject_database_writes(engine), SessionLocal() as db:
        model = db.get(ClassificationModel, args.model_id)
        assert model and model.is_active
        artifact_path = model.artifact_path
        artifact_hash = digest(artifact_path)
        bundle = load_classification_artifact(artifact_path)
        allow_presentation = model.status == "presentation_only"
        if allow_presentation:
            assert presentation_authorization(bundle)["authorized"], "Presentation grant expired or invalid"
        manifest_path = bundle["dataset_manifest_path"]
        assert digest(manifest_path) == bundle["dataset_manifest_sha256"]
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        assert manifest["dataset_fingerprint"] == bundle["dataset_fingerprint"]
        rows = []
        for source in (manifest["artifacts"]["splits"]["test"], manifest["artifacts"]["out_of_scope"]):
            assert digest(source["path"]) == source["sha256"]
            rows.extend(r for line in Path(source["path"]).read_text(encoding="utf-8").splitlines()
                        if line.strip() and (r := json.loads(line))["data_split"] == "test")
        assert len({r["dataset_id"] for r in rows}) == len(rows)
        results = []
        for row in rows:
            prediction = classify_with_artifact(artifact_path, title=None, text=row["transcript"],
                                                allow_presentation=allow_presentation)
            results.append({"dataset_id": row["dataset_id"], "video_id": row["source_youtube_id"],
                            "true": row["taxonomy_leaf_key"], "predicted": prediction["taxonomy_leaf_key"],
                            "confidence": prediction["confidence"], "acceptance": prediction["acceptance"]})
        labels = ["phone", "camera", "laptop", "unknown"]
        in_scope = [r for r in results if r["true"] != "unknown"]
        by_category = {}
        for label in labels:
            group = [r for r in results if r["true"] == label]
            correct = sum(r["true"] == r["predicted"] for r in group)
            by_category[label] = {"count": len(group), "correct": correct,
                                  "recall": correct / len(group) if group else None}
        report = {"captured_at": datetime.now(timezone.utc).isoformat(), "model_id": model.model_id,
            "model_status_unchanged": model.status, "artifact_sha256": artifact_hash,
            "allow_presentation": allow_presentation,
            "evaluation_type": "reused_test_regression_after_activation_not_fresh_independent_test",
            "used_for_selection": False, "qualification_updated": False,
            "sample_count": len(results), "by_category": by_category,
            "in_scope_accuracy": accuracy_score([r["true"] for r in in_scope], [r["predicted"] for r in in_scope]),
            "in_scope_macro_f1": f1_score([r["true"] for r in in_scope], [r["predicted"] for r in in_scope],
                                         labels=labels[:3], average="macro", zero_division=0),
            "confusion_labels": labels,
            "confusion_matrix": confusion_matrix([r["true"] for r in results], [r["predicted"] for r in results],
                                                  labels=labels).tolist(), "results": results}
        assert digest(artifact_path) == artifact_hash
        db.rollback()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k not in {"results", "confusion_matrix"}}))


if __name__ == "__main__":
    main()
