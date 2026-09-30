"""Synthetic regressions for the Phase 5-7 review, never human study results."""
import copy
import json
import tempfile
import unittest
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.analysis_evaluation import (
    REVIEW_SCHEMA_VERSION, allocate_variant_orders, audit_study_manifest,
    build_presentation_variants, digest, freeze_utility_protocol,
    pilot_classification_metrics, utility_metrics, validate_utility_responses,
)
from app.services.recommendation_utility_study import (
    audit_actionable_evidence, build_blind_packets, stable_context_lock, study_readiness,
)
from app.services.revision_comparisons import _accepted_classification, _context_status
from app.services.recommendation_evidence import _observation, user_context
from scripts import evaluate_analysis as runner
from tests.test_recommendation_utility_evaluation import manifest_case, recommendation_result
from tests import test_phase20_keyword_gap_evidence as database_fixtures


class PhaseReviewTests(unittest.TestCase):
    def setUp(self):
        self.protocol = freeze_utility_protocol(study_id="synthetic-review", manifest_sha256="a"*64,
            context_lock={}, reviewer_ids=["r01", "r02", "r03"], seed=21)

    def study(self, result=None):
        outputs = {"phone-01": {"variants": build_presentation_variants(
            recommendation_result() if result is None else result), "analysis_status": "completed"}}
        allocation = allocate_variant_orders(study_id=self.protocol["study_id"],
            protocol_sha256=self.protocol["protocol_sha256"], case_ids=list(outputs),
            reviewer_ids=["r01"], seed=21)
        _, private = build_blind_packets(protocol=self.protocol, allocations=allocation, case_outputs=outputs)
        ratings = []
        for row in private["allocations"]:
            scores = {key: 4 for key in ("relevance", "novelty", "clarity", "actionability")}
            scores["evidence_correctness"] = 4 if row["variant_id"] == "C" else "N/A"
            ratings.append({**row, "scores": scores, "critical_flags": []})
        response = {"schema_version": REVIEW_SCHEMA_VERSION, "study_id": self.protocol["study_id"],
            "protocol_sha256": self.protocol["protocol_sha256"], "reviewer_id": "r01", "consent": True,
            "pre_reviews": [{"case_id": "phone-01", "watched_video": True,
                "improvement_opportunity": "yes", "notes": "Synthetic fixture only"}], "ratings": ratings}
        return outputs, private["allocations"], response

    def validate(self, outputs, allocations, response):
        return validate_utility_responses(response_documents=[response], allocations=allocations,
            protocol=self.protocol, case_outputs=outputs)

    def test_settings_capture_time_is_not_semantic_but_model_is(self):
        context = {"settings": {"captured_at": "old", "asr_model": "small"},
                   "method_versions": {"buckets": (1, 2)}}
        later = copy.deepcopy(context)
        later["settings"]["captured_at"] = "new"
        self.assertEqual(stable_context_lock(context), stable_context_lock(later))
        self.assertEqual(stable_context_lock(context), json.loads(json.dumps(stable_context_lock(context))))
        later["settings"]["asr_model"] = "large"
        self.assertNotEqual(stable_context_lock(context), stable_context_lock(later))

    def test_orders_balanced_within_each_reviewer_and_first_position_per_clip(self):
        allocations = allocate_variant_orders(study_id="synthetic", protocol_sha256="abc",
            case_ids=[f"case-{i}" for i in range(12)], reviewer_ids=["r1", "r2", "r3"], seed=42)
        groups = defaultdict(list)
        for row in allocations:
            groups[row["case_id"], row["reviewer_id"]].append(row)
        by_reviewer, first_by_case = defaultdict(Counter), defaultdict(Counter)
        for (case, reviewer), rows in groups.items():
            order = "".join(r["variant_id"] for r in sorted(rows, key=lambda r: r["position"]))
            by_reviewer[reviewer][order] += 1
            first_by_case[case][order[0]] += 1
        self.assertTrue(all(len(c) == 6 and set(c.values()) == {2} for c in by_reviewer.values()))
        self.assertTrue(all(dict(c) == {"A": 1, "B": 1, "C": 1} for c in first_by_case.values()))

    def test_no_pre_review_no_ratings_and_boolean_is_not_a_score(self):
        outputs, allocations, response = self.study()
        response["pre_reviews"] = []
        self.assertEqual(self.validate(outputs, allocations, response)["accepted_rating_count"], 0)
        outputs, allocations, response = self.study()
        response["ratings"][0]["scores"]["actionability"] = True
        checked = self.validate(outputs, allocations, response)
        self.assertIn("invalid_score_actionability", [r["reason"] for r in checked["rejected"]])

    def test_modified_payload_rejected_even_if_hash_field_unchanged(self):
        outputs, allocations, response = self.study()
        outputs["phone-01"]["variants"]["C"]["items"][0]["evidence"]["support_count"] = 999
        checked = self.validate(outputs, allocations, response)
        self.assertIn("output_integrity_mismatch", [r["reason"] for r in checked["rejected"]])

    def test_failed_jobs_do_not_create_successful_abstention_packets(self):
        outputs, allocations, _ = self.study()
        outputs["phone-01"].update(analysis_status="failed", variants={})
        packets, private = build_blind_packets(protocol=self.protocol, allocations=allocations, case_outputs=outputs)
        self.assertEqual(packets, {})
        self.assertEqual(private["allocations"], [])

    def test_three_reviewers_globally_is_not_three_reviews_per_clip(self):
        outputs, ratings, pre = {}, [], []
        for i in range(6):
            case = f"phone-{i}"
            outputs[case] = {"spec": {"role": "heldout", "expected_label": "phone"}, "exclusions": []}
            for reviewer in ["r01", "r02", "r03"]:
                pre.append({"case_id": case, "reviewer_id": reviewer, "improvement_opportunity": "yes"})
            for variant in ["A", "B", "C"]:
                ratings.append({"case_id": case, "reviewer_id": f"r0{i%3+1}", "variant_id": variant,
                    "scores": {"actionability": 3 if variant == "A" else 5,
                               "relevance": 5, "novelty": 5, "clarity": 5, "evidence_correctness": 5}})
        result = utility_metrics(validated={"ratings": ratings, "pre_reviews": pre}, case_outputs=outputs)
        self.assertEqual(result["status"], "insufficient_utility_evaluation")
        self.assertEqual(len(result["incomplete_primary_cases"]), 6)

    def test_failed_unknowns_do_not_pass_classification(self):
        rows = [{"role": "heldout", "expected_label": label, "predicted_label": label,
                 "manifest_eligible": True} for label in ("phone", "camera", "laptop", "unknown") for _ in range(3)]
        for row in rows[-3:]:
            row.update(error="ASR failed", predicted_label=None)
        result = pilot_classification_metrics(rows)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["unknown_rejection_numerator"], 0)

    def test_fresh_clips_from_same_creator_are_not_duplicate_media(self):
        cases = [manifest_case(f"phone-{i}", creator_group_key="fresh-creator", media_sha256=f"{i:064x}")
                 for i in range(1, 4)]
        audit = audit_study_manifest({"cases": cases})
        self.assertEqual(audit["eligible_counts"]["phone"], 3)

    def test_missing_classification_fails_closed_and_cleaned_offsets_use_cleaned_text(self):
        self.assertFalse(_accepted_classification({"domain": "phone"})[0])
        raw = "A long preamble. " + "noise " * 40 + "fast charge"
        context = user_context(transcript="charging test", raw_transcript=raw)
        observation = _observation(context, ["charging"])
        self.assertEqual(observation["source_field"], "cleaned_transcript")
        self.assertEqual(_context_status(context, ["charging"], ["test"], observation)["status"], "context_present")

    def test_artifact_seal_detects_tampering_and_does_not_cover_new_human_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner.write(root / "cases.json", {"data": "original"})
            runner.seal_artifacts(root)
            (root / "responses").mkdir()
            runner.write(root / "responses" / "new.json", {"ratings": []})
            runner.verify_artifacts(root)
            runner.write(root / "cases.json", {"data": "modified"})
            with self.assertRaisesRegex(ValueError, "Frozen artifact changed"):
                runner.verify_artifacts(root)

    def test_invented_timestamp_is_not_valid_just_because_it_is_a_dictionary(self):
        result = recommendation_result()
        bundle = result["recommendation"]["evidence_bundle"]
        for doc in bundle["reference_documents"]:
            doc.update(transcript="charging", data_split="train", segments=[])
        for ref in bundle["action_topics"][0]["references"]:
            ref["occurrences"] = [{"quote": "charging", "quote_start_char": 0, "quote_end_char": 8,
                                   "timestamp": {"start_seconds": 0, "end_seconds": 1}}]
        self.assertIn("invalid_timestamp", audit_actionable_evidence(result)[0]["structural_issues"])

    def test_positive_runner_persists_all_cases_and_one_failure_without_rating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, cases = Path(tmp), []
            scenarios = {"phone": ["general_review", "camera_focus", "gaming_focus"],
                         "camera": ["dedicated_camera", "video_focus", "phone_camera_confusion"],
                         "laptop": ["general_productivity", "gaming_laptop", "confusion_hard_case"],
                         "unknown": ["accessory", "non_it", "accessory"]}
            for label, kinds in scenarios.items():
                for i, scenario in enumerate(kinds):
                    path = root / f"{label}-{i}.mp4"
                    path.write_bytes(f"synthetic-media-{label}-{i}".encode())
                    cases.append(manifest_case(f"{label}-{i}", label, video_path=str(path),
                        scenario_kind=scenario, media_sha256=runner.file_hash(path)))
            manifest = {"cases": cases}
            audit = audit_study_manifest(manifest)
            context = {"settings": {"asr_model": "small", "hook_duration_seconds": 60,
                        "upload_max_duration_seconds": 300, "captured_at": "initial"},
                       "statistics_cutoff": "2026-09-30T10:00:00Z"}
            protocol = freeze_utility_protocol(study_id="synthetic-runner", manifest_sha256=digest(manifest),
                context_lock=stable_context_lock(context), reviewer_ids=["r01", "r02", "r03"])
            allocations = allocate_variant_orders(study_id=protocol["study_id"],
                protocol_sha256=protocol["protocol_sha256"], reviewer_ids=protocol["reviewer_ids"],
                case_ids=[c["case_id"] for c in cases], seed=protocol["seed"])
            prepared = root / "prepared"
            prepared.mkdir()
            for name, value in {"manifest": manifest, "manifest-audit": audit, "protocol": protocol,
                "readiness": study_readiness(manifest_audit=audit, reviewer_ids=protocol["reviewer_ids"]),
                "allocation-plan.private": allocations}.items():
                runner.write(prepared / f"{name}.json", value)
            runner.seal_artifacts(prepared)
            context["settings"]["captured_at"] = "later"
            def fake_analysis(path, **kwargs):
                if "camera-0" in path:
                    raise RuntimeError("Synthetic ASR failure")
                return {"cleaned_transcript": Path(path).stem,
                        "analysis": {"stt_meta": {"transcript_source": "speech_to_text"}}}
            recommendation = recommendation_result()["recommendation"]
            recommendation["domain"] = "phone"
            args = SimpleNamespace(prepared=str(prepared), out=str(root / "run"))
            with patch("app.database.db.SessionLocal", return_value=MagicMock()) as db, \
                    patch.object(runner, "database_context", return_value=(context, {}, [], [])), \
                    patch("app.services.ai_pipeline.analyze_video", side_effect=fake_analysis) as asr, \
                    patch("app.services.media_validation.validate_user_upload_duration", return_value=120), \
                    patch("app.routes.analyze._build_recommendation", return_value=(recommendation, {})) as recommend:
                runner.run_study(args)
                self.assertEqual(asr.call_count, 12)
                self.assertEqual(recommend.call_count, 11)
                self.assertEqual(recommend.call_args.kwargs["evidence_as_of"].isoformat(), "2026-09-30T10:00:00")
                db.return_value.commit.assert_not_called()
                with self.assertRaises(FileExistsError):
                    runner.run_study(args)
                self.assertEqual(asr.call_count, 12)
            run = root / "run"
            runner.verify_artifacts(run)
            saved = runner.read(run / "cases.json")["cases"]
            self.assertEqual(len(saved), 12)
            failed = next(c for c in saved if c["case_id"] == "camera-0")
            self.assertEqual(failed["variants"], {})
            self.assertEqual(failed["analysis_status"], "failed")
            key = runner.read(run / "private" / "allocation-key.json")
            self.assertEqual(len(key["allocations"]), 11*3*3)


