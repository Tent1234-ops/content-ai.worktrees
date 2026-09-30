import unittest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.db import Base
from app.database.models import TrendHistoryAttempt
from app.services.source_health import source_health


class SourceHealthTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.now = datetime(2026, 9, 26, 8)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add(self, status, age, *, platform='youtube', scope='global', region='TH', count=50):
        self.db.add(TrendHistoryAttempt(run_id=age + 1, region=region, platform=platform,
            ranking_scope=scope, observed_at=self.now - timedelta(minutes=age),
            status=status, sample_count=count if status == 'observed' else None))
        self.db.commit()

    def status(self):
        return {(r['platform'], r['scope']): r for r in source_health(self.db, now=self.now)['items']}

    def test_failure_does_not_hide_last_success_or_borrow_other_scopes(self):
        self.add('observed', 60)
        self.add('failed', 30)
        self.add('observed', 1, scope='category:20')
        self.add('observed', 0, region='US')
        rows = self.status()
        self.assertEqual(rows['youtube', 'global']['status'], 'failed')
        self.assertEqual(rows['youtube', 'global']['failed_24h'], 1)
        self.assertIsNotNone(rows['youtube', 'global']['last_success_at'])
        self.assertIsNone(rows['youtube', 'global']['sample_count'])
        self.assertEqual(rows['google', 'global']['status'], 'no_data')

    def test_empty_stale_and_mock_are_not_healthy_live_data(self):
        self.add('observed', 1500)
        self.add('observed', 1, platform='google', count=0)
        self.assertEqual(self.status()['youtube', 'global']['status'], 'stale')
        self.assertEqual(self.status()['google', 'global']['status'], 'empty')
        self.add('excluded_mock', 0)
        self.assertEqual(self.status()['youtube', 'global']['status'], 'excluded_mock')
