import copy
import json
from pathlib import Path
import tempfile
import unittest

from app.services.analysis_evaluation import (
    REVIEW_SCHEMA_VERSION,
    allocate_variant_orders,
    allocation_balance,
    assert_variant_parity,
    audit_study_manifest,
    build_presentation_variants,
    freeze_utility_protocol,
    human_review_summary,
    pilot_classification_metrics,
    utility_metrics,
    validate_utility_responses,
    verify_utility_protocol,
)
from app.services.recommendation_utility_study import (
    audit_actionable_evidence, build_blind_packets,
    evidence_correctness_summary,
    render_review_html,
    study_readiness,
)
from scripts.evaluate_analysis import new_output, report_study, seal_artifacts, write


def manifest_case(case_id="phone-01", label="phone", **updates):
    default_scenario = {"phone": "general_review", "camera": "dedicated_camera",
                        "laptop": "general_productivity", "unknown": "accessory"}[label]
    value = {
        "case_id": case_id,
        "video_path": f"heldout/{case_id}.mp4",
        "media_sha256": (case_id[0] if case_id[0] in "abcdef" else "a") * 64,
        "role": "heldout",
        "source_kind": "self_recorded",
        "expected_label": label,
        "scenario_kind": default_scenario,
        "label_reviewed_by": "labeler-01",
        "source_youtube_id": "",
        "source_channel_id": "",
        "creator_group_key": f"creator-{case_id}",
        "independence_confirmed_by": "auditor-01",
        "provenance_note": "Recorded after the frozen model and never used for development",
        "registered_at": "2026-09-30T06:00:00Z",
        "consent_status": "granted",
    }
    value.update(updates)
    return value


def recommendation_result():
    topic = "topic-battery"
    return {
        "recommendation": {
            "actionable_recommendations": {
                "status": "ready",
                "limitation": "เป็นความสัมพันธ์ ไม่ใช่เหตุและผล",
                "items": [{
                    "id": "advice-1", "evidence_topic_id": topic, "title": "ความเร็วในการชาร์จ",
                    "finding": "ยังไม่พบหัวข้อนี้", "proposal": "เพิ่มการทดสอบ",
                    "condition": "หากรุ่นนี้รองรับ", "steps": ["ระบุกำลังชาร์จ", "จับเวลา"],
                    "example": "ลองชาร์จจาก 20 ถึง 80 เปอร์เซ็นต์",
                    "reason": "พบในคลิปอ้างอิง", "relevance_reason": "เกี่ยวข้องกับแบตเตอรี่",
                    "support_count": 2, "channel_count": 2, "sample_size": 10,
                    "supporting_dataset_row_ids": [1, 2],
                }],
            },
            "evidence_bundle": {
                "action_topics": [{
                    "topic_id": topic,
                    "references": [
                        {"dataset_id": 1, "occurrences": [{"quote": "ชาร์จได้เร็ว"}]},
                        {"dataset_id": 2, "occurrences": [{"quote": "ทดสอบชาร์จ"}]},
                    ],
                }],
                "reference_documents": [
                    {"dataset_id": 1, "video_id": "v1", "channel_id": "c1",
                     "published_at": "2026-09-01", "statistics_captured_at": "2026-09-29"},
                    {"dataset_id": 2, "video_id": "v2", "channel_id": "c2",
                     "published_at": "2026-09-02", "statistics_captured_at": "2026-09-29"},
                ],
                "topic_comparisons": {"items": [{"evidence_topic_id": topic, "status": "reference_only"}]},
            },
        }
    }


