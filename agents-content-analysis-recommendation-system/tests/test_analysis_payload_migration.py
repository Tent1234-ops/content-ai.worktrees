import json
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import Text, create_engine, select
from sqlalchemy.dialects import mysql, sqlite

from app.database.db import Base
from app.database.migrations import migrate_analysis_payload_schema
from app.database.models import AnalysisResult, Recommendation


class AnalysisPayloadMigrationTests(unittest.TestCase):
    def test_both_payload_columns_use_longtext_only_on_mysql(self):
        for column in (
            AnalysisResult.__table__.c.summary,
            Recommendation.__table__.c.recommended_keywords,
        ):
            with self.subTest(column=column.name):
                self.assertEqual(column.type.compile(dialect=mysql.dialect()), "LONGTEXT")
                self.assertEqual(column.type.compile(dialect=sqlite.dialect()), "TEXT")

    def test_large_payload_and_legacy_value_survive_sqlite_migration(self):
        engine = create_engine("sqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        payload = json.dumps({"evidence": [{"text": "reference " * 1000}] * 20})
        self.assertGreater(len(payload.encode("utf-8")), 65535)
        table = Recommendation.__table__
        with engine.begin() as connection:
            connection.execute(table.insert(), [
                {"content_id": 1, "recommended_keywords": "legacy"},
                {"content_id": 2, "recommended_keywords": payload},
            ])
        for _ in range(2):
            self.assertEqual(migrate_analysis_payload_schema(engine), {"widened_columns": []})
        with engine.connect() as connection:
            values = connection.execute(select(table.c.recommended_keywords).order_by(table.c.rec_id)).scalars().all()
        self.assertEqual(values, ["legacy", payload])

    def run_mysql_migration(self, columns):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        connection.dialect.name = "mysql"
        inspector = MagicMock()
        inspector.get_table_names.return_value = list(columns)
        inspector.get_columns.side_effect = lambda table: columns[table]
        with patch("app.database.migrations.inspect", return_value=inspector):
            result = migrate_analysis_payload_schema(engine)
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        return result, statements

    def test_mysql_widens_both_legacy_columns(self):
        result, statements = self.run_mysql_migration({
            "analysis_results": [{"name": "summary", "type": Text()}],
            "recommendations": [{"name": "recommended_keywords", "type": Text()}],
        })
        self.assertEqual(result["widened_columns"], ["analysis_results.summary", "recommendations.recommended_keywords"])
        self.assertEqual(statements, [
            "ALTER TABLE analysis_results MODIFY COLUMN summary LONGTEXT NULL",
            "ALTER TABLE recommendations MODIFY COLUMN recommended_keywords LONGTEXT NULL",
        ])

    def test_mysql_skips_columns_already_widened(self):
        result, statements = self.run_mysql_migration({
            "analysis_results": [{"name": "summary", "type": mysql.LONGTEXT()}],
            "recommendations": [{"name": "recommended_keywords", "type": mysql.LONGTEXT()}],
        })
        self.assertEqual(result, {"widened_columns": []})
        self.assertEqual(statements, [])

    def test_recommendation_migrates_without_analysis_table(self):
        result, statements = self.run_mysql_migration({
            "recommendations": [{"name": "recommended_keywords", "type": Text()}],
        })
        self.assertEqual(result["widened_columns"], ["recommendations.recommended_keywords"])
        self.assertEqual(len(statements), 1)

    def test_missing_tables_or_columns_are_not_created(self):
        for columns in ({}, {"analysis_results": [], "recommendations": []}):
            with self.subTest(columns=columns):
                result, statements = self.run_mysql_migration(columns)
                self.assertEqual(result, {"widened_columns": []})
                self.assertEqual(statements, [])


if __name__ == "__main__":
    unittest.main()
