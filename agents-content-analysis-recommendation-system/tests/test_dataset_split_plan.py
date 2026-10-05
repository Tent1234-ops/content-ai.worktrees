import copy
import json
import unittest

from app.database.migrations import migrate_classification_split_strategy
from app.database.models import DatasetContent, DatasetSplitPlan, User
from app.services.dataset_contract import channel_dataset_split
from app.services.dataset_split_plan import (
    apply_scope_holdout_plan, load_split_registry, plan_digest, propose_scope_holdout_plan,
)
from app.services.classification_training import prepare_classification_dataset
from app.services.youtube_cc_dataset import list_youtube_cc_review_queue
from tests import test_classification_training as training_fixture


class DatasetSplitPlanTests(unittest.TestCase):
    def setUp(self):
        self.fixture = training_fixture.ClassificationTrainingTests()
        self.fixture.setUp()
        self.db = self.fixture.db
        self.admin = User(username="partition-admin", email="partition@example.test", password_hash="unused", role="admin")
        self.db.add(self.admin)
        for label in ("phone", "camera", "laptop"):
            for split, count in (("train", 20), ("validation", 5), ("test", 5)):
                for i in range(count):
                    original = "phone" if label == "laptop" else label
                    index = i + (1000 if label == "laptop" else 0) + {"train": 0, "validation": 100, "test": 200}[split]
                    self.fixture._add_example(original, split, index)
                    if label == "laptop":
                        self.db.query(DatasetContent).filter_by(title=f"phone review {index}", data_split=split).update(
                            {"taxonomy_leaf_key": "laptop", "category": "laptop"})
        for split, count in (("train", 35), ("validation", 5), ("test", 2)):
            for i in range(count):
                self.fixture._add_example("unknown", split, i + {"train": 0, "validation": 100, "test": 200}[split])
        self.db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def plan(self):
        return propose_scope_holdout_plan(self.db, version="test-holdout-v1")

    def test_preview_is_metadata_only_deterministic_and_preserves_old_holdouts(self):
        before = {r.dataset_id: r.data_split for r in self.db.query(DatasetContent).all()}
        plan = self.plan()
        self.assertEqual(plan["counts_after"]["unknown"], {"train": 2, "validation": 10, "test": 30})
        self.assertFalse(plan["predictions_used"])
        self.assertFalse(plan["fresh_external_test"])
        self.assertEqual(plan, self.plan())
        self.assertTrue(all(r["data_split"] == "train" for r in plan["changes"]))
        self.assertEqual(before, {r.dataset_id: r.data_split for r in self.db.query(DatasetContent).all()})
        self.assertEqual(self.db.query(DatasetSplitPlan).count(), 0)

    def test_apply_registry_survives_migration_and_covers_archived_channel_rows(self):
        preview = self.plan()
        channel = next(iter(preview["overrides"]))
        _, group = channel_dataset_split(channel)
        self.db.add(DatasetContent(title="Archived channel record", source_channel_id=channel,
                                  creator_group_key=group, data_split="train", is_active=False,
                                  dataset_source="youtube_cc"))
        self.db.commit()
        plan = self.plan()
        report = apply_scope_holdout_plan(self.db, plan, expected_sha256=plan_digest(plan), user_id=self.admin.user_id)
        admin_id = self.admin.user_id
        self.assertTrue(report["partition_integrity_passed"])
        self.assertEqual(report["unknown_support"]["split_counts"], plan["counts_after"]["unknown"])
        self.assertEqual(load_split_registry(self.db)["overrides"], plan["overrides"])
        self.db.close()
        migrate_classification_split_strategy(self.fixture.engine)
        self.db.expire_all()
        after = prepare_classification_dataset(self.db, required_leaf_keys=("phone", "camera", "laptop")).report
        self.assertEqual(report["dataset_fingerprint"], after["dataset_fingerprint"])
        self.assertTrue(after["ready"])
        archived = self.db.query(DatasetContent).filter_by(title="Archived channel record").one()
        self.assertEqual(archived.data_split, plan["overrides"][channel])
        with self.assertRaises(ValueError):
            apply_scope_holdout_plan(self.db, plan, expected_sha256=plan_digest(plan), user_id=admin_id)
        self.db.rollback()

    def test_changed_inventory_and_tampered_plan_are_rejected(self):
        plan = self.plan()
        altered = copy.deepcopy(plan)
        altered["overrides"][next(iter(altered["overrides"]))] = "train"
        with self.assertRaises(ValueError):
            apply_scope_holdout_plan(self.db, altered, expected_sha256=plan_digest(plan), user_id=self.admin.user_id)
        self.db.add(DatasetContent(title="New record"))
        self.db.commit()
        with self.assertRaises(ValueError):
            apply_scope_holdout_plan(self.db, plan, expected_sha256=plan_digest(plan), user_id=self.admin.user_id)
        self.assertEqual(self.db.query(DatasetSplitPlan).count(), 0)

    def test_known_training_rows_move_with_an_unknown_holdout_channel(self):
        unknown = self.db.query(DatasetContent).filter_by(taxonomy_leaf_key="unknown", data_split="train").limit(3).all()
        channel, group = unknown[0].source_channel_id, unknown[0].creator_group_key
        known = self.db.query(DatasetContent).filter_by(taxonomy_leaf_key="phone", data_split="train").first()
        for row in [*unknown, known]:
            row.source_channel_id, row.creator_group_key = channel, group
        self.db.commit()
        plan = self.plan()
        # Only two Unknown rows can remain reserved; this three-row channel must move as a whole.
        self.assertIn(channel, plan["overrides"])
        apply_scope_holdout_plan(self.db, plan, expected_sha256=plan_digest(plan), user_id=self.admin.user_id)
        self.assertEqual(known.data_split, plan["overrides"][channel])
        self.assertNotEqual(known.data_split, "train")
        self.assertEqual({row.data_split for row in unknown}, {known.data_split})

    def test_only_admin_can_apply_and_corrupt_registry_fails_closed(self):
        plan = self.plan()
        self.admin.role = "user"
        self.db.commit()
        with self.assertRaises(ValueError):
            apply_scope_holdout_plan(self.db, plan, expected_sha256=plan_digest(plan), user_id=self.admin.user_id)
        self.db.add(DatasetSplitPlan(plan_version=plan["version"], plan_sha256="0" * 64,
                                    payload_json=json.dumps(plan)))
        self.db.commit()
        with self.assertRaises(ValueError):
            load_split_registry(self.db)

    def test_review_unknown_total_alone_is_not_ready(self):
        result = list_youtube_cc_review_queue(self.db, collection_run_id=-1)
        unknown = next(r for r in result["taxonomy"] if r["leaf_key"] == "unknown")
        self.assertEqual(unknown["verified_sample_count"], 42)
        self.assertEqual(unknown["split_counts"], {"train": 35, "validation": 5, "test": 2})
        self.assertFalse(unknown["ready"])
        self.assertEqual(unknown["minimum_sample_count"], 40)


if __name__ == "__main__":
    unittest.main()
