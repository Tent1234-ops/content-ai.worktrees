"""Recalculate real saved text for inspection, without changing saved results."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["CONTENT_AI_SKIP_DB_BOOTSTRAP"] = "1"

from app.database.db import SessionLocal, engine
from app.database.models import UserContent
from app.schemas.contents import UserContentDetailResponse
from app.schemas.recommendation import RecommendationAnalysisResponse
from app.services.contents import get_user_content_detail
from app.services.outcome_prediction_readiness import reject_database_writes
from app.services.recommendation import build_recommendation_from_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / "artifacts")
    with reject_database_writes(engine), SessionLocal() as db:
        content = db.get(UserContent, args.content_id)
        if content is None:
            raise ValueError("Saved content not found")
        original = UserContentDetailResponse.model_validate(get_user_content_detail(
            db, user_id=content.user_id, content_id=content.content_id)).model_dump(mode="json")
        recommendation = RecommendationAnalysisResponse.model_validate(build_recommendation_from_text(
            db, title=content.title, text=content.raw_transcript or content.transcript or ""
        )).model_dump(mode="json")
        report = {"mode": "read_only_recalculation_not_saved_to_database",
                  "source_content_id": content.content_id, "title": content.title,
                  "category": recommendation["domain"], "topics": []}
        advised = {item["evidence_topic_id"] for item in
                   recommendation.get("actionable_recommendations", {}).get("items", [])}
        for topic in recommendation["evidence_bundle"]["topic_comparisons"]["items"]:
            if topic["evidence_topic_id"] in advised:
                report["topics"].append({"title": topic["title_th"],
                                        **topic["group_response_summary"]})
        output.mkdir(parents=True, exist_ok=True)
        for name, payload in (("saved-original.json", original),
                              ("fresh-recommendation.json", recommendation), ("audit.json", report)):
            (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
