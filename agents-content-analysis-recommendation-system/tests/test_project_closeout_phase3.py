import json
import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user, get_current_watch_session
from app.database.db import Base, get_db
from app.database.models import Notification, User, UserTrendWatchSession
from app.routes.notifications import router as notifications_router
from app.services.admin_report import sanitize_system_log_detail


class Phase3NotificationOwnershipTests(unittest.TestCase):
    """Deterministic DB fixture; this is not live-provider evidence."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as db:
            first = User(
                username="phase3-first",
                email="phase3-first@test.invalid",
                role="user",
                password_hash="unused",
            )
            second = User(
                username="phase3-second",
                email="phase3-second@test.invalid",
                role="user",
                password_hash="unused",
            )
            db.add_all((first, second))
            db.flush()
            first_watch = UserTrendWatchSession(
                user_id=first.user_id,
                session_key="phase3-first-session",
            )
            second_watch = UserTrendWatchSession(
                user_id=second.user_id,
                session_key="phase3-second-session",
            )
            db.add_all((first_watch, second_watch))
            db.flush()
            first_notification = Notification(
                user_id=first.user_id,
                watch_session_id=first_watch.watch_session_id,
                type="new_live_trend",
                trend_key="first-trend",
                platform="youtube",
                title="Fixture trend for first user",
                category="Gaming",
                detected_at=datetime.utcnow(),
                payload=json.dumps({"ranking_scope": "youtube_category:20"}),
            )
            second_notification = Notification(
                user_id=second.user_id,
                watch_session_id=second_watch.watch_session_id,
                type="new_live_trend",
                trend_key="second-trend",
                platform="youtube",
                title="Fixture trend for second user",
                category="Music",
                detected_at=datetime.utcnow(),
                payload=json.dumps({"ranking_scope": "youtube_category:10"}),
            )
            db.add_all((first_notification, second_notification))
            db.commit()
            self.first = first
            self.second = second
            self.first_watch = first_watch
            self.second_watch = second_watch
            self.first_notification_id = first_notification.notification_id
            self.second_notification_id = second_notification.notification_id

        self.actor = self.first
        self.watch = self.first_watch
        app = FastAPI()
        app.include_router(notifications_router)

        def db_override():
            with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: self.actor
        app.dependency_overrides[get_current_watch_session] = lambda: self.watch
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def test_unread_mark_read_and_owner_scope_survive_new_db_session(self):
        response = self.client.get("/notifications/?unread_only=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(
            response.json()["items"][0]["notification_id"],
            self.first_notification_id,
        )

        response = self.client.post(
            "/notifications/mark_read",
            json={
                "ids": [self.first_notification_id, self.second_notification_id]
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["marked"], 1)

        with self.sessions() as reopened:
            self.assertTrue(
                reopened.get(Notification, self.first_notification_id).is_read
            )
            self.assertFalse(
                reopened.get(Notification, self.second_notification_id).is_read
            )

        self.actor = self.second
        self.watch = self.second_watch
        second_response = self.client.get("/notifications/")
        self.assertEqual(second_response.json()["total"], 1)
        self.assertEqual(
            second_response.json()["items"][0]["notification_id"],
            self.second_notification_id,
        )


class Phase3AdminLogSafetyTests(unittest.TestCase):
    def test_plain_log_removes_credentials_and_sql_trace(self):
        detail = (
            "provider failed api_key=top-secret session_id=browser-123 "
            "Authorization=Bearer.token\nTraceback (most recent call last):\n"
            "RuntimeError: internal\n[SQL: SELECT * FROM users]"
        )
        result = sanitize_system_log_detail(detail)
        self.assertIn("api_key=[redacted]", result)
        self.assertIn("session_id=[redacted]", result)
        self.assertIn("Authorization=[redacted]", result)
        self.assertNotIn("top-secret", result)
        self.assertNotIn("browser-123", result)
        self.assertNotIn("Traceback", result)
        self.assertNotIn("SELECT *", result)

    def test_json_log_keeps_actor_but_redacts_nested_secrets(self):
        detail = json.dumps(
            {
                "deleted_actor_user_id": 7,
                "api_key": "secret-value",
                "request": {"access_token": "token-value", "status": "failed"},
            }
        )
        result = json.loads(sanitize_system_log_detail(detail))
        self.assertEqual(result["deleted_actor_user_id"], 7)
        self.assertEqual(result["api_key"], "[redacted]")
        self.assertEqual(result["request"]["access_token"], "[redacted]")
        self.assertEqual(result["request"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
