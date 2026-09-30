"""Read-only integrity audit of completed topic evidence for the active version."""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["CONTENT_AI_SKIP_DB_BOOTSTRAP"] = "1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from app.database.db import SessionLocal
    from app.database.models import (
        TrendTopicConfig, TrendTopicCount, TrendTopicEvidence, TrendTopicJob, TrendTopicObservation, TrendTopicVersion,
    )
    from app.services.trend_topic_store import packed, runtime_manifest, sha
    with SessionLocal() as db:
        version_id = db.get(TrendTopicConfig, 1).active_version_id
        version = db.get(TrendTopicVersion, version_id)
        assert json.loads(version.manifest_json) == runtime_manifest(), "Extractor build mismatch"
        assert sha(packed({"catalog": json.loads(version.catalog_json),
                          "method": json.loads(version.manifest_json)})) == version_id
        topic_ids = {row["id"] for row in json.loads(version.catalog_json)["topics"]}
        jobs, sources = {}, Counter()
        for job, source in db.query(TrendTopicJob, TrendTopicObservation).join(TrendTopicObservation,
            TrendTopicJob.observation_id == TrendTopicObservation.observation_id).filter(
                TrendTopicJob.version_id == version_id, TrendTopicJob.status == "completed").yield_per(500):
            assert hashlib.sha256(source.payload_json.encode("utf-8")).hexdigest() == source.input_sha256
            jobs[job.job_id] = json.loads(job.result_json)
            sources[source.status] += 1
        support, eligible = Counter(), Counter()
        videos, evidence_rows, spans = set(), 0, 0
        for row in db.query(TrendTopicEvidence).join(TrendTopicJob).filter(
                TrendTopicJob.version_id == version_id, TrendTopicJob.status == "completed").yield_per(500):
            evidence_rows += 1
            videos.add(row.video_id)
            eligible[row.job_id] += 1
            matched = set()
            for match in json.loads(row.matches_json):
                assert match["topic_id"] in topic_ids and match["topic_id"] not in matched
                matched.add(match["topic_id"])
                support[row.job_id, match["topic_id"]] += 1
                for span in match["evidence"]:
                    for part in [span, *span.get("context_evidence", [])]:
                        assert row.title[part["start"]:part["end"]] == part["text"]
                        spans += 1
        count_rows = 0
        for row in db.query(TrendTopicCount).join(TrendTopicJob).filter(
                TrendTopicJob.version_id == version_id, TrendTopicJob.status == "completed").yield_per(500):
            count_rows += 1
            assert row.video_count == support[row.job_id, row.topic_id], "Count/evidence mismatch"
            assert row.eligible_videos == eligible[row.job_id] == jobs[row.job_id]["eligible_videos"]
        assert count_rows == len(jobs) * len(topic_ids), "Incomplete count set"
        result = {"audited_at": datetime.utcnow().isoformat() + "Z", "version_id": version_id,
            "completed_jobs": len(jobs), "evidence_rows": evidence_rows, "unique_videos": len(videos),
            "exact_spans_verified": spans, "count_rows_verified": count_rows,
            "source_statuses": dict(sources), "integrity": "passed"}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
