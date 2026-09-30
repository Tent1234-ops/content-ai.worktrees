import json
import time
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.migrations import migrate_trend_scope_schema
from app.core.config import settings
from app.core.security import decode_access_token, hash_password
from app.database.models import (
    Notification,
    TrendSnapshotItem,
    TrendSnapshotRun,
    User,
    UserTrendWatchSession,
)
from app.routes.auth import login
from app.schemas.trends import GoogleTrendItem, YouTubeTrendItem
from app.schemas.auth import LoginRequest
from app.schemas.notifications import NotificationItem
from app.routes.dashboard import (
    dashboard_live_trends_snapshot,
    dashboard_youtube_category_snapshots,
)
from app.services.dashboard import build_dashboard_summary
from app.services.live_trend_notifications import compare_live_trend_snapshot, load_public_trend_snapshot
from app.services.live_trend_snapshots import (
    GLOBAL_SNAPSHOT_KIND,
    YOUTUBE_CATEGORY_SNAPSHOT_KIND,
    load_latest_live_snapshot,
    load_trend_item_detail,
    load_youtube_category_snapshot,
    normalize_live_item,
    refresh_global_live_trends,
    refresh_youtube_category_live_trends,
)
from app.services.trend_watch_sessions import start_trend_watch_session
from app.services.simple_cache import clear as clear_simple_cache
from app.services.trends import _live_youtube_categories
from app.services.view_metrics import (
    YOUTUBE_PLAY_START_VIEW_V2,
    YOUTUBE_QUALIFIED_VIEW_V1,
)


class LiveTrendSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(
            username="snapshot-test",
            email="snapshot@example.com",
            password_hash=hash_password("test-password"),
            role="user",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    @staticmethod
    def _youtube(_region, _limit):
        return "live", [
            YouTubeTrendItem(
                title="YouTube trend A",
                channel_title="Channel",
                description="Creator supplied description",
                category="Technology",
                video_url="https://youtube.example/a",
                thumbnail_url="https://images.example/a.jpg",
                views=1000,
                likes=100,
                comments=10,
                trend_score=730,
                duration_seconds=125,
                source="youtube_live",
            )
        ]

    @staticmethod
    def _google(_region, _limit):
        return "live", [
            GoogleTrendItem(
                title="Google trend B",
                query="Google trend B",
                category="Search",
                video_url="https://google.example/b",
                views=0,
                likes=0,
                comments=0,
                trend_score=500,
                search_volume=500,
                source="google_trends_live",
                traffic_text="500+",
            )
        ]

    @staticmethod
    def _failed_tiktok(_region, _limit):
        raise TimeoutError("simulated TikTok failure")

    @staticmethod
    def _empty_provider(_region, _limit):
        return "live", []

    @staticmethod
    def _youtube_titles(*titles):
        def fetcher(_region, _limit):
            return "live", [
                YouTubeTrendItem(
                    title=title,
                    channel_title="Channel",
                    category="Technology",
                    video_url=f"https://youtube.example/{title.lower()}",
                    views=1000,
                    likes=100,
                    comments=10,
                    trend_score=730,
                    source="youtube_live",
                )
                for title in titles
            ]

        return fetcher

    @staticmethod
    def _youtube_metric(views, likes, comments):
        def fetcher(_region, _limit):
            return "live", [
                YouTubeTrendItem(
                    title="Keyboard momentum",
                    channel_title="Channel",
                    category="Technology",
                    video_url="https://youtube.example/keyboard-momentum",
                    views=views,
                    likes=likes,
                    comments=comments,
                    trend_score=730,
                    source="youtube_live",
                )
            ]

        return fetcher

    @staticmethod
    def _youtube_versioned_metric(views, version):
        def fetcher(_region, _limit):
            return "live", [
                {
                    "title": "Versioned momentum",
                    "category": "Technology",
                    "video_url": "https://youtube.example/versioned-momentum",
                    "views": views,
                    "likes": 100,
                    "comments": 10,
                    "trend_score": 730,
                    "source": "youtube_live",
                    "view_metric_version": version,
                }
            ]

        return fetcher

    @staticmethod
    def _google_ranked(*titles):
        def fetcher(_region, _limit):
            return "live", [
                GoogleTrendItem(
                    title=title,
                    query=title,
                    category="TH",
                    video_url=f"https://google.example/{title.lower()}",
                    trend_score=float(50_000 - (index * 10_000)),
                    source="google_trends_live",
                )
                for index, title in enumerate(titles)
            ]

        return fetcher

    @staticmethod
    def _youtube_categories(category_titles):
        def fetcher(_region, limit, category_id):
            titles = category_titles.get(category_id, [])[:limit]
            return "live", [
                YouTubeTrendItem(
                    title=title,
                    channel_title=f"Channel {category_id}",
                    category=category_id,
                    video_url=f"https://youtube.example/{title.lower()}",
                    views=1000 - index,
                    likes=100,
                    comments=10,
                    trend_score=730 - index,
                    source="youtube_live",
                )
                for index, title in enumerate(titles)
            ]

        return fetcher

    def _start_watch_session(self):
        return start_trend_watch_session(self.db, user=self.user, region="TH")

    def _backdate_latest_run(self, *, minutes=6):
        run = (
            self.db.query(TrendSnapshotRun)
            .order_by(TrendSnapshotRun.run_id.desc())
            .first()
        )
        run.started_at -= timedelta(minutes=minutes)
        if run.completed_at is not None:
            run.completed_at -= timedelta(minutes=minutes)
        self.db.commit()

    def test_partial_run_keeps_successful_platforms_and_reads_quickly(self):
        result = refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube,
                "google": self._google,
                "tiktok": self._failed_tiktok,
            },
            db=self.db,
        )

        started = time.perf_counter()
        snapshot = load_latest_live_snapshot(self.db, region="TH", limit=50)
        elapsed = time.perf_counter() - started

        self.assertEqual(result["status"], "partial")
        self.assertEqual(snapshot["platforms"]["youtube"]["total"], 1)
        self.assertEqual(snapshot["platforms"]["google"]["total"], 1)
        self.assertEqual(
            snapshot["platforms"]["google"]["items"][0]["search_volume"],
            500,
        )
        self.assertEqual(snapshot["platforms"]["tiktok"]["mode"], "live_error")
        self.assertTrue(result["completed_at"].endswith("Z"))
        self.assertTrue(snapshot["generated_at"].endswith("Z"))
        self.assertLess(elapsed, 1.0)

    def test_top_trend_detail_preserves_metadata_and_snapshot_history(self):
        fetchers = {
            "youtube": self._youtube,
            "google": self._empty_provider,
            "tiktok": self._empty_provider,
        }
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers=fetchers,
            db=self.db,
        )
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers=fetchers,
            db=self.db,
        )
        snapshot = load_latest_live_snapshot(self.db, region="TH", limit=50)
        item = snapshot["platforms"]["youtube"]["items"][0]

        detail = load_trend_item_detail(
            self.db,
            region="TH",
            trend_key=item["key"],
            platform="youtube",
            ranking_scope="global",
            category_id=None,
        )

        self.assertEqual(item["channel_title"], "Channel")
        self.assertEqual(item["duration_seconds"], 125)
        self.assertEqual(detail["item"]["description"], "Creator supplied description")
        self.assertEqual(detail["item"]["thumbnail_url"], "https://images.example/a.jpg")
        self.assertEqual(len(detail["history"]), 2)
        self.assertTrue(detail["captured_at"].endswith("Z"))
        self.assertTrue(detail["first_seen_in_history_at"].endswith("Z"))

    def test_metric_availability_is_preserved_for_hidden_counts(self):
        item = normalize_live_item(
            "youtube",
            YouTubeTrendItem(
                title="Hidden engagement",
                channel_title="Channel",
                video_url="https://youtube.example/hidden",
                views=500,
                likes=0,
                comments=0,
                likes_available=False,
                comments_available=False,
            ),
        )

        self.assertTrue(item["views_available"])
        self.assertFalse(item["likes_available"])
        self.assertFalse(item["comments_available"])

    def test_failed_latest_refresh_keeps_last_successful_platform_data(self):
        successful = refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube,
                "google": self._google,
                "tiktok": self._empty_provider,
            },
            db=self.db,
        )
        failed = refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._failed_tiktok,
                "google": self._failed_tiktok,
                "tiktok": self._failed_tiktok,
            },
            db=self.db,
        )

        snapshot = load_latest_live_snapshot(self.db, region="TH", limit=50)

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(snapshot["run_id"], successful["run_id"])
        self.assertEqual(snapshot["latest_attempt_run_id"], failed["run_id"])
        self.assertEqual(snapshot["platforms"]["youtube"]["total"], 1)
        self.assertEqual(
            snapshot["platforms"]["youtube"]["items"][0]["title"],
            "YouTube trend A",
        )
        self.assertEqual(snapshot["platforms"]["youtube"]["mode"], "live_stale")
        self.assertTrue(snapshot["platforms"]["youtube"]["is_stale"])
        self.assertEqual(
            snapshot["platforms"]["youtube"]["data_run_id"],
            successful["run_id"],
        )

    def test_user_snapshot_uses_cached_run_as_baseline(self):
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube,
                "google": self._google,
                "tiktok": self._failed_tiktok,
            },
            db=self.db,
        )
        watch_session = self._start_watch_session()

        result = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )

        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["platforms"]["youtube"]["total"], 1)
        self.assertEqual(result["platforms"]["google"]["total"], 1)
        self.assertEqual(result["platforms"]["tiktok"]["mode"], "live_error")

    def test_dashboard_snapshot_endpoint_reads_cached_data_under_one_second(self):
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube,
                "google": self._google,
                "tiktok": self._failed_tiktok,
            },
            db=self.db,
        )
        watch_session = self._start_watch_session()

        started = time.perf_counter()
        result = dashboard_live_trends_snapshot(
            region="TH",
            trend_limit=50,
            current_user=self.user,
            watch_session=watch_session,
            db=self.db,
        )
        elapsed = time.perf_counter() - started

        self.assertEqual(result["platforms"]["youtube"]["total"], 1)
        self.assertEqual(result["platforms"]["google"]["total"], 1)
        self.assertEqual(result["platforms"]["tiktok"]["mode"], "live_error")
        self.assertLess(elapsed, 1.0)

    def test_dashboard_summary_live_mode_never_calls_external_providers(self):
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube,
                "google": self._google,
                "tiktok": self._failed_tiktok,
            },
            db=self.db,
        )

        with (
            patch("app.services.dashboard.get_youtube_trending", side_effect=AssertionError("network call")),
            patch("app.services.dashboard.get_google_trending", side_effect=AssertionError("network call")),
            patch("app.services.dashboard.get_tiktok_trending", side_effect=AssertionError("network call")),
        ):
            started = time.perf_counter()
            result = build_dashboard_summary(
                db=self.db,
                current_user=self.user,
                region="TH",
                trend_mode="live",
                trend_limit=50,
            )
            elapsed = time.perf_counter() - started

        self.assertEqual(result["youtube_trends"]["total"], 1)
        self.assertEqual(result["google_trends"]["total"], 1)
        self.assertEqual(result["tiktok_trends"]["mode"], "live_error")
        self.assertEqual(result["top_trends"], [])
        self.assertEqual(
            result["youtube_trends"]["items"][0]["title"],
            "YouTube trend A",
        )
        self.assertEqual(
            result["google_trends"]["items"][0]["title"],
            "Google trend B",
        )
        self.assertLess(elapsed, 1.0)

    def test_login_uses_current_snapshot_as_baseline(self):
        snapshot = refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube,
                "google": self._google,
                "tiktok": self._failed_tiktok,
            },
            db=self.db,
        )

        response = login(
            LoginRequest(email=self.user.email, password="test-password"),
            db=self.db,
        )
        watch_session = (
            self.db.query(UserTrendWatchSession)
            .filter(UserTrendWatchSession.session_key == response.session_key)
            .one()
        )

        self.assertEqual(watch_session.baseline_run_id, snapshot["run_id"])
        self.assertEqual(watch_session.last_seen_run_id, snapshot["run_id"])
        self.assertEqual(decode_access_token(response.access_token)["sid"], response.session_key)
        self.assertEqual(self.db.query(Notification).count(), 0)

    def test_new_trend_is_notified_once_per_login_session(self):
        base_fetchers = {
            "youtube": self._youtube_titles("A", "B", "C"),
            "google": self._empty_provider,
            "tiktok": self._empty_provider,
        }
        refresh_global_live_trends(region="TH", limit=50, fetchers=base_fetchers, db=self.db)
        watch_session = self._start_watch_session()

        baseline = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )
        self.assertEqual(baseline["new_count"], 0)

        refresh_global_live_trends(region="TH", limit=50, fetchers=base_fetchers, db=self.db)
        unchanged = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )
        self.assertEqual(unchanged["new_count"], 0)

        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                **base_fetchers,
                "youtube": self._youtube_titles("A", "B", "C", "D"),
            },
            db=self.db,
        )
        changed = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )
        self.assertEqual(changed["new_count"], 1)
        self.assertEqual(changed["new_notifications"][0].title, "D")

        duplicate_poll = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )
        notifications = self.db.query(Notification).all()
        self.assertEqual(duplicate_poll["new_count"], 0)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].type, "new_live_trend")
        self.assertNotIn("Analysis complete", notifications[0].title)
        serialized = NotificationItem.model_validate(notifications[0]).model_dump(
            mode="json"
        )
        self.assertTrue(serialized["detected_at"].endswith("Z"))
        self.assertTrue(serialized["created_at"].endswith("Z"))

    def test_youtube_momentum_uses_stable_window_and_qualitative_label(self):
        empty = self._empty_provider
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube_metric(1_000, 100, 10),
                "google": empty,
                "tiktok": empty,
            },
            db=self.db,
        )
        self._backdate_latest_run()
        watch_session = self._start_watch_session()
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube_metric(1_600, 160, 16),
                "google": empty,
                "tiktok": empty,
            },
            db=self.db,
        )

        result = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )
        item = result["platforms"]["youtube"]["items"][0]

        self.assertEqual(item["change_kind"], "velocity_up")
        self.assertEqual(item["change_label"], "Gaining fastest")
        self.assertGreater(item["engagement_rate_per_minute"], 0)
        self.assertGreaterEqual(item["comparison_window_seconds"], 300)
        self.assertTrue(item["is_meaningful_rising"])
        self.assertNotIn("/min", item["change_label"])

    def test_youtube_momentum_ignores_single_refresh_noise(self):
        empty = self._empty_provider
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube_metric(1_000, 100, 10),
                "google": empty,
                "tiktok": empty,
            },
            db=self.db,
        )
        watch_session = self._start_watch_session()
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube_metric(1_001, 101, 10),
                "google": empty,
                "tiktok": empty,
            },
            db=self.db,
        )

        result = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )
        item = result["platforms"]["youtube"]["items"][0]

        self.assertEqual(item["change_kind"], "baseline")
        self.assertEqual(item["change_label"], "Baseline")
        self.assertEqual(item["engagement_rate_per_minute"], 0)
        self.assertFalse(item["is_meaningful_rising"])

    def test_youtube_momentum_resets_when_view_metric_version_changes(self):
        empty = self._empty_provider
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube_versioned_metric(
                    1_000,
                    YOUTUBE_QUALIFIED_VIEW_V1,
                ),
                "google": empty,
                "tiktok": empty,
            },
            db=self.db,
        )
        self._backdate_latest_run()
        watch_session = self._start_watch_session()
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube_versioned_metric(
                    50_000,
                    YOUTUBE_PLAY_START_VIEW_V2,
                ),
                "google": empty,
                "tiktok": empty,
            },
            db=self.db,
        )

        result = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )
        item = result["platforms"]["youtube"]["items"][0]

        self.assertEqual(item["change_kind"], "metric_baseline")
        self.assertEqual(item["engagement_delta"], 0)
        self.assertEqual(item["engagement_rate_per_minute"], 0)
        self.assertFalse(item["has_previous_snapshot"])
        self.assertTrue(item["metric_version_changed"])

    def test_public_snapshot_compares_rankings_without_user_writes(self):
        for titles in [("A", "B"), ("B", "A")]:
            refresh_global_live_trends(
                region="TH", limit=50, db=self.db,
                fetchers={"youtube": self._youtube,
                          "google": self._google_ranked(*titles),
                          "tiktok": self._empty_provider},
            )
            if titles[0] == "A":
                self._backdate_latest_run()

        with patch.object(self.db, "commit", side_effect=AssertionError("Public read must not write")):
            result = load_public_trend_snapshot(self.db, region="TH", limit=50)
            repeated = load_public_trend_snapshot(self.db, region="TH", limit=50)
        self.assertEqual(result, repeated)
        self.assertEqual(result["platforms"]["google"]["items"][0]["rank_change"], 1)
        video = result["platforms"]["youtube"]["items"][0]
        self.assertEqual(video["channel_title"], "Channel")
        self.assertEqual(video["duration_seconds"], 125)
        self.assertEqual(video["views"], 1000)
        self.assertEqual(self.db.query(UserTrendWatchSession).count(), 0)
        self.assertEqual(self.db.query(Notification).count(), 0)
        self.assertNotIn("recent_analyses", result)

    def test_google_momentum_uses_rank_movement(self):
        empty = self._empty_provider
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": empty,
                "google": self._google_ranked("A", "B", "C"),
                "tiktok": empty,
            },
            db=self.db,
        )
        self._backdate_latest_run()
        watch_session = self._start_watch_session()
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": empty,
                "google": self._google_ranked("C", "A", "B"),
                "tiktok": empty,
            },
            db=self.db,
        )

        result = compare_live_trend_snapshot(
            db=self.db,
            user=self.user,
            watch_session=watch_session,
            region="TH",
            limit=50,
        )
        item = result["platforms"]["google"]["items"][0]

        self.assertEqual(item["title"], "C")
        self.assertEqual(item["rank_change"], 2)
        self.assertEqual(item["change_kind"], "rank_up")
        self.assertEqual(item["change_label"], "Up 2 ranks")
        self.assertTrue(item["is_meaningful_rising"])

    def test_google_region_is_not_exposed_as_a_content_category(self):
        normalized = normalize_live_item(
            "google",
            GoogleTrendItem(
                title="Thai search topic",
                query="Thai search topic",
                category="TH",
                video_url="https://google.example/topic",
                trend_score=20_000,
                source="google_trends_live",
            ),
        )

        self.assertEqual(normalized["category"], "Search Trends")
        self.assertEqual(normalized["views"], 0)

    def test_google_traffic_text_is_normalized_as_approximate_search_volume(self):
        normalized = normalize_live_item(
            "google",
            GoogleTrendItem(
                title="Thai search topic",
                query="Thai search topic",
                category="TH",
                video_url="https://google.example/topic",
                trend_score=20_000,
                traffic_text="20K+",
                source="google_trends_live",
            ),
        )

        self.assertEqual(normalized["search_volume"], 20_000)

    def test_trend_schema_backfills_only_legacy_google_scores_above_rank_range(self):
        run = TrendSnapshotRun(
            region="TH",
            snapshot_kind=GLOBAL_SNAPSHOT_KIND,
            status="completed",
            provider_status="{}",
        )
        self.db.add(run)
        self.db.flush()
        traffic_row = TrendSnapshotItem(
            run_id=run.run_id,
            platform="google",
            ranking_scope="global",
            provider_rank=1,
            trend_key="a" * 40,
            title="Traffic-backed trend",
            category="Search Trends",
            source_platform="google_trends_live",
            trend_score=2_000,
            engagement_signal=2_000,
            search_volume=None,
        )
        rank_fallback_row = TrendSnapshotItem(
            run_id=run.run_id,
            platform="google",
            ranking_scope="global",
            provider_rank=2,
            trend_key="b" * 40,
            title="Rank-only trend",
            category="Search Trends",
            source_platform="google_trends_live",
            trend_score=50,
            engagement_signal=50,
            search_volume=None,
        )
        self.db.add_all((traffic_row, rank_fallback_row))
        self.db.commit()

        result = migrate_trend_scope_schema(self.engine)
        self.db.expire_all()

        self.assertGreaterEqual(result["search_volume_backfilled_rows"], 1)
        self.assertEqual(self.db.get(TrendSnapshotItem, traffic_row.item_id).search_volume, 2_000)
        self.assertIsNone(
            self.db.get(TrendSnapshotItem, rank_fallback_row.item_id).search_volume
        )

    def test_youtube_category_snapshot_keeps_50_items_separate_from_global(self):
        refresh_global_live_trends(
            region="TH",
            limit=50,
            fetchers={
                "youtube": self._youtube_titles("Global A", "Global B"),
                "google": self._empty_provider,
                "tiktok": self._empty_provider,
            },
            db=self.db,
        )
        entertainment = [f"Entertainment {index}" for index in range(1, 51)]
        gaming = [f"Gaming {index}" for index in range(1, 51)]
        result = refresh_youtube_category_live_trends(
            region="TH",
            limit=50,
            category_ids=("24", "20"),
            category_titles={"24": "Entertainment", "20": "Gaming"},
            fetcher=self._youtube_categories({"24": entertainment, "20": gaming}),
            db=self.db,
        )

        snapshot = load_youtube_category_snapshot(
            self.db,
            region="TH",
            category_id="24",
            limit=50,
        )
        selected = snapshot["selected_category"]
        global_snapshot = load_latest_live_snapshot(self.db, region="TH", limit=50)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["total_items"], 100)
        self.assertEqual(selected["ranking_scope"], "category:24")
        self.assertEqual(len(selected["items"]), 50)
        self.assertEqual(selected["items"][0]["rank"], 1)
        self.assertEqual(selected["items"][-1]["rank"], 50)
        self.assertEqual(global_snapshot["platforms"]["youtube"]["total"], 2)
        self.assertEqual(
            self.db.query(TrendSnapshotRun)
            .filter(TrendSnapshotRun.snapshot_kind == GLOBAL_SNAPSHOT_KIND)
            .count(),
            1,
        )
        self.assertEqual(
            self.db.query(TrendSnapshotRun)
            .filter(
                TrendSnapshotRun.snapshot_kind == YOUTUBE_CATEGORY_SNAPSHOT_KIND
            )
            .count(),
            1,
        )

    def test_youtube_category_movement_compares_only_the_same_scope(self):
        first = {
            "24": ["A", "B", "C"],
            "20": ["C", "A", "B"],
        }
        refresh_youtube_category_live_trends(
            region="TH",
            limit=50,
            category_ids=("24", "20"),
            category_titles={"24": "Entertainment", "20": "Gaming"},
            fetcher=self._youtube_categories(first),
            db=self.db,
        )
        second = {
            "24": ["C", "A", "B"],
            "20": ["C", "A", "B"],
        }
        refresh_youtube_category_live_trends(
            region="TH",
            limit=50,
            category_ids=("24", "20"),
            category_titles={"24": "Entertainment", "20": "Gaming"},
            fetcher=self._youtube_categories(second),
            db=self.db,
        )

        snapshot = load_youtube_category_snapshot(
            self.db,
            region="TH",
            category_id="24",
            limit=50,
        )
        first_item = snapshot["selected_category"]["items"][0]

        self.assertEqual(first_item["title"], "C")
        self.assertEqual(first_item["rank"], 1)
        self.assertEqual(first_item["rank_change"], 2)
        self.assertEqual(first_item["change_kind"], "rank_up")
        self.assertEqual(first_item["ranking_scope"], "category:24")
        self.assertEqual(
            self.db.query(TrendSnapshotItem)
            .filter(TrendSnapshotItem.ranking_scope == "category:24")
            .count(),
            6,
        )

    def test_youtube_category_metadata_is_cached_between_chart_requests(self):
        payload = json.dumps(
            {
                "items": [
                    {
                        "id": "24",
                        "snippet": {
                            "title": "Entertainment",
                            "assignable": True,
                        },
                    }
                ]
            }
        ).encode("utf-8")
        response = MagicMock()
        response.__enter__.return_value.read.return_value = payload
        clear_simple_cache()
        try:
            with (
                patch.object(settings, "youtube_api_key", "test-key"),
                patch("app.services.trends.urlopen", return_value=response) as request,
            ):
                first = _live_youtube_categories("TH")
                second = _live_youtube_categories("TH")
        finally:
            clear_simple_cache()

        self.assertEqual(request.call_count, 1)
        self.assertEqual(first[0].category_id, "24")
        self.assertEqual(second[0].title, "Entertainment")

    def test_youtube_category_dashboard_endpoint_reads_database_only(self):
        refresh_youtube_category_live_trends(
            region="TH",
            limit=50,
            category_ids=("24",),
            category_titles={"24": "Entertainment"},
            fetcher=self._youtube_categories({"24": ["A", "B"]}),
            db=self.db,
        )

        with (
            patch(
                "app.services.live_trend_snapshots.get_youtube_trending",
                side_effect=AssertionError("network call"),
            ),
            patch(
                "app.services.live_trend_snapshots.get_youtube_categories",
                side_effect=AssertionError("network call"),
            ),
        ):
            result = dashboard_youtube_category_snapshots(
                region="TH",
                video_category_id="24",
                trend_limit=50,
                _current_user=self.user,
                db=self.db,
            )

        self.assertEqual(result["selected_category"]["total"], 2)
        self.assertEqual(result["selected_category"]["items"][0]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
