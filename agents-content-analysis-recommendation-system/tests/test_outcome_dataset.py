import copy
import hashlib
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database.migrations import migrate_outcome_statistics_schema
from app.database.models import (
    DatasetContent,
    ReferenceStatisticsConfig,
    ReferenceStatisticsRun,
    ReferenceVideoStatistic,
)
from app.services.outcome_dataset import (
    build_collection_manifest,
    build_feature_record,
    cv_fold_labels,
    database_source_records,
    feature_schema,
    fit_benchmarks,
    freeze_manifest,
    label_records,
    verify_manifest,
)
from app.services.outcome_statistics import collect_outcome_statistics
from app.services.youtube_cc_dataset import YouTubeQuotaExceededError
from tests import test_phase20_keyword_gap_evidence as fixtures


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "docs/implementation/outcome-prediction-protocol-v1.json").read_text(encoding="utf-8"))


def confirmed_data_use():
    return {
        "schema_version": "outcome-data-use-decision-v1",
        "status": "confirmed", "owner": "fixture-owner",
        "intended_uses": ["audit", "training", "serving"],
        "confirmation_evidence": [{"fixture": True}],
        "decision": {"audit_allowed": True},
    }


def unverified_data_use():
    return {
        "schema_version": "outcome-data-use-decision-v1",
        "status": "unverified", "owner": "fixture-owner",
        "intended_uses": ["audit", "training", "serving"],
        "confirmation_evidence": [], "decision": {"audit_allowed": True},
    }


def record(index, *, role="fit", channel=None, views=1000, transcript=None,
           category="phone", source_split="train"):
    channel = channel or f"channel-{index}"
    transcript = transcript or f"รีวิวมือถือ แบตเตอรี่และชาร์จเร็ว ตัวอย่าง {index}"
    video_id = f"fixture{index:04d}"
    return {
        "dataset_id": index, "source_youtube_id": video_id,
        "source_channel_id": channel,
        "creator_group_key": hashlib.sha256(channel.encode()).hexdigest(),
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "source_split": source_split,
        "split_protection": "protected" if source_split in {"validation", "test"} else "none",
        "outcome_role": role, "accepted_category": category,
        "confirmed_format": "long_form", "format_provenance": "fixture",
        "duration_seconds": 180, "published_at": "2026-08-01T00:00:00Z",
        "frozen_age_context": "age_30_90d", "age_days_at_observation": 60,
        "transcript": transcript,
        "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
        "transcript_scope": "full_video", "transcript_source": "fixture",
        "transcript_timestamps_available": False, "transcript_segments": [],
        "metadata_provenance": {"fixture": True},
        "collection_strategy": "classification_diverse",
        "sampling_frame": "general_protocol_v1", "prior_explicit_roles": [],
        "observation": {
            "observation_id": index, "observed_at": "2026-10-01T00:00:00Z",
            "view_metric_version": "youtube_play_start_view_v2",
            "views": views, "status": "complete",
        },
        "exclusion_reasons": [],
    }


