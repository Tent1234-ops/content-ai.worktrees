import unittest

from sqlalchemy import create_engine, inspect, text

from app.database.db import Base
from app.database.migrations import archive_phase10_notification_tables
import app.database.models  # noqa: F401


class Phase11NotificationMigrationTests(unittest.TestCase):
    def test_legacy_tables_are_archived_and_phase11_schema_is_created(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE notifications (
                        notification_id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        dataset_id INTEGER,
                        trend_score FLOAT,
                        delivered_via_ws BOOLEAN
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE user_trend_snapshots (
                        snapshot_id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL
                    )
                    """
                )
            )

        archived = archive_phase10_notification_tables(engine)
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        columns = {
            column["name"] for column in inspector.get_columns("notifications")
        }

        self.assertEqual(archived["notifications"], "notifications_legacy_phase10")
        self.assertEqual(
            archived["user_trend_snapshots"],
            "user_trend_snapshots_legacy_phase10",
        )
        self.assertIn("notifications_legacy_phase10", tables)
        self.assertIn("user_trend_snapshots_legacy_phase10", tables)
        self.assertIn("user_trend_watch_sessions", tables)
        self.assertTrue(
            {
                "watch_session_id",
                "trend_key",
                "platform",
                "title",
                "category",
                "detected_at",
                "payload",
                "is_read",
            }.issubset(columns)
        )
        self.assertTrue(
            {"dataset_id", "trend_score", "delivered_via_ws"}.isdisjoint(columns)
        )
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
