import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import DatasetContent, SystemLog
from scripts.verify_submission_dataset import purge_demo_rows, submission_report


class SubmissionDatasetGuardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_demo_rows_make_submission_not_ready_and_can_be_purged(self):
        self.db.add(
            DatasetContent(
                title="Legacy synthetic row",
                source_platform="youtube_seed",
                dataset_source="legacy",
                dataset_version="legacy-v1",
                is_active=False,
                is_training_eligible=False,
            )
        )
        self.db.commit()

        before = submission_report(self.db)
        self.assertFalse(before["ready_for_submission"])
        self.assertEqual(before["demo_rows"], 1)

        self.assertEqual(purge_demo_rows(self.db), 1)

        after = submission_report(self.db)
        self.assertFalse(after["ready_for_submission"])
        self.assertEqual(after["demo_rows"], 0)
        self.assertEqual(after["production_transcript_rows"], 0)
        self.assertEqual(
            self.db.query(SystemLog)
            .filter(SystemLog.action == "purge_legacy_demo_dataset")
            .count(),
            1,
        )


if __name__ == "__main__":
    unittest.main()
