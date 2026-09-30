import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect, text

from app.database.migrations import migrate_phase19_transcript_schema
from app.routes.analyze import _build_recommendation
from app.services.nlp import (
    extract_comparable_keyword_candidates,
    tokenize_text,
)
from app.services.pipeline.core import analyze_video, normalize_asr_terms
from app.services.recommendation import build_classified_user_signal_snapshot


THAI_PHONE_TRANSCRIPT = (
    "มือถือรุ่นนี้กล้องและเซนเซอร์ถ่ายภาพได้คมชัด "
    "ใช้ชิป Snapdragon ประมวลผลเกมได้ดี "
    "แบตเตอรี่อึดใช้งานได้ทั้งวัน "
    "จอ AMOLED มีความสว่างสูง "
    "พร้อมระบบระบายความร้อนและพัดลม"
)


class Phase19ThaiKeywordExtractionTests(unittest.TestCase):
    def test_pythainlp_splits_unspaced_thai_transcript(self):
        tokens = tokenize_text(THAI_PHONE_TRANSCRIPT)

        for expected in ("กล้อง", "เซนเซอร์", "ชิป", "แบตเตอรี่", "จอ"):
            self.assertIn(expected, tokens)

    def test_explicit_synonyms_map_to_five_phone_dimensions(self):
        candidates = extract_comparable_keyword_candidates(
            THAI_PHONE_TRANSCRIPT,
            "smartphone",
        )
        by_keyword = {item["keyword"]: item for item in candidates}

        expected = {
            "camera quality",
            "chip performance",
            "battery life",
            "display quality",
            "thermal control",
        }
        self.assertTrue(expected.issubset(by_keyword))
        for keyword in expected:
            self.assertGreater(by_keyword[keyword]["frequency"], 0)
            self.assertTrue(by_keyword[keyword]["matched_terms"])

        battery = by_keyword["battery life"]
        self.assertIn("แบตเตอรี่", battery["matched_terms"])
        self.assertNotIn("แบต", battery["matched_terms"])

    def test_normalization_changes_only_reviewed_terms(self):
        transcript = (
            "คำเฉพาะผู้สร้าง แบท 6500 ชิพเดมเซตี "
            "แบตเตอร์รี่ สแนปดราก้อน อะโมเล็ด"
        )

        normalized = normalize_asr_terms(transcript, aggressive=True)

        self.assertIn("คำเฉพาะผู้สร้าง", normalized)
        self.assertIn("แบต 6500", normalized)
        self.assertIn("ชิปdimensity", normalized)
        self.assertIn("แบตเตอรี่", normalized)
        self.assertIn("snapdragon", normalized)
        self.assertIn("amoled", normalized)

    def test_content_hook_and_comparable_keywords_are_separate(self):
        snapshot = build_classified_user_signal_snapshot(
            text=THAI_PHONE_TRANSCRIPT,
            hook_text="เปิดคลิปด้วยการทดสอบกล้องและจอ AMOLED",
            taxonomy_leaf_key="phone",
            max_keywords=12,
        )

        self.assertTrue(snapshot["content_keywords"])
        self.assertTrue(snapshot["hook_terms"])
        self.assertIn("กล้อง", snapshot["content_keywords"])
        self.assertIn("ระบายความร้อน", snapshot["content_keywords"])
        self.assertIn("camera quality", snapshot["comparable_keywords"])
        self.assertIn("chip performance", snapshot["comparable_keywords"])
        self.assertIn("camera quality", snapshot["hook_comparable_keywords"])
        self.assertNotIn("battery life", snapshot["hook_comparable_keywords"])

    def test_actual_asr_variants_recover_chip_and_battery_evidence(self):
        transcript = (
            "ชิพข้างในใช้เป็นเดมเซตี 8400 อัลติเมต "
            "หน้าจอ AMOLED กล้องหลักคมชัด แบท 6500 "
            "และมีระบบระบายความร้อน"
        )
        normalized = normalize_asr_terms(transcript)
        snapshot = build_classified_user_signal_snapshot(
            text=normalized,
            hook_text=normalized,
            taxonomy_leaf_key="phone",
            max_keywords=12,
        )

        expected = {
            "camera quality",
            "chip performance",
            "battery life",
            "display quality",
            "thermal control",
        }
        self.assertTrue(expected.issubset(snapshot["comparable_keywords"]))
        status_by_name = {
            item["name"]: item["status"]
            for item in snapshot["dimension_status"]
        }
        for keyword in expected:
            self.assertEqual(status_by_name[keyword], "present")

    @patch("app.routes.analyze.build_recommendation_from_analysis_data")
    @patch("app.routes.analyze.classify_text_domain")
    def test_api_result_exposes_three_keyword_sets(
        self,
        classify_mock,
        recommendation_mock,
    ):
        classify_mock.return_value = {
            "domain": "phone",
            "taxonomy_leaf_key": "phone",
            "category_level_1": "Technology",
            "category_level_2": "Electronics",
            "category_level_3": "Phone",
            "confidence": 0.91,
            "method": "trained_tfidf_classifier",
            "is_unknown": False,
        }
        recommendation_mock.side_effect = lambda _db, **kwargs: {
            "domain": kwargs["domain"],
            "user_keywords": kwargs["user_keywords"],
            "missing_keywords": [],
            "hook_keywords": [],
            "evidence": {},
        }
        result = {
            "transcript": THAI_PHONE_TRANSCRIPT,
            "raw_transcript": THAI_PHONE_TRANSCRIPT,
            "cleaned_transcript": normalize_asr_terms(THAI_PHONE_TRANSCRIPT),
            "analysis": {
                "hook_raw_transcript": "เปิดคลิปด้วยการทดสอบกล้อง",
                "hook_cleaned_transcript": "เปิดคลิปด้วยการทดสอบกล้อง",
                "stt_meta": {"transcript_source": "speech_to_text"},
            },
        }

        recommendation, _ = _build_recommendation(
            MagicMock(),
            filename="neutral-upload-name.mp4",
            result=result,
        )

        self.assertEqual(
            set(recommendation["keyword_sets"]),
            {"content", "hook", "comparable"},
        )
        self.assertTrue(recommendation["keyword_sets"]["content"])
        self.assertTrue(recommendation["keyword_sets"]["hook"])
        self.assertIn(
            "thermal control",
            recommendation["keyword_sets"]["comparable"],
        )
        self.assertTrue(recommendation["comparable_keyword_evidence"])

    @patch("models.speech_to_text.transcribe_with_meta")
    @patch("app.services.pipeline.core.extract_audio", return_value=True)
    def test_pipeline_preserves_raw_and_cleaned_transcripts(
        self,
        _extract_audio,
        transcribe,
    ):
        raw = "กล้องดี แบตเตอร์รี่ อึด และใช้สแนปดราก้อน"
        transcribe.return_value = {
            "text": raw,
            "language": "th",
            "language_probability": 0.99,
            "segment_count": 1,
            "avg_no_speech_prob": 0.01,
            "segments": [
                {"start": 0.0, "end": 12.0, "text": raw},
            ],
        }

        result = analyze_video(
            "clip.mp4",
            display_name="neutral-name.mp4",
            hook_duration_seconds=60,
        )

        self.assertEqual(result["raw_transcript"], raw)
        self.assertEqual(result["transcript"], raw)
        self.assertIn("แบตเตอรี่", result["cleaned_transcript"])
        self.assertIn("snapdragon", result["cleaned_transcript"])
        self.assertEqual(
            result["analysis"]["stt_meta"]["transcript_normalization"],
            "explicit_terms_only",
        )

    def test_phase19_migration_adds_and_backfills_transcript_columns(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE user_contents ("
                    "content_id INTEGER PRIMARY KEY, transcript TEXT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO user_contents (content_id, transcript) "
                    "VALUES (1, 'legacy transcript')"
                )
            )

        status = migrate_phase19_transcript_schema(engine)
        columns = {
            column["name"] for column in inspect(engine).get_columns("user_contents")
        }
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT raw_transcript, cleaned_transcript "
                    "FROM user_contents WHERE content_id = 1"
                )
            ).one()

        self.assertEqual(
            set(status["added_columns"]),
            {
                "user_contents.raw_transcript",
                "user_contents.cleaned_transcript",
            },
        )
        self.assertIn("raw_transcript", columns)
        self.assertIn("cleaned_transcript", columns)
        self.assertEqual(tuple(row), ("legacy transcript", "legacy transcript"))
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
