import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import text

from app.database.models import (
    DatasetContent,
    ReferenceStatisticsRun,
    ReferenceVideoStatistic,
)
from app.services.outcome_prediction_readiness import (
    DATA_USE_SCHEMA_VERSION,
    audit_outcome_readiness,
    data_use_gate,
    database_identity,
    reject_database_writes,
    scan_prior_artifact_use,
    validate_protocol,
)
from tests import test_phase20_keyword_gap_evidence as fixtures


ROOT = Path(__file__).resolve().parents[1]


def data_use(status="unverified", evidence=None):
    return {
        "schema_version": DATA_USE_SCHEMA_VERSION,
        "status": status,
        "owner": "project_owner",
        "intended_uses": ["audit", "training", "serving"],
        "confirmation_evidence": list(evidence or []),
        "decision": {"audit_allowed": True},
    }


class OutcomePredictionReadinessTests(unittest.TestCase):
    setUp = fixtures.Phase20KeywordGapEvidenceTests.setUp
    tearDown = fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def prepare_rows(self, cutoff):
        rows = self.db.query(DatasetContent).order_by(DatasetContent.dataset_id).all()
        run = ReferenceStatisticsRun(
            status="completed", actor="test", started_at=cutoff - timedelta(hours=1),
            completed_at=cutoff - timedelta(minutes=50), requests_used=1,
            candidate_count=len(rows),
        )
        self.db.add(run)
        self.db.flush()
        for index, row in enumerate(rows):
            metadata = json.loads(row.raw_metadata_json)
            metadata["content_format"] = "long_form"
            row.raw_metadata_json = json.dumps(metadata)
            self.db.add(ReferenceVideoStatistic(
                run_id=run.run_id, dataset_id=row.dataset_id,
                video_id=row.source_youtube_id, source_url=row.video_url,
                observed_at=cutoff - timedelta(hours=1), status="complete",
                views=1000 + index, likes=10, comments=2,
                view_metric_version="youtube_play_start_view_v2",
            ))
        self.db.commit()
        return rows, run

    def new_run(self, cutoff, suffix):
        run = ReferenceStatisticsRun(
            status="completed", actor=f"test-{suffix}",
            started_at=cutoff - timedelta(minutes=40),
            completed_at=cutoff - timedelta(minutes=20), requests_used=1,
            candidate_count=1,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def test_audit_is_read_only_and_keeps_test_labels_closed(self):
        cutoff = datetime(2026, 10, 8, 12, 0, 0)
        rows, _run = self.prepare_rows(cutoff)
        rows[0].data_split = "test"
        rows[1].data_split = "validation"
        self.db.commit()
        before = database_identity(self.db)
        with TemporaryDirectory() as temp:
            report = audit_outcome_readiness(
                self.db, cutoff=cutoff, repo_root=Path(temp),
                data_use_record=data_use(),
            )
        after = database_identity(self.db)
        self.assertEqual(before, after)
        self.assertFalse(self.db.new)
        self.assertFalse(self.db.dirty)
        self.assertEqual(report["dataset"]["active_target_rows"], 30)
        self.assertEqual(report["dataset"]["structurally_ready_without_rights_or_outcome_split"], 30)
        self.assertEqual(report["dataset"]["training_allowed_rows"], 0)
        self.assertEqual(report["holdout"]["classification_holdout_rows"], 2)
        self.assertEqual(report["holdout"]["fresh_outcome_test_count"], 0)
        self.assertNotIn("views", report["records"][0])
        self.assertTrue(report["records"][0]["views_available"])

    def test_cutoff_missing_fields_format_and_metric_mismatch_are_explicit(self):
        cutoff = datetime(2026, 10, 8, 12, 0, 0)
        rows, run = self.prepare_rows(cutoff)
        rows[0].raw_metadata_json = "{}"
        rows[1].published_at = cutoff + timedelta(days=1)
        rows[2].transcript_scope = "first_window"
        rows[3].transcript = rows[3].transcript + " changed"
        first = self.db.query(ReferenceVideoStatistic).filter_by(dataset_id=rows[4].dataset_id).one()
        first.view_metric_version = "unknown_v1"
        self.db.query(ReferenceVideoStatistic).filter_by(dataset_id=rows[5].dataset_id).delete()
        later_run = self.new_run(cutoff, "after-cutoff")
        self.db.add(ReferenceVideoStatistic(
            run_id=later_run.run_id, dataset_id=rows[6].dataset_id,
            video_id=rows[6].source_youtube_id, source_url=rows[6].video_url,
            observed_at=cutoff + timedelta(hours=1), status="complete", views=999,
            view_metric_version="youtube_play_start_view_v2",
        ))
        self.db.commit()
        with TemporaryDirectory() as temp:
            report = audit_outcome_readiness(
                self.db, cutoff=cutoff, repo_root=Path(temp),
                data_use_record=data_use(),
            )
        by_id = {item["dataset_id"]: item for item in report["records"]}
        self.assertIn("confirmed_format_missing", by_id[rows[0].dataset_id]["issues"])
        self.assertIn("publication_after_observation", by_id[rows[1].dataset_id]["issues"])
        self.assertIn("transcript_not_full_video", by_id[rows[2].dataset_id]["issues"])
        self.assertIn("transcript_hash_mismatch", by_id[rows[3].dataset_id]["issues"])
        self.assertIn("unknown_view_metric_version", by_id[rows[4].dataset_id]["issues"])
        self.assertIn("no_observation", by_id[rows[5].dataset_id]["issues"])
        self.assertEqual(by_id[rows[6].dataset_id]["latest_observed_at"], "2026-10-08T11:00:00Z")

    def test_multiple_observations_count_as_one_video_and_latest_before_cutoff(self):
        cutoff = datetime(2026, 10, 8, 12, 0, 0)
        rows, _run = self.prepare_rows(cutoff)
        row = rows[0]
        run_two = self.new_run(cutoff, "second")
        run_three = self.new_run(cutoff, "after")
        self.db.add_all([
            ReferenceVideoStatistic(
                run_id=run_two.run_id, dataset_id=row.dataset_id, video_id=row.source_youtube_id,
                source_url=row.video_url, observed_at=cutoff - timedelta(minutes=30),
                status="partial", views=1200, likes=None, comments=None,
                view_metric_version="youtube_play_start_view_v2",
            ),
            ReferenceVideoStatistic(
                run_id=run_three.run_id, dataset_id=row.dataset_id, video_id=row.source_youtube_id,
                source_url=row.video_url, observed_at=cutoff + timedelta(minutes=30),
                status="complete", views=9999, likes=50, comments=5,
                view_metric_version="youtube_play_start_view_v2",
            ),
        ])
        self.db.commit()
        with TemporaryDirectory() as temp:
            report = audit_outcome_readiness(
                self.db, cutoff=cutoff, repo_root=Path(temp),
                data_use_record=data_use(),
            )
        record = next(item for item in report["records"] if item["dataset_id"] == row.dataset_id)
        self.assertEqual(record["latest_observed_at"], "2026-10-08T11:30:00Z")
        self.assertEqual(record["successful_observation_count"], 2)
        self.assertEqual(report["statistics"]["videos_with_two_or_more_successful_observations"], 1)
        self.assertEqual(report["dataset"]["independent_video_ids"], 30)

    def test_cross_split_channel_and_normalized_transcript_are_flagged(self):
        cutoff = datetime(2026, 10, 8, 12, 0, 0)
        rows, _run = self.prepare_rows(cutoff)
        rows[1].data_split = "test"
        rows[1].source_channel_id = rows[0].source_channel_id
        rows[1].creator_group_key = rows[0].creator_group_key
        rows[1].transcript = rows[0].transcript + " !!!"
        rows[1].transcript_sha256 = hashlib.sha256(rows[1].transcript.encode()).hexdigest()
        self.db.commit()
        with TemporaryDirectory() as temp:
            report = audit_outcome_readiness(
                self.db, cutoff=cutoff, repo_root=Path(temp),
                data_use_record=data_use(),
            )
        channel = next(item for item in report["identity_review"]["channel"]
                       if rows[0].dataset_id in item["dataset_ids"])
        normalized = next(item for item in report["identity_review"]["normalized_transcript"]
                          if rows[0].dataset_id in item["dataset_ids"])
        self.assertTrue(channel["cross_split"])
        self.assertTrue(normalized["cross_split"])

    def test_protocol_and_data_use_gates_fail_closed(self):
        protocol = json.loads((ROOT / "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))
        self.assertTrue(validate_protocol(protocol)["valid"])
        invalid = dict(protocol)
        invalid.pop("target")
        self.assertFalse(validate_protocol(invalid)["valid"])
        self.assertTrue(data_use_gate(data_use(), "audit")["allowed"])
        self.assertFalse(data_use_gate(data_use(), "training")["allowed"])
        self.assertFalse(data_use_gate(data_use("restricted", ["owner-record"]), "serving")["allowed"])
        self.assertTrue(data_use_gate(data_use("confirmed", ["owner-record"]), "training")["allowed"])

    def test_artifact_scan_records_explicit_prior_roles_only(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "artifacts/classification_training/run/dataset/version"
            folder.mkdir(parents=True)
            (folder / "test.jsonl").write_text(json.dumps({
                "dataset_id": 7, "source_youtube_id": "video-7"
            }) + "\n", encoding="utf-8")
            report = scan_prior_artifact_use(root)
        self.assertEqual(report["by_dataset_id"]["7"], ["classification_test"])
        self.assertEqual(report["by_video_id"]["video-7"], ["classification_test"])

    def test_sql_write_guard_rejects_mutation(self):
        with reject_database_writes(self.engine):
            self.db.execute(text("SELECT 1"))
            with self.assertRaisesRegex(RuntimeError, "blocked SQL verb: UPDATE"):
                self.db.execute(text("UPDATE dataset_contents SET title = title"))
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
