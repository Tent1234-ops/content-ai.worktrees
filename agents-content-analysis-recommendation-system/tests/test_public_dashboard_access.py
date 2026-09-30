import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.db import get_db
from app.routes import analyze, contents, dashboard, follows, notifications


class PublicDashboardAccessTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        app = FastAPI()
        for module in [dashboard, analyze, contents, follows, notifications]:
            app.include_router(module.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_guest_can_read_shared_snapshot_and_category_only(self):
        for path, reader, expected in [
            ("/dashboard/public/trends?region=th", "load_public_trend_snapshot",
             {"region": "TH", "limit": 50}),
            ("/dashboard/public/youtube/categories?video_category_id=24",
             "load_youtube_category_snapshot",
             {"region": "TH", "category_id": "24", "limit": 50}),
        ]:
            with self.subTest(path=path), patch(
                f"app.routes.dashboard.{reader}", return_value={"items": []}
            ) as load:
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                load.assert_called_once_with(self.db, **expected)

    def test_private_reads_and_writes_still_require_login(self):
        for method, path in [
            ("GET", "/dashboard/summary"),
            ("GET", "/dashboard/overview"),
            ("GET", "/dashboard/live-trends/snapshot"),
            ("GET", "/contents/my"),
            ("GET", "/contents/1"),
            ("GET", "/follows/topics"),
            ("GET", "/notifications/"),
            ("POST", "/follows/topic"),
            ("POST", "/analyze"),
            ("POST", "/analyze/save"),
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path).status_code, 401)
        self.db.query.assert_not_called()

    def test_public_limit_cannot_exceed_fifty(self):
        with patch("app.routes.dashboard.load_public_trend_snapshot") as load:
            self.assertEqual(self.client.get("/dashboard/public/trends?trend_limit=51").status_code, 422)
            load.assert_not_called()