class OutcomeDatasetContractTests(unittest.TestCase):
    def test_documented_feature_schema_matches_builder(self):
        documented = json.loads((
            ROOT / "docs/implementation/outcome-feature-schema-v1.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(documented, feature_schema(PROTOCOL))

    def test_duplicate_video_is_one_sample_and_channel_cannot_cross_partitions(self):
        first = record(1, role="fit", channel="shared")
        duplicate = record(2, role="fit", channel="other")
        duplicate["source_youtube_id"] = first["source_youtube_id"]
        result = freeze_manifest(
            [first, duplicate], cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
            data_use_record=confirmed_data_use(),
        )
        self.assertEqual(len(result["manifest"]["records"]), 1)
        self.assertIn("duplicate_video_or_transcript", result["excluded"][0]["reason_codes"])

        crossed = freeze_manifest(
            [record(3, role="fit", channel="same"),
             record(4, role="tuning", channel="same")],
            cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
            data_use_record=confirmed_data_use(),
        )
        self.assertIsNone(crossed["manifest"])
        self.assertTrue(all("identity_crosses_outcome_partitions" in item["reason_codes"]
                            for item in crossed["excluded"]))

    def test_manifest_is_deterministic_and_changes_with_material_inputs(self):
        rows = [record(1), record(2, role="independent_test", source_split="test")]
        first = freeze_manifest(rows, cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
                                data_use_record=confirmed_data_use())
        second = freeze_manifest(copy.deepcopy(rows), cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
                                 data_use_record=confirmed_data_use())
        self.assertEqual(first["manifest"]["manifest_sha256"], second["manifest"]["manifest_sha256"])
        self.assertTrue(verify_manifest(first["manifest"]))
        test_public = next(item for item in first["manifest"]["records"]
                           if item["outcome_role"] == "independent_test")
        self.assertNotIn("views", test_public["observation"])
        self.assertEqual(test_public["outcome_access"], "sealed_until_phase_6_evaluation")

        changed = copy.deepcopy(rows)
        changed[0]["transcript"] += " เปลี่ยน"
        changed[0]["transcript_sha256"] = hashlib.sha256(changed[0]["transcript"].encode()).hexdigest()
        transcript_result = freeze_manifest(changed, cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
                                            data_use_record=confirmed_data_use())
        self.assertNotEqual(first["manifest"]["manifest_sha256"],
                            transcript_result["manifest"]["manifest_sha256"])
        changed = copy.deepcopy(rows)
        changed[1]["observation"]["views"] += 1
        observation_result = freeze_manifest(changed, cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
                                             data_use_record=confirmed_data_use())
        self.assertNotEqual(first["manifest"]["manifest_sha256"],
                            observation_result["manifest"]["manifest_sha256"])
        changed_protocol = copy.deepcopy(PROTOCOL)
        changed_protocol.pop("protocol_sha256")
        changed_protocol["cutoff_policy"]["latest_successful_observation_max_age_hours"] = 23
        protocol_result = freeze_manifest(
            rows, cutoff=datetime(2026, 10, 1), protocol=changed_protocol,
            data_use_record=confirmed_data_use(),
        )
        self.assertNotEqual(first["manifest"]["manifest_sha256"],
                            protocol_result["manifest"]["manifest_sha256"])

    def test_features_are_binary_full_catalog_and_unassessable_is_not_false_vector(self):
        once = record(1, transcript="รีวิวมือถือ แบตเตอรี่ ชาร์จเร็ว")
        repeated = record(1, transcript="รีวิวมือถือ แบตเตอรี่ ชาร์จเร็ว " + "ชาร์จเร็ว " * 20)
        feature_once = build_feature_record(once, PROTOCOL)
        feature_repeat = build_feature_record(repeated, PROTOCOL)
        self.assertEqual(feature_once["model_input"]["canonical_topic_presence"],
                         feature_repeat["model_input"]["canonical_topic_presence"])
        self.assertTrue(feature_once["model_input"]["canonical_topic_presence"]["charging speed"])
        self.assertNotIn("views", json.dumps(feature_once["model_input"]))
        failed = copy.deepcopy(once)
        failed["transcript_scope"] = "first_window"
        self.assertEqual(build_feature_record(failed, PROTOCOL)["status"], "unusable")
        self.assertNotIn("model_input", build_feature_record(failed, PROTOCOL))

    def test_fit_benchmark_never_uses_validation_or_test_outcomes(self):
        fit = [record(index, channel=f"fit-{(index - 1) % 5}", views=index * 100)
               for index in range(1, 21)]
        validation = record(25, role="calibration", channel="c", views=999999,
                            source_split="validation")
        test = record(26, role="independent_test", channel="d", views=888888,
                      source_split="test")
        before = fit_benchmarks([*fit, validation, test], PROTOCOL)
        validation["observation"]["views"] = 1
        test["observation"]["views"] = 2
        after = fit_benchmarks([*fit, validation, test], PROTOCOL)
        self.assertEqual(before, after)
        labels = label_records([*fit, validation, test], before)
        self.assertEqual(labels, label_records([*fit, validation, test], before))
        self.assertFalse(labels["independent_test_unlocked"])
        self.assertTrue(any(item["reason"] == "independent_test_sealed"
                            for item in labels["exclusions"]))

    def test_cv_fold_benchmark_excludes_heldout_channel_and_unsupported_cell_abstains(self):
        rows = [record(index, channel=f"fit-{(index - 1) % 5}", views=index * 100)
                for index in range(1, 21)]
        rows.append(record(21, channel="held", views=100000))
        fold = cv_fold_labels(rows, PROTOCOL, heldout_channel_ids={"held"})
        self.assertNotIn("held", fold["fit_channel_ids"])
        self.assertEqual(fold["benchmarks"]["cells"][0]["threshold_views"], 1000)
        self.assertEqual(fold["benchmarks"]["cells"][0]["status"], "supported")
        unsupported = record(22, role="calibration", category="camera", views=10,
                             source_split="validation")
        labels = label_records([unsupported], fold["benchmarks"])
        self.assertEqual(labels["labels"], [])
        self.assertEqual(labels["exclusions"][0]["reason"], "unsupported_fit_cell")

    def test_data_use_gate_blocks_real_manifest(self):
        result = freeze_manifest(
            [record(1)], cutoff=datetime(2026, 10, 1), protocol=PROTOCOL,
            data_use_record=unverified_data_use(),
        )
        self.assertEqual(result["status"], "blocked_data_use")
        self.assertIsNone(result["manifest"])


class OutcomeDatasetDatabaseTests(unittest.TestCase):
    setUp = fixtures.Phase20KeywordGapEvidenceTests.setUp
    tearDown = fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def _observation(self, row, *, observed_at, views=0, status="complete", version="youtube_play_start_view_v2"):
        run = ReferenceStatisticsRun(
            actor="fixture", status="completed", started_at=observed_at,
            completed_at=observed_at, candidate_count=1,
        )
        self.db.add(run)
        self.db.flush()
        self.db.add(ReferenceVideoStatistic(
            run_id=run.run_id, dataset_id=row.dataset_id,
            video_id=row.source_youtube_id, source_url=row.video_url,
            observed_at=observed_at, status=status,
            views=views if status in {"complete", "partial"} else None,
            likes=0 if status == "complete" else None,
            comments=0 if status == "complete" else None,
            view_metric_version=version,
        ))
        self.db.commit()

    def test_cutoff_zero_views_failure_staleness_and_negative_age_are_explicit(self):
        cutoff = datetime(2026, 10, 8, 12)
        rows = self.db.query(DatasetContent).order_by(DatasetContent.dataset_id).limit(8).all()
        for row in rows:
            metadata = json.loads(row.raw_metadata_json)
            metadata.update(content_format="long_form", outcome_sampling_frame="general_protocol_v1")
            row.raw_metadata_json = json.dumps(metadata)
            row.published_at = cutoff - timedelta(days=30)
        rows[4].published_at = cutoff + timedelta(days=1)
        rows[7].data_split = "validation"
        self.db.commit()
        self._observation(rows[0], observed_at=cutoff - timedelta(hours=1), views=0)
        self._observation(rows[1], observed_at=cutoff + timedelta(hours=1), views=10)
        self._observation(rows[2], observed_at=cutoff - timedelta(hours=1), status="failed")
        self._observation(rows[3], observed_at=cutoff - timedelta(hours=25), views=10)
        self._observation(rows[4], observed_at=cutoff - timedelta(hours=1), views=10)
        self._observation(rows[5], observed_at=cutoff - timedelta(hours=1), views=10,
                          version="unknown_v1")
        self._observation(rows[6], observed_at=datetime(2026, 8, 23, 12), views=10,
                          version="youtube_play_start_view_v2")
        self._observation(rows[7], observed_at=cutoff - timedelta(hours=1), views=10)
        with TemporaryDirectory() as temp:
            records = database_source_records(
                self.db, cutoff=cutoff, protocol=PROTOCOL, repo_root=Path(temp)
            )
        by_id = {item["dataset_id"]: item for item in records}
        self.assertEqual(by_id[rows[0].dataset_id]["observation"]["views"], 0)
        self.assertIn("observations_after_cutoff_only", by_id[rows[1].dataset_id]["exclusion_reasons"])
        self.assertIn("no_successful_views_observation", by_id[rows[2].dataset_id]["exclusion_reasons"])
        self.assertIn("successful_observation_stale", by_id[rows[3].dataset_id]["exclusion_reasons"])
        self.assertIn("invalid_age_context", by_id[rows[4].dataset_id]["exclusion_reasons"])
        self.assertIn("unsupported_view_metric_version", by_id[rows[5].dataset_id]["exclusion_reasons"])
        self.assertIn("view_metric_version_timestamp_mismatch", by_id[rows[6].dataset_id]["exclusion_reasons"])
        self.assertIn("outcome_selected_holdout_forbidden", by_id[rows[7].dataset_id]["exclusion_reasons"])

    def test_collection_dry_run_has_no_write_and_live_is_idempotent_without_eligibility_changes(self):
        rows = self.db.query(DatasetContent).order_by(DatasetContent.dataset_id).limit(2).all()
        source = [record(index + 1) for index in range(2)]
        for item, row in zip(source, rows):
            item.update(
                dataset_id=row.dataset_id, source_youtube_id=row.source_youtube_id,
                source_url=row.video_url, source_split=row.data_split,
                split_protection="none",
            )
        manifest = build_collection_manifest(
            source, cutoff=datetime(2026, 10, 8, 12),
            protocol_sha256=PROTOCOL["protocol_sha256"],
        )
        before = (
            self.db.query(ReferenceStatisticsRun).count(),
            self.db.query(ReferenceVideoStatistic).count(),
        )
        result = collect_outcome_statistics(
            manifest=manifest, data_use_record=confirmed_data_use(),
            session_factory=sessionmaker(bind=self.engine),
            now=datetime(2026, 10, 8, 12), dry_run=True,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["api_calls"], 0)
        self.assertEqual(before, (
            self.db.query(ReferenceStatisticsRun).count(),
            self.db.query(ReferenceVideoStatistic).count(),
        ))
        eligibility = [(row.data_split, row.is_training_eligible,
                        row.is_keyword_recommendation_eligible) for row in rows]
        attempts = {"count": 0}

        def fetch(ids):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise TimeoutError("secret=https://example.invalid?key=never-print")
            return {"items": [{"id": value, "statistics": {
                "viewCount": "0", "likeCount": "0", "commentCount": "0"
            }} for value in ids]}

        live = collect_outcome_statistics(
            manifest=manifest, data_use_record=confirmed_data_use(),
            session_factory=sessionmaker(bind=self.engine),
            now=datetime(2026, 10, 8, 12), dry_run=False, approved=True,
            fetch=fetch,
        )
        self.assertEqual(live["status"], "completed")
        self.assertEqual(live["requests_used"], 2)
        self.assertNotIn("secret", json.dumps(live))
        again = collect_outcome_statistics(
            manifest=manifest, data_use_record=confirmed_data_use(),
            session_factory=sessionmaker(bind=self.engine),
            now=datetime(2026, 10, 8, 12), dry_run=False, approved=True,
            fetch=lambda _ids: self.fail("idempotent retry called provider"),
        )
        self.assertEqual(again["status"], "already_collected")
        self.db.expire_all()
        self.assertEqual(eligibility, [
            (self.db.get(DatasetContent, row.dataset_id).data_split,
             self.db.get(DatasetContent, row.dataset_id).is_training_eligible,
             self.db.get(DatasetContent, row.dataset_id).is_keyword_recommendation_eligible)
            for row in rows
        ])

    def test_unverified_rights_block_collection_before_api_or_write(self):
        row = self.db.query(DatasetContent).first()
        source = [record(1)]
        source[0].update(dataset_id=row.dataset_id, source_youtube_id=row.source_youtube_id,
                         source_url=row.video_url, source_split=row.data_split,
                         split_protection="none")
        manifest = build_collection_manifest(
            source, cutoff=datetime(2026, 10, 8),
            protocol_sha256=PROTOCOL["protocol_sha256"],
        )
        before = self.db.query(ReferenceStatisticsRun).count()
        result = collect_outcome_statistics(
            manifest=manifest, data_use_record=unverified_data_use(),
            session_factory=sessionmaker(bind=self.engine), dry_run=False,
            approved=True, fetch=lambda _ids: self.fail("provider must not run"),
            now=datetime(2026, 10, 8),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(before, self.db.query(ReferenceStatisticsRun).count())

    def test_live_quota_failure_is_counted_and_persists_cooldown(self):
        row = self.db.query(DatasetContent).first()
        source = [record(1)]
        source[0].update(dataset_id=row.dataset_id, source_youtube_id=row.source_youtube_id,
                         source_url=row.video_url, source_split=row.data_split,
                         split_protection="none")
        manifest = build_collection_manifest(
            source, cutoff=datetime(2026, 10, 8, 13),
            protocol_sha256=PROTOCOL["protocol_sha256"],
        )
        self.db.add(ReferenceStatisticsConfig(
            config_id=1, enabled=True, interval_seconds=3600,
            daily_request_budget=100,
        ))
        self.db.commit()

        def quota(_ids):
            raise YouTubeQuotaExceededError("videos", 403, "quotaExceeded")

        result = collect_outcome_statistics(
            manifest=manifest, data_use_record=confirmed_data_use(),
            session_factory=sessionmaker(bind=self.engine), dry_run=False,
            approved=True, fetch=quota, now=datetime(2026, 10, 8, 13),
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "provider_quota")
        self.assertEqual(result["requests_used"], 1)
        self.db.expire_all()
        self.assertEqual(self.db.get(ReferenceStatisticsConfig, 1).blocked_until,
                         datetime(2026, 10, 9, 13))

    def test_shared_daily_budget_blocks_before_provider(self):
        row = self.db.query(DatasetContent).first()
        source = [record(1)]
        source[0].update(dataset_id=row.dataset_id, source_youtube_id=row.source_youtube_id,
                         source_url=row.video_url, source_split=row.data_split,
                         split_protection="none")
        manifest = build_collection_manifest(
            source, cutoff=datetime(2026, 10, 8, 14),
            protocol_sha256=PROTOCOL["protocol_sha256"],
        )
        self.db.add(ReferenceStatisticsConfig(
            config_id=1, enabled=True, interval_seconds=3600,
            daily_request_budget=1,
        ))
        self.db.add(ReferenceStatisticsRun(
            actor="reference", status="completed",
            started_at=datetime(2026, 10, 8, 13), completed_at=datetime(2026, 10, 8, 13),
            requests_used=1, candidate_count=1,
        ))
        self.db.commit()
        result = collect_outcome_statistics(
            manifest=manifest, data_use_record=confirmed_data_use(),
            session_factory=sessionmaker(bind=self.engine), dry_run=False,
            approved=True, fetch=lambda _ids: self.fail("budget must block provider"),
            now=datetime(2026, 10, 8, 14),
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("daily_request_budget_insufficient", result["reason_codes"])


class OutcomeMigrationTests(unittest.TestCase):
    def test_migration_is_additive_idempotent_and_preserves_old_rows(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE reference_statistics_runs ("
                "run_id INTEGER PRIMARY KEY, status VARCHAR(32) NOT NULL, "
                "actor VARCHAR(32) NOT NULL, started_at DATETIME NOT NULL, "
                "completed_at DATETIME, requests_used INTEGER NOT NULL DEFAULT 0, "
                "candidate_count INTEGER NOT NULL DEFAULT 0, error_code VARCHAR(64))"
            ))
            connection.execute(text(
                "INSERT INTO reference_statistics_runs "
                "(run_id,status,actor,started_at) VALUES (1,'completed','legacy','2026-10-01')"
            ))
        first = migrate_outcome_statistics_schema(engine)
        second = migrate_outcome_statistics_schema(engine)
        self.assertEqual(set(first["added_columns"]), {
            "purpose", "manifest_sha256", "idempotency_key", "split_protection"
        })
        self.assertEqual(second, {"added_columns": [], "added_indexes": []})
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text(
                "SELECT COUNT(*) FROM reference_statistics_runs WHERE run_id=1"
            )).scalar(), 1)
        columns = {item["name"] for item in inspect(engine).get_columns("reference_statistics_runs")}
        self.assertIn("manifest_sha256", columns)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
