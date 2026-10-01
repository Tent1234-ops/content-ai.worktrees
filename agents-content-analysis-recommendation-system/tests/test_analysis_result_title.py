import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import AnalysisResult, Base, User, UserContent
from app.services.persistence import analysis_display_title, save_video_analysis_result


class AnalysisResultTitleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp.name) / 'titles.db'}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(
            username="title-owner",
            email="title-owner@example.test",
            password_hash="fixture",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def test_display_title_uses_only_sanitized_upload_filename(self):
        self.assertEqual(
            analysis_display_title(r"C:\private\Review_Phone--Final.mp4"),
            "Review Phone Final",
        )
        self.assertEqual(
            analysis_display_title("รีวิว_กล้อง\nฉบับใหม่.mov"),
            "รีวิว กล้อง ฉบับใหม่",
        )
        self.assertEqual(analysis_display_title(""), "คลิปวิดีโอ")

    def test_new_result_ignores_asr_summary_without_rewriting_old_results(self):
        historical = UserContent(
            user_id=self.user.user_id,
            title="ชื่อผลเก่าที่บันทึกไว้",
            transcript="ข้อความเดิม",
        )
        self.db.add(historical)
        self.db.commit()

        saved = save_video_analysis_result(
            self.db,
            user=self.user,
            filename="Review_Phone.mp4",
            file_path="videos/upload.mp4",
            transcript="ข้อความถอดเสียง",
            analysis_payload={"analysis": {"title": "ข้อความ ASR ที่อ่านไม่เป็นชื่อคลิป"}},
            nlp_result={"top_keywords": []},
            recommendation_payload={},
        )

        created = self.db.get(UserContent, saved["content_id"])
        snapshot = json.loads(
            self.db.get(AnalysisResult, saved["analysis_id"]).summary
        )
        self.assertEqual(saved["title"], "Review Phone")
        self.assertEqual(created.title, "Review Phone")
        self.assertEqual(
            snapshot["ai_analysis"]["analysis"]["title"],
            "ข้อความ ASR ที่อ่านไม่เป็นชื่อคลิป",
        )
        self.assertEqual(
            self.db.get(UserContent, historical.content_id).title,
            "ชื่อผลเก่าที่บันทึกไว้",
        )


if __name__ == "__main__":
    unittest.main()
