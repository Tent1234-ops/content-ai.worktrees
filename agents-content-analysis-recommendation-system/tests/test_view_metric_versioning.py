import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, text

from app.database.migrations import migrate_view_metric_schema
from app.services.view_metrics import (
    GOOGLE_INTEREST_V1,
    YOUTUBE_PLAY_START_VIEW_V2,
    YOUTUBE_QUALIFIED_VIEW_V1,
    view_metric_version_for,
    view_metrics_are_comparable,
)


class ViewMetricVersioningTests(unittest.TestCase):
    def test_youtube_metric_switches_at_announced_cutoff(self):
        before = datetime(2026, 8, 23, 23, 59, 59, tzinfo=timezone.utc)
        after = datetime(2026, 8, 24, 0, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(
            view_metric_version_for("youtube", before),
            YOUTUBE_QUALIFIED_VIEW_V1,
        )
        self.assertEqual(
            view_metric_version_for("youtube_live", after),
            YOUTUBE_PLAY_START_VIEW_V2,
        )
        self.assertFalse(
            view_metrics_are_comparable(
                "youtube",
                YOUTUBE_QUALIFIED_VIEW_V1,
                YOUTUBE_PLAY_START_VIEW_V2,
            )
        )

    def test_migration_backfills_dataset_and_snapshot_metric_versions(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE dataset_contents ("
                    "dataset_id INTEGER PRIMARY KEY, source_platform VARCHAR(50), "
                    "statistics_captured_at DATETIME, created_at DATETIME, "
                    "taxonomy_leaf_key VARCHAR(100))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO dataset_contents VALUES "
                    "(1, 'youtube', '2026-08-23 23:00:00', "
                    "'2026-08-23 23:00:00', 'phone'), "
                    "(2, 'youtube', '2026-08-24 01:00:00', "
                    "'2026-08-24 01:00:00', 'phone'), "
                    "(3, 'google_live', '2026-08-24 01:00:00', "
                    "'2026-08-24 01:00:00', 'phone')"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE trend_snapshot_items ("
                    "item_id INTEGER PRIMARY KEY, platform VARCHAR(50), "
                    "created_at DATETIME)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO trend_snapshot_items VALUES "
                    "(1, 'youtube', '2026-08-23 23:00:00'), "
                    "(2, 'youtube', '2026-08-24 01:00:00')"
                )
            )

        result = migrate_view_metric_schema(engine)

        self.assertIn(
            "dataset_contents.view_metric_version",
            result["added_columns"],
        )
        self.assertIn(
            "view_metric_version",
            {column["name"] for column in inspect(engine).get_columns("dataset_contents")},
        )
        with engine.connect() as connection:
            dataset_versions = connection.execute(
                text(
                    "SELECT view_metric_version FROM dataset_contents "
                    "ORDER BY dataset_id"
                )
            ).scalars().all()
            snapshot_versions = connection.execute(
                text(
                    "SELECT view_metric_version FROM trend_snapshot_items "
                    "ORDER BY item_id"
                )
            ).scalars().all()

        self.assertEqual(
            dataset_versions,
            [
                YOUTUBE_QUALIFIED_VIEW_V1,
                YOUTUBE_PLAY_START_VIEW_V2,
                GOOGLE_INTEREST_V1,
            ],
        )
        self.assertEqual(
            snapshot_versions,
            [YOUTUBE_QUALIFIED_VIEW_V1, YOUTUBE_PLAY_START_VIEW_V2],
        )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
