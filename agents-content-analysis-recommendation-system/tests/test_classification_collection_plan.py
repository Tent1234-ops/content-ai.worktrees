import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import DatasetContent
from app.services.classification_collection_plan import build_collection_plan, preview_collection_channels
from app.services.dataset_contract import channel_dataset_split


def report_fixture():
    return {"ready": True,
            "by_leaf": [{"leaf_key": key, "minimum_required": 30} for key in ("phone", "camera", "laptop")],
            "phase22": {"by_leaf": [{"leaf_key": key, "sample_count": count,
                "minimum_sample_count": 80, "unique_channels": 15, "minimum_unique_channels": 10}
                for key, count in (("phone", 50), ("camera", 52), ("laptop", 52))]},
            "unknown_support": {"split_counts": {}, "channel_counts": {}}}


class ClassificationCollectionPlanTests(unittest.TestCase):
    def test_current_shape_requires_86_known_and_40_unknown_not_30_aggregated(self):
        plan = build_collection_plan(report_fixture())
        self.assertEqual([r["missing"] for r in plan["rows"]], [30, 28, 28, 10, 30])
        self.assertEqual(plan["additional_minimum"], 126)
        self.assertEqual(plan["unknown_total_minimum"], 40)
        self.assertFalse(plan["collection_ready"])

    def test_unknown_train_or_extra_validation_cannot_fill_test_gap(self):
        report = report_fixture()
        report["unknown_support"] = {"split_counts": {"train": 100, "validation": 40},
                                     "channel_counts": {"train": 15, "validation": 4}}
        plan = build_collection_plan(report)
        self.assertEqual(plan["rows"][-1]["missing"], 30)
        self.assertEqual(plan["unknown_train_reserved_count"], 100)
        self.assertFalse(plan["collection_ready"])

    def test_counts_alone_do_not_pass_channel_or_partition_requirements(self):
        report = report_fixture()
        for row in report["phase22"]["by_leaf"]:
            row["sample_count"] = 80
        report["unknown_support"] = {"split_counts": {"validation": 10, "test": 30},
                                     "channel_counts": {"validation": 3, "test": 1}}
        self.assertEqual(build_collection_plan(report)["additional_minimum"], 2)
        self.assertFalse(build_collection_plan(report)["collection_ready"])
        report["unknown_support"]["channel_counts"]["test"] = 3
        self.assertTrue(build_collection_plan(report)["collection_ready"])
        report["ready"] = False
        self.assertFalse(build_collection_plan(report)["collection_ready"])

    def test_diagnostic_plan_is_distinct_and_never_claims_activation(self):
        plan = build_collection_plan(report_fixture(), enforce_phase22_gate=False)
        self.assertEqual(plan["additional_minimum"], 20)
        self.assertEqual(plan["unknown_total_minimum"], 20)
        self.assertTrue(plan["activation_requires_evaluation"])

    def test_channel_preview_is_read_only_and_remembers_archived_rows(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        try:
            with sessionmaker(bind=engine)() as db:
                channel = "UC" + "a" * 22
                assigned, _ = channel_dataset_split(channel)
                original_split = "test" if assigned != "test" else "train"
                row = DatasetContent(title="Archived test fixture", source_channel_id=channel, data_split=original_split,
                                     deleted_at=datetime.utcnow(), is_active=False)
                db.add(row)
                db.commit()
                result = preview_collection_channels(db, [channel, channel, "UC" + "b" * 22])
                self.assertEqual(len(result["items"]), 2)
                first = result["items"][0]
                self.assertEqual(first["assigned_split"], assigned)
                self.assertEqual(first["existing_dataset_count"], 1)
                self.assertTrue(first["split_conflict"])
                self.assertFalse(first["independence_confirmed"])
                self.assertFalse(result["database_changed"])
                self.assertEqual(db.query(DatasetContent).count(), 1)
                self.assertEqual(db.get(DatasetContent, row.dataset_id).data_split, original_split)
                self.assertEqual(result, preview_collection_channels(db, [channel, channel, "UC" + "b" * 22]))
                for invalid in ([], ["@creator"], ["https://youtube.com/watch?v=abcdefghijk"], [channel] * 51):
                    with self.assertRaises(ValueError):
                        preview_collection_channels(db, invalid)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