class FrozenDatabaseContextTests(unittest.TestCase):
    setUp = database_fixtures.Phase20KeywordGapEvidenceTests.setUp
    tearDown = database_fixtures.Phase20KeywordGapEvidenceTests.tearDown
    _add_phone_rows = database_fixtures.Phase20KeywordGapEvidenceTests._add_phone_rows

    def test_statistics_history_changes_invalidate_context_but_capture_time_does_not(self):
        from app.database.models import DatasetContent, ReferenceStatisticsRun, ReferenceVideoStatistic, SystemConfig
        self.db.add(SystemConfig(user_id=None))
        cutoff = datetime.utcnow() + timedelta(seconds=1)
        run = ReferenceStatisticsRun(actor="synthetic-test", status="completed", started_at=cutoff)
        self.db.add(run)
        self.db.flush()
        row = self.db.query(DatasetContent).first()
        observation = ReferenceVideoStatistic(run_id=run.run_id, dataset_id=row.dataset_id,
            video_id=row.source_youtube_id, source_url=row.video_url, observed_at=cutoff,
            status="complete", views=1000, view_metric_version="youtube_play_start_view_v2")
        self.db.add(observation)
        self.db.commit()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "model.bin"
            artifact.write_bytes(b"synthetic-model-not-for-inference")
            manifest = root / "manifest.json"
            runner.write(manifest, {"artifacts": {"splits": {}}})
            with patch("app.services.classification.get_active_classification_model", return_value=SimpleNamespace(artifact_path=str(artifact))), \
                    patch("app.services.classification_training.load_classification_artifact", return_value={"dataset_manifest_path": str(manifest)}), \
                    patch("app.services.analysis_settings.capture_analysis_settings", side_effect=[
                        {"asr_model": "small", "captured_at": "one"},
                        {"asr_model": "small", "captured_at": "two"},
                        {"asr_model": "small", "captured_at": "three"}]):
                first = runner.database_context(self.db, as_of=cutoff)[0]
                second = runner.database_context(self.db, as_of=cutoff)[0]
                self.assertEqual(stable_context_lock(first), stable_context_lock(second))
                self.assertEqual(first["reference_count"], 30)
                observation.views = 900
                self.db.commit()
                changed = runner.database_context(self.db, as_of=cutoff)[0]
                self.assertNotEqual(first["statistics_sha256"], changed["statistics_sha256"])
                self.assertEqual(first["reference_sha256"], changed["reference_sha256"])


if __name__ == "__main__":
    unittest.main()