class RecommendationUtilityEvaluationTests(unittest.TestCase):
    def protocol(self, reviewers=("r01", "r02", "r03")):
        return freeze_utility_protocol(
            study_id="pilot-20260930", manifest_sha256="a" * 64,
            context_lock={"model": "frozen"}, reviewer_ids=list(reviewers),
            seed=42, created_at="2026-09-30T06:10:00Z")

    def test_manifest_blocks_prior_hash_video_channel_creator_and_renamed_file(self):
        case = manifest_case(
            video_path="renamed/new-name.mp4", media_sha256="b" * 64,
            source_kind="public_video", source_youtube_id="video-1",
            source_channel_id="channel-1", creator_group_key="creator-1",
            provenance_note="Public video registered before prediction",
            consent_status="public_research_allowed")
        prior = [{"media_sha256": "b" * 64, "source_youtube_id": "video-1",
                  "source_channel_id": "channel-1", "creator_group_key": "creator-1",
                  "registry_source": "old-regression"}]
        audit = audit_study_manifest({"cases": [case]}, prior_records=prior)
        reasons = set(audit["cases"][0]["exclusions"])
        self.assertTrue({"previously_used_media", "previously_used_video",
                         "development_channel_overlap", "development_creator_overlap"} <= reasons)
        self.assertNotIn("video_path", audit["cases"][0]["identity_matches"][0])

    def test_protocol_is_frozen_and_stale_hash_is_rejected(self):
        protocol = self.protocol()
        self.assertTrue(verify_utility_protocol(protocol))
        changed = copy.deepcopy(protocol)
        changed["seed"] = 99
        self.assertFalse(verify_utility_protocol(changed))
        self.assertIn("causal_engagement_gain", protocol["claims_not_measured"])

    def test_variants_have_same_topics_and_b_c_have_identical_actions(self):
        variants = build_presentation_variants(recommendation_result())
        self.assertEqual([row["title"] for row in variants["A"]["items"]],
                         [row["title"] for row in variants["C"]["items"]])
        self.assertEqual(variants["B"]["items"][0]["action"], variants["C"]["items"][0]["action"])
        broken = copy.deepcopy(variants)
        broken["C"]["items"][0]["title"] = "หัวข้อใหม่"
        with self.assertRaisesRegex(ValueError, "identical topics"):
            assert_variant_parity(broken)

    def test_all_six_orders_are_balanced_and_deterministic(self):
        protocol = self.protocol()
        kwargs = {"study_id": protocol["study_id"], "protocol_sha256": protocol["protocol_sha256"],
                  "case_ids": [f"case-{i:02}" for i in range(12)],
                  "reviewer_ids": protocol["reviewer_ids"], "seed": protocol["seed"]}
        first = allocate_variant_orders(**kwargs)
        self.assertEqual(first, allocate_variant_orders(**kwargs))
        balance = allocation_balance(first)
        self.assertEqual(set(balance["order_counts"]), {"ABC", "ACB", "BAC", "BCA", "CAB", "CBA"})
        self.assertEqual(balance["max_order_imbalance"], 0)
        self.assertEqual(set(balance["first_variant_counts"].values()), {12})

    def test_blind_packets_hide_variant_and_use_opaque_rating_units(self):
        protocol = self.protocol(("r01",))
        variants = build_presentation_variants(recommendation_result())
        allocations = allocate_variant_orders(
            study_id=protocol["study_id"], protocol_sha256=protocol["protocol_sha256"],
            case_ids=["phone-01"], reviewer_ids=["r01"], seed=42)
        packets, private = build_blind_packets(
            protocol=protocol, allocations=allocations,
            case_outputs={"phone-01": {"variants": variants, "video_uri": "file:///clip.mp4",
                                        "analysis_status": "completed"}})
        public = str(packets["r01"])
        self.assertNotIn("variant_id", public)
        self.assertNotIn("phone-01:A:set", public)
        self.assertEqual({row["variant_id"] for row in private["allocations"]}, {"A", "B", "C"})
        html = render_review_html(packets["r01"])
        self.assertIn("ดูคลิปก่อนตอบ", html)
        self.assertIn("download", html)

    def test_response_validation_accepts_multiple_raters_but_rejects_exact_duplicate_and_stale_output(self):
        protocol = self.protocol(("r01", "r02"))
        variants = build_presentation_variants(recommendation_result())
        outputs = {"phone-01": {"variants": variants}}
        allocations = allocate_variant_orders(
            study_id=protocol["study_id"], protocol_sha256=protocol["protocol_sha256"],
            case_ids=["phone-01"], reviewer_ids=protocol["reviewer_ids"], seed=42)
        _, private = build_blind_packets(protocol=protocol, allocations=allocations,
                                          case_outputs={"phone-01": {**outputs["phone-01"], "video_uri": "x"}})
        documents = []
        for reviewer in protocol["reviewer_ids"]:
            ratings = []
            for row in [item for item in private["allocations"] if item["reviewer_id"] == reviewer]:
                scores = {field: 4 for field in ("relevance", "novelty", "clarity", "actionability")}
                scores["evidence_correctness"] = 4 if row["variant_id"] == "C" else "N/A"
                scores["abstention_appropriateness"] = "N/A"
                ratings.append({"case_id": "phone-01", "presentation_id": row["presentation_id"],
                                "unit_id": row["unit_id"], "output_sha256": row["output_sha256"],
                                "scores": scores, "missed_opportunity": False,
                                "low_score_reason": "", "critical_flags": []})
            documents.append({"schema_version": REVIEW_SCHEMA_VERSION, "study_id": protocol["study_id"],
                              "protocol_sha256": protocol["protocol_sha256"], "reviewer_id": reviewer,
                              "consent": True, "pre_reviews": [{"case_id": "phone-01", "watched_video": True,
                                  "improvement_opportunity": "yes", "notes": "Fixture pre-review"}], "ratings": ratings})
        documents.append(copy.deepcopy(documents[0]))
        documents[1]["ratings"][0]["output_sha256"] = "stale"
        result = validate_utility_responses(response_documents=documents,
                                            allocations=private["allocations"],
                                            protocol=protocol, case_outputs=outputs)
        self.assertEqual(result["accepted_reviewer_count"], 2)
        self.assertIn("duplicate_rating", {row["reason"] for row in result["rejected"]})
        self.assertIn("stale_output_hash", {row["reason"] for row in result["rejected"]})

    def test_empty_advice_missing_scores_and_failures_are_not_silently_zero_or_unknown(self):
        rows = [
            {"role": "heldout", "expected_label": "phone", "predicted_label": "phone",
             "manifest_eligible": True, "exclusions": []},
            {"role": "heldout", "expected_label": "camera", "manifest_eligible": True,
             "error": "decode failed", "exclusions": ["analysis_not_completed"]},
            {"role": "heldout", "expected_label": "laptop", "predicted_label": "unknown",
             "manifest_eligible": True, "exclusions": []},
            {"role": "heldout", "expected_label": "unknown", "predicted_label": "unknown",
             "manifest_eligible": True, "exclusions": []},
        ]
        metrics = pilot_classification_metrics(rows)
        self.assertEqual(metrics["registered_eligible_count"], 4)
        self.assertEqual(metrics["failure_count"], 1)
        self.assertEqual(metrics["end_to_end_coverage"], 0.75)
        self.assertEqual(metrics["end_to_end_accuracy"], 0.5)
        self.assertEqual(metrics["unknown_rejection_numerator"], 1)
        self.assertEqual(metrics["unknown_false_acceptance_numerator"], 0)
        self.assertTrue(metrics["failures_are_not_unknown_rejections"])
        self.assertEqual(utility_metrics(validated={"ratings": []}, case_outputs={})["status"], "not_evaluated")

    def test_empty_advice_uses_abstention_score_and_missing_value_is_rejected(self):
        protocol = self.protocol(("r01",))
        variants = build_presentation_variants({})
        outputs = {"unknown-01": {"variants": variants}}
        allocations = allocate_variant_orders(
            study_id=protocol["study_id"], protocol_sha256=protocol["protocol_sha256"],
            case_ids=["unknown-01"], reviewer_ids=["r01"], seed=42)
        _, private = build_blind_packets(
            protocol=protocol, allocations=allocations,
            case_outputs={"unknown-01": {"variants": variants, "video_uri": "x"}})
        ratings = []
        for index, row in enumerate(private["allocations"]):
            scores = {"evidence_correctness": "N/A"}
            if index:
                scores["abstention_appropriateness"] = 5
            ratings.append({"case_id": "unknown-01", "presentation_id": row["presentation_id"],
                            "unit_id": row["unit_id"], "output_sha256": row["output_sha256"],
                            "scores": scores, "missed_opportunity": False,
                            "low_score_reason": "", "critical_flags": []})
        document = {"schema_version": REVIEW_SCHEMA_VERSION, "study_id": protocol["study_id"],
                    "protocol_sha256": protocol["protocol_sha256"], "reviewer_id": "r01",
                    "consent": True, "pre_reviews": [{"case_id": "unknown-01", "watched_video": True,
                        "improvement_opportunity": "no", "notes": "Fixture pre-review"}], "ratings": ratings}
        result = validate_utility_responses(response_documents=[document],
                                            allocations=private["allocations"],
                                            protocol=protocol, case_outputs=outputs)
        self.assertEqual(result["accepted_rating_count"], 2)
        self.assertIn("invalid_abstention_score", {row["reason"] for row in result["rejected"]})

    def test_hand_computed_utility_aggregates_reviewers_then_clips(self):
        cases = {f"case-{i}": {"spec": {"role": "heldout", "expected_label": "phone"},
                               "exclusions": []} for i in range(6)}
        ratings, pre = [], []
        for case_id in cases:
            for reviewer in ("r01", "r02", "r03"):
                pre.append({"case_id": case_id, "reviewer_id": reviewer,
                            "improvement_opportunity": "yes"})
                for variant, actionability in (("A", 3), ("B", 4), ("C", 4)):
                    ratings.append({"case_id": case_id, "reviewer_id": reviewer,
                                    "variant_id": variant, "presentation_id": f"{case_id}-{reviewer}-{variant}",
                                    "scores": {"relevance": 4, "novelty": 4, "clarity": 4,
                                               "actionability": actionability,
                                               "evidence_correctness": 5 if variant == "C" else "N/A"},
                                    "critical_flags": []})
        result = utility_metrics(validated={"ratings": ratings, "pre_reviews": pre}, case_outputs=cases)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["criteria"]["B_minus_A_actionability"]["median"], 1)
        self.assertEqual(result["criteria"]["C_minus_B_actionability"]["median"], 0)
        self.assertEqual(result["primary_case_count"], 6)

    def test_readiness_requires_three_per_class_and_three_real_reviewers(self):
        cases = []
        sequence = 0
        scenarios = {
            "phone": ("general_review", "camera_focus", "gaming_focus"),
            "camera": ("dedicated_camera", "video_focus", "phone_camera_confusion"),
            "laptop": ("general_productivity", "gaming_laptop", "confusion_hard_case"),
            "unknown": ("accessory", "non_it", "accessory"),
        }
        for label in ("phone", "camera", "laptop", "unknown"):
            for index in range(1, 4):
                sequence += 1
                cases.append(manifest_case(f"{label}-{index}", label,
                                           scenario_kind=scenarios[label][index - 1],
                                           media_sha256=f"{sequence:064x}"))
        audit = audit_study_manifest({"cases": cases})
        self.assertEqual(study_readiness(manifest_audit=audit,
                                         reviewer_ids=["r1", "r2"])["state"],
                         "awaiting_fresh_clips_or_reviewers")
        self.assertEqual(study_readiness(manifest_audit=audit,
                                         reviewer_ids=["r1", "r2", "r3"])["state"],
                         "ready_for_prediction")

    def test_evidence_audit_does_not_mutate_output_and_legacy_zero_one_contract_remains(self):
        cases = {"c1": {"role": "heldout", "manifest_eligible": True,
                         "recommendation_checks": [{"structural_issues": ["bad_count"]}]}}
        original = copy.deepcopy(cases)
        summary = evidence_correctness_summary(cases)
        self.assertEqual(cases, original)
        self.assertEqual(summary["units_with_automated_issues"], 1)
        key = {"case_id": "old", "output_sha256": "hash", "lane": "missing_keywords", "index": "0"}
        review = {**key, "reviewer": "person", "relevant": "1", "not_already_covered": "1",
                  "evidence_correct": "1", "actionable": "0"}
        legacy = human_review_summary([review], [key])
        self.assertEqual(legacy["reviewed"], 1)
        self.assertEqual(legacy["pass_rates"]["actionable"], 0)

    def test_evaluation_artifact_directory_can_never_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new-run"
            self.assertEqual(new_output(target), target.resolve())
            marker = target / "keep.txt"
            marker.write_text("original", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                new_output(target)
            self.assertEqual(marker.read_text(encoding="utf-8"), "original")

    def test_report_without_human_responses_is_explicitly_not_evaluated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "run"
            (run / "private").mkdir(parents=True)
            protocol = self.protocol()
            write(run / "protocol.json", protocol)
            write(run / "readiness.json", {"state": "ready_for_prediction", "missing": []})
            write(run / "cases.json", {"cases": []})
            write(run / "private" / "allocation-key.json", {"allocations": []})
            seal_artifacts(run)
            args = type("Args", (), {"run": str(run), "responses": None,
                                      "adjudications": None, "out": str(root / "report")})()
            report_study(args)
            report = json.loads((root / "report" / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "tooling_ready")
            self.assertFalse(report["evaluation_complete"])
            self.assertEqual(report["recommendation_utility"]["status"], "not_evaluated")

    def test_actionable_evidence_audit_verifies_quotes_counts_and_causal_claims(self):
        result = recommendation_result()
        recommendation = result["recommendation"]
        documents = recommendation["evidence_bundle"]["reference_documents"]
        for index, document in enumerate(documents, 1):
            document.update({"data_split": "train", "transcript": "พูดถึงการชาร์จได้เร็ว",
                             "channel_id": f"c{index}", "video_id": f"v{index}"})
        references = recommendation["evidence_bundle"]["action_topics"][0]["references"]
        for reference in references:
            quote = "ชาร์จได้เร็ว" if reference["dataset_id"] == 1 else "การชาร์จ"
            text = documents[reference["dataset_id"] - 1]["transcript"]
            start = text.index(quote)
            reference["occurrences"] = [{"quote": quote, "quote_start_char": start,
                                          "quote_end_char": start + len(quote), "timestamp": None}]
        recommendation["actionable_recommendations"]["items"][0]["causal_engagement_claim"] = False
        self.assertEqual(audit_actionable_evidence(result)[0]["structural_issues"], [])
        recommendation["actionable_recommendations"]["items"][0]["causal_engagement_claim"] = True
        self.assertIn("causal_engagement_claim",
                      audit_actionable_evidence(result)[0]["structural_issues"])


if __name__ == "__main__":
    unittest.main()
