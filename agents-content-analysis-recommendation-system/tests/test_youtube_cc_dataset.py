import csv
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.migrations import migrate_youtube_cc_dataset_schema
from app.database.models import (
    AnalysisResult,
    DatasetCollectionRun,
    DatasetContent,
    DatasetReviewEvent,
    UserContent,
)
from app.services.dataset_eligibility import (
    out_of_scope_evaluation_query,
    production_transcript_query,
    validate_training_eligibility_values,
)
from app.services.dataset_contract import channel_dataset_split
from app.services.taxonomy import (
    TAXONOMY_VERSION,
    UNKNOWN_LEAF_KEY,
    collection_queries_for_leaf,
    sync_taxonomy_registry,
)
from app.services.youtube_cc_dataset import (
    CLASSIFICATION_DIVERSE_STRATEGY,
    RECOMMENDATION_HIGH_PERFORMANCE_STRATEGY,
    REVIEW_FIELDS,
    YouTubeCollectionResumeCooldownError,
    YouTubeCCDatasetError,
    YouTubeQuotaExceededError,
    YouTubeTranscriptProviderBlockedError,
    _review_rows,
    _youtube_get,
    collect_youtube_cc_candidates,
    create_notebooklm_transcript_candidate,
    import_reviewed_youtube_cc_dataset,
    list_youtube_cc_review_queue,
    parse_iso8601_duration,
    repair_quota_waiting_run_statuses,
    retarget_youtube_cc_collection_languages,
    resume_youtube_cc_collection,
    review_youtube_cc_candidate,
)


def _search_response(video_ids):
    return {
        "items": [
            {"id": {"videoId": video_id}, "snippet": {"title": video_id}}
            for video_id in video_ids
        ]
    }


def _video(
    video_id,
    index=0,
    *,
    duration="PT2M10S",
    license_code="creativeCommon",
    caption="true",
):
    return {
        "id": video_id,
        "snippet": {
            "title": f"รีวิวมือถือจริง {index}",
            "description": "รีวิวกล้อง แบตเตอรี่ และประสิทธิภาพ",
            "channelId": f"channel-{index % 2}",
            "channelTitle": f"Creator {index % 2}",
            "categoryId": "28",
            "publishedAt": "2025-01-01T00:00:00Z",
            "liveBroadcastContent": "none",
        },
        "contentDetails": {"duration": duration, "caption": caption},
        "statistics": {
            "viewCount": str(10000 + index * 1000),
            "likeCount": str(500 + index * 10),
            "commentCount": str(40 + index),
        },
        "status": {"license": license_code, "privacyStatus": "public"},
    }


def _transcript(video_id, _languages):
    transcript = f"วันนี้รีวิวมือถือ {video_id} กล้อง แบตเตอรี่ จอ และประสิทธิภาพ"
    return {
        "language": "th",
        "caption_type": "manual",
        "segments": [{"text": transcript, "start": 0.0, "duration": 30.0}],
        "segment_count": 1,
        "start_seconds": 0.0,
        "end_seconds": 30.0,
        "transcript": transcript,
        "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
    }


class YouTubeCCDatasetTests(unittest.TestCase):
    def test_notebooklm_unknown_import_preserves_validation_and_test_roles(self):
        for index, split in enumerate(('validation', 'test')):
            with self.subTest(split=split), tempfile.TemporaryDirectory() as temp_dir:
                video_id = f'unknw{index:06d}'
                channel = next(f'unknown-channel-{i}' for i in range(1000)
                               if channel_dataset_split(f'unknown-channel-{i}')[0] == split)
                video = _video(video_id)
                video['snippet']['channelId'] = channel
                created = create_notebooklm_transcript_candidate(self.db, api_key='test-key',
                    video_url=f'https://youtube.com/watch?v={video_id}',
                    transcript=(f'Keyboard switches and typing sound {video_id}. ' * 20),
                    proposed_leaf_key='unknown', transcript_language='th', caption_type='unspecified',
                    youtube_getter=lambda *_a, **_k: {'items': [video]},
                    artifact_root=Path(temp_dir) / 'raw')
                review_youtube_cc_candidate(self.db, collection_run_id=created['collection_run_id'],
                    source_youtube_id=video_id, decision='approve', reviewer='test-reviewer',
                    reviewed_leaf_key='unknown', transcript_quality='good', notes='Test fixture only',
                    review_root=Path(temp_dir) / 'reviews')
                row = self.db.query(DatasetContent).filter_by(source_youtube_id=video_id).one()
                self.assertEqual(row.data_split, split)
                self.assertFalse(row.is_training_eligible)
                self.assertFalse(row.is_keyword_recommendation_eligible)
                self.assertFalse(row.is_duration_recommendation_eligible)
                self.assertEqual(out_of_scope_evaluation_query(self.db).filter_by(dataset_id=row.dataset_id).count(), 1)

    def test_new_notebooklm_holdouts_have_reference_permissions_disabled_at_import(self):
        for index, expected_split in enumerate(('validation', 'test')):
            with self.subTest(split=expected_split), tempfile.TemporaryDirectory() as temp_dir:
                video_id = f'guard{index:06d}'
                channel = next(f'held-channel-{i}' for i in range(1000)
                               if channel_dataset_split(f'held-channel-{i}')[0] == expected_split)
                video = _video(video_id)
                video['snippet']['channelId'] = channel
                created = create_notebooklm_transcript_candidate(self.db, api_key='test-key',
                    video_url=f'https://youtube.com/watch?v={video_id}',
                    transcript=(f'รีวิวมือถือ {video_id} กล้อง แบตเตอรี่ หน้าจอ ประสิทธิภาพ ' * 8),
                    proposed_leaf_key='phone', transcript_language='th', caption_type='unspecified',
                    youtube_getter=lambda *_a, **_k: {'items': [video]},
                    artifact_root=Path(temp_dir) / 'raw')
                review_youtube_cc_candidate(self.db, collection_run_id=created['collection_run_id'],
                    source_youtube_id=video_id, decision='approve', reviewer='admin',
                    reviewed_leaf_key='phone', transcript_quality='good', notes='Checked source',
                    review_root=Path(temp_dir) / 'reviews')
                row = self.db.query(DatasetContent).filter_by(source_youtube_id=video_id).one()
                self.assertEqual(row.data_split, expected_split)
                self.assertTrue(row.is_training_eligible)
                self.assertFalse(row.is_keyword_recommendation_eligible)
                self.assertFalse(row.is_duration_recommendation_eligible)

    def test_large_text_columns_use_longtext_on_mysql(self):
        for model in (DatasetContent, UserContent):
            column_type = model.__table__.c.transcript.type
            self.assertEqual(
                column_type.compile(dialect=mysql.dialect()).upper(),
                "LONGTEXT",
            )
            self.assertEqual(
                column_type.compile(dialect=sqlite.dialect()).upper(),
                "TEXT",
            )

        summary_type = AnalysisResult.__table__.c.summary.type
        self.assertEqual(
            summary_type.compile(dialect=mysql.dialect()).upper(),
            "LONGTEXT",
        )
        self.assertEqual(
            summary_type.compile(dialect=sqlite.dialect()).upper(),
            "TEXT",
        )

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        sync_taxonomy_registry(self.db)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _collect(self, root: Path, *, count: int = 3):
        ids = [f"realcc{i:05d}" for i in range(count)]

        def youtube_getter(resource, **_kwargs):
            if resource == "search":
                return _search_response(ids)
            if resource == "videos":
                return {"items": [_video(video_id, index) for index, video_id in enumerate(ids)]}
            raise AssertionError(resource)

        candidates = root / "candidates.jsonl"
        reviews = root / "review.csv"
        manifest = root / "manifest.json"
        result = collect_youtube_cc_candidates(
            self.db,
            api_key="test-key",
            candidate_path=candidates,
            review_path=reviews,
            manifest_path=manifest,
            dataset_version="youtube-cc-test-v1",
            leaf_keys=["phone"],
            target_per_leaf=count,
            languages=["th", "en"],
            max_pages_per_query=1,
            transcript_fetcher=_transcript,
            youtube_getter=youtube_getter,
        )
        return result, candidates, reviews, manifest

    @staticmethod
    def _fill_review(path: Path, decisions):
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row, decision in zip(rows, decisions):
            row["decision"] = decision
            if decision:
                row["reviewer"] = "human@example.test"
                row["reviewed_at"] = "2026-08-12T04:30:00Z"
                row["review_notes"] = "Transcript and category checked against the video."
            if decision == "approve":
                row["reviewed_leaf_key"] = "phone"
                row["transcript_quality"] = "good"
            elif decision == "reject":
                row["transcript_quality"] = "poor"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_legacy_review_csv_without_view_metric_version_is_readable(self):
        legacy_fields = [
            field for field in REVIEW_FIELDS if field != "view_metric_version"
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            review_path = Path(temp_dir) / "legacy-review.csv"
            with review_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=legacy_fields)
                writer.writeheader()
                writer.writerow(
                    {
                        **{field: "" for field in legacy_fields},
                        "source_youtube_id": "legacy-video",
                    }
                )

            rows = _review_rows(review_path)

        self.assertEqual(rows[0]["source_youtube_id"], "legacy-video")
        self.assertEqual(rows[0]["view_metric_version"], "")

    def test_duration_parser_and_five_minute_boundary(self):
        self.assertEqual(parse_iso8601_duration("PT5M"), 300)
        self.assertEqual(parse_iso8601_duration("PT4M59S"), 299)
        self.assertEqual(parse_iso8601_duration("PT1H2M3S"), 3723)
        with self.assertRaises(YouTubeCCDatasetError):
            parse_iso8601_duration("not-a-duration")

    def test_notebooklm_full_transcript_is_trainable_without_duration_limit(self):
        video_id = "notebook001"
        transcript = (
            "รีวิวโทรศัพท์รุ่นใหม่แบบละเอียด กล้อง แบตเตอรี่ หน้าจอ "
            "ประสิทธิภาพ ซอฟต์แวร์ และประสบการณ์ใช้งานจริง " * 8
        ).strip()

        def youtube_getter(resource, **_kwargs):
            self.assertEqual(resource, "videos")
            return {"items": [_video(video_id, duration="PT12M")]}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            created = create_notebooklm_transcript_candidate(
                self.db,
                api_key="test-key",
                video_url=f"https://www.youtube.com/watch?v={video_id}",
                transcript=transcript,
                proposed_leaf_key="phone",
                transcript_language="th",
                caption_type="unspecified",
                youtube_getter=youtube_getter,
                artifact_root=root / "raw",
            )
            candidate = created["candidate"]
            self.assertEqual(candidate["transcript_scope"], "full_video")
            self.assertEqual(
                candidate["transcript_acquisition_method"],
                "notebooklm_manual_source",
            )
            self.assertFalse(candidate["transcript_timestamps_available"])
            self.assertEqual(candidate["duration_seconds"], 720)

            review_youtube_cc_candidate(
                self.db,
                collection_run_id=created["collection_run_id"],
                source_youtube_id=video_id,
                decision="approve",
                reviewer="admin@example.test [user:1]",
                reviewed_leaf_key="phone",
                transcript_quality="good",
                notes="Full NotebookLM source transcript checked against the video.",
                review_root=root / "reviews",
            )

        dataset = self.db.query(DatasetContent).filter_by(
            source_youtube_id=video_id
        ).one()
        self.assertTrue(dataset.is_training_eligible)
        self.assertEqual(dataset.is_keyword_recommendation_eligible, dataset.data_split == "train")
        self.assertFalse(dataset.is_duration_recommendation_eligible)
        self.assertEqual(dataset.transcript_scope, "full_video")
        self.assertEqual(dataset.transcript_window_seconds, 720)
        self.assertEqual(dataset.transcript_end_seconds, 720)
        self.assertEqual(production_transcript_query(self.db).count(), 1)

    def test_notebooklm_accepts_standard_license_without_public_captions(self):
        video_id = "standard001"
        transcript = (
            "ทดสอบรีวิวมือถือจาก NotebookLM ทั้งคลิป มีข้อมูลหน้าจอ กล้อง "
            "แบตเตอรี่ ราคา และประสบการณ์ใช้งานจริง " * 8
        ).strip()

        def youtube_getter(resource, **_kwargs):
            self.assertEqual(resource, "videos")
            return {
                "items": [
                    _video(
                        video_id,
                        duration="PT17M26S",
                        license_code="youtube",
                        caption="false",
                    )
                ]
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            created = create_notebooklm_transcript_candidate(
                self.db,
                api_key="test-key",
                video_url=f"https://www.youtube.com/watch?v={video_id}",
                transcript=transcript,
                proposed_leaf_key="phone",
                transcript_language="th",
                caption_type="unspecified",
                youtube_getter=youtube_getter,
                artifact_root=root / "raw",
            )
            candidate = created["candidate"]
            self.assertEqual(candidate["youtube_license_code"], "youtube")
            self.assertEqual(candidate["license_name"], "YouTube Standard License")
            self.assertFalse(candidate["public_captions_available"])
            self.assertTrue(all(candidate["automated_checks"].values()))

            review_youtube_cc_candidate(
                self.db,
                collection_run_id=created["collection_run_id"],
                source_youtube_id=video_id,
                decision="approve",
                reviewer="admin@example.test [user:1]",
                reviewed_leaf_key="phone",
                transcript_quality="good",
                notes="NotebookLM transcript checked against the public source.",
                review_root=root / "reviews",
            )

        dataset = self.db.query(DatasetContent).filter_by(
            source_youtube_id=video_id
        ).one()
        self.assertEqual(dataset.dataset_source, "youtube_public_research")
        self.assertEqual(dataset.license_name, "YouTube Standard License")
        self.assertEqual(dataset.transcript_source, "notebooklm_source_transcript")
        self.assertTrue(dataset.is_training_eligible)
        self.assertEqual(production_transcript_query(self.db).count(), 1)

    def test_notebooklm_rejects_duplicate_transcript_in_same_batch(self):
        transcript = (
            "รีวิวโทรศัพท์จาก NotebookLM มีข้อมูลกล้อง แบตเตอรี่ หน้าจอ "
            "ประสิทธิภาพ ราคา และประสบการณ์ใช้งานจริง " * 8
        ).strip()

        def youtube_getter(resource, **kwargs):
            self.assertEqual(resource, "videos")
            return {"items": [_video(str(kwargs["id"]))]}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "raw"
            first = create_notebooklm_transcript_candidate(
                self.db,
                api_key="test-key",
                video_url="https://www.youtube.com/watch?v=notebook001",
                transcript=transcript,
                proposed_leaf_key="phone",
                transcript_language="th",
                youtube_getter=youtube_getter,
                artifact_root=root,
            )

            with self.assertRaisesRegex(
                YouTubeCCDatasetError,
                "transcript duplicates another file in the current import batch",
            ):
                create_notebooklm_transcript_candidate(
                    self.db,
                    api_key="test-key",
                    video_url="https://www.youtube.com/watch?v=notebook002",
                    transcript=transcript,
                    proposed_leaf_key="phone",
                    transcript_language="th",
                    collection_run_id=first["collection_run_id"],
                    youtube_getter=youtube_getter,
                    artifact_root=root,
                )

    def test_notebooklm_allows_more_than_three_videos_from_one_channel(self):
        def youtube_getter(resource, **kwargs):
            self.assertEqual(resource, "videos")
            return {"items": [_video(str(kwargs["id"]), index=0)]}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "raw"
            run_id = None
            for index in range(3):
                created = create_notebooklm_transcript_candidate(
                    self.db,
                    api_key="test-key",
                    video_url=(
                        "https://www.youtube.com/watch?v="
                        f"laptop{index:05d}"
                    ),
                    transcript=(
                        f"Laptop review sample {index} covers processor, memory, "
                        "display, battery, keyboard, cooling, ports and daily use. "
                    )
                    * 4,
                    proposed_leaf_key="laptop",
                    transcript_language="th",
                    collection_run_id=run_id,
                    youtube_getter=youtube_getter,
                    artifact_root=root,
                )
                run_id = created["collection_run_id"]

            fourth = create_notebooklm_transcript_candidate(
                self.db,
                api_key="test-key",
                video_url="https://www.youtube.com/watch?v=laptop00003",
                transcript=(
                    "Fourth laptop review covers processor, memory, display, "
                    "battery, keyboard, cooling, ports and daily use. "
                )
                * 4,
                proposed_leaf_key="laptop",
                transcript_language="th",
                collection_run_id=run_id,
                youtube_getter=youtube_getter,
                artifact_root=root,
            )

        self.assertEqual(fourth["candidate_count"], 4)
        self.assertEqual(fourth["candidate"]["proposed_leaf_key"], "laptop")

    def test_phone_and_camera_queries_exclude_common_false_positives(self):
        phone_queries = collection_queries_for_leaf("phone")
        camera_queries = collection_queries_for_leaf("camera")
        self.assertTrue(any("-case" in query for query in phone_queries))
        self.assertTrue(any("-phone" in query for query in camera_queries))
        self.assertTrue(any("mirrorless" in query for query in camera_queries))
        self.assertEqual(len(phone_queries), len(set(phone_queries)))
        self.assertTrue(any("งบ 5000" in query for query in phone_queries))
        self.assertTrue(any("ถ่ายรูปกลางคืน" in query for query in phone_queries))
        self.assertTrue(any("แกะกล่องมือถือ" in query for query in phone_queries))
        self.assertTrue(any("หลังใช้ 1 เดือน" in query for query in phone_queries))

    def test_new_collection_defaults_to_thai_only(self):
        requested_languages = []
        video_id = "thaidefault1"

        def youtube_getter(resource, **_kwargs):
            if resource == "search":
                return _search_response([video_id])
            if resource == "videos":
                return {"items": [_video(video_id)]}
            raise AssertionError(resource)

        def recording_transcript(requested_video_id, languages):
            requested_languages.append(tuple(languages))
            return _transcript(requested_video_id, languages)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates.jsonl",
                review_path=root / "review.csv",
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-thai-default-v1",
                leaf_keys=["phone"],
                target_per_leaf=1,
                performance_target_per_leaf=0,
                max_pages_per_query=1,
                transcript_fetcher=recording_transcript,
                youtube_getter=youtube_getter,
            )

        queries = result["config"]["queries_by_leaf"]["phone"]
        self.assertEqual(requested_languages, [("th",)])
        self.assertEqual(tuple(result["config"]["languages"]), ("th",))
        self.assertEqual(result["config"]["min_thai_per_leaf"], 1)
        self.assertEqual(
            result["config"]["language_balance_policy"],
            "thai_only_v1",
        )
        self.assertTrue(
            all(
                any("\u0e00" <= character <= "\u0e7f" for character in query)
                for query in queries
            )
        )

    def test_collection_creates_real_candidate_artifact_but_no_dataset_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result, candidates, reviews, manifest = self._collect(Path(temp_dir))
            candidate_rows = [
                json.loads(line)
                for line in candidates.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            with reviews.open("r", encoding="utf-8", newline="") as handle:
                review_rows = list(csv.DictReader(handle))
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "collected")
        self.assertEqual(len(candidate_rows), 3)
        self.assertTrue(manifest.name.endswith(".json"))
        self.assertTrue(all(item["youtube_license_code"] == "creativeCommon" for item in candidate_rows))
        self.assertTrue(all(item["transcript_source"] == "youtube_public_caption" for item in candidate_rows))
        self.assertTrue(all(item["duration_seconds"] > 0 for item in candidate_rows))
        self.assertTrue(
            all(item["transcript_window_seconds"] == 300 for item in candidate_rows)
        )
        self.assertTrue(all(not item["decision"] for item in review_rows))
        self.assertEqual(
            sum(manifest_payload["view_metric_versions"].values()),
            len(candidate_rows),
        )
        self.assertEqual(self.db.query(DatasetContent).count(), 0)
        run = self.db.query(DatasetCollectionRun).one()
        self.assertEqual(run.transcripts_collected, 3)

    def test_long_source_video_is_trainable_but_not_duration_evidence(self):
        video_id = "longvideo01"

        def youtube_getter(resource, **kwargs):
            if resource == "search":
                return _search_response([video_id])
            if resource == "videos":
                return {"items": [_video(video_id, duration="PT1H2M3S")]}
            raise AssertionError(resource)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidates = root / "candidates.jsonl"
            reviews = root / "review.csv"
            collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=candidates,
                review_path=reviews,
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-long-source-v1",
                leaf_keys=["phone"],
                target_per_leaf=1,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                max_pages_per_query=1,
                transcript_fetcher=_transcript,
                youtube_getter=youtube_getter,
            )
            candidate = json.loads(candidates.read_text(encoding="utf-8").strip())
            self.assertEqual(candidate["duration_seconds"], 3723)
            self.assertEqual(candidate["transcript_window_seconds"], 300)

            self._fill_review(reviews, ["approve"])
            import_reviewed_youtube_cc_dataset(
                self.db,
                candidate_path=candidates,
                review_path=reviews,
            )

        row = self.db.query(DatasetContent).one()
        self.assertEqual(row.duration_seconds, 3723)
        self.assertTrue(row.is_training_eligible)
        self.assertEqual(row.is_keyword_recommendation_eligible, row.data_split == "train")
        self.assertFalse(row.is_duration_recommendation_eligible)
        self.assertEqual(production_transcript_query(self.db).count(), 1)

    def test_collection_uses_separate_diverse_and_high_performance_samples(self):
        ids = [f"strategy{i:03d}" for i in range(4)]
        search_orders = []

        def youtube_getter(resource, **kwargs):
            if resource == "search":
                search_orders.append(kwargs["order"])
                return _search_response(ids)
            if resource == "videos":
                requested = kwargs["id"].split(",")
                return {
                    "items": [
                        _video(video_id, ids.index(video_id))
                        for video_id in requested
                    ]
                }
            raise AssertionError(resource)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates.jsonl",
                review_path=root / "review.csv",
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-strategy-v1",
                leaf_keys=["phone"],
                target_per_leaf=4,
                performance_target_per_leaf=2,
                languages=["th", "en"],
                max_pages_per_query=1,
                transcript_fetcher=_transcript,
                youtube_getter=youtube_getter,
            )
            rows = [
                json.loads(line)
                for line in (root / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

        self.assertEqual(result["status"], "collected")
        self.assertEqual(search_orders[:2], ["viewCount", "relevance"])
        counts = Counter(row["collection_strategy"] for row in rows)
        self.assertEqual(counts[RECOMMENDATION_HIGH_PERFORMANCE_STRATEGY], 2)
        self.assertEqual(counts[CLASSIFICATION_DIVERSE_STRATEGY], 2)
        self.assertTrue(all(row["average_views_per_day"] > 0 for row in rows))
        self.assertTrue(all(row["view_metric_version"] for row in rows))
        self.assertEqual(
            sorted(row["performance_rank_within_leaf"] for row in rows),
            [1, 2, 3, 4],
        )

    def test_collection_reserves_minimum_thai_transcripts_per_leaf(self):
        ids = ["en00000001", "en00000002", "en00000003", "en00000004", "th00000001", "th00000002"]

        def youtube_getter(resource, **kwargs):
            if resource == "search":
                return _search_response(ids)
            if resource == "videos":
                items = []
                for index, video_id in enumerate(kwargs["id"].split(",")):
                    item = _video(video_id, index)
                    item["snippet"]["channelId"] = f"language-channel-{index}"
                    items.append(item)
                return {"items": items}
            raise AssertionError(resource)

        def transcript_fetcher(video_id, _languages):
            language = "th" if video_id.startswith("th") else "en"
            transcript = f"{language} transcript {video_id}"
            return {
                "language": language,
                "caption_type": "manual",
                "segments": [{"text": transcript, "start": 0.0, "duration": 20.0}],
                "segment_count": 1,
                "start_seconds": 0.0,
                "end_seconds": 20.0,
                "transcript": transcript,
                "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest(),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates.jsonl",
                review_path=root / "review.csv",
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-language-balance-v1",
                leaf_keys=["phone"],
                target_per_leaf=4,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                min_thai_per_leaf=2,
                max_pages_per_query=1,
                transcript_fetcher=transcript_fetcher,
                youtube_getter=youtube_getter,
            )
            rows = [
                json.loads(line)
                for line in (root / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

        languages = Counter(row["transcript_language"] for row in rows)
        self.assertEqual(result["status"], "collected")
        self.assertEqual(languages, Counter({"en": 2, "th": 2}))
        self.assertEqual(
            result["quality_filters"]["skipped_by_reason"][
                "non_thai_capacity_reserved"
            ],
            2,
        )
        leaf_progress = result["progress"]["by_leaf"][0]
        self.assertEqual(leaf_progress["thai_minimum"], 2)
        self.assertEqual(leaf_progress["language_counts"]["th"], 2)

    def test_existing_approved_thai_satisfies_collection_minimum(self):
        existing_transcript = "approved Thai phone transcript"
        self.db.add(
            DatasetContent(
                title="Approved Thai phone review",
                transcript=existing_transcript,
                dataset_source="youtube_cc",
                dataset_version="youtube-cc-existing-thai-v1",
                source_record_id="existing-thai-phone",
                source_youtube_id="existingth01",
                source_channel_id="existing-thai-channel",
                taxonomy_leaf_key="phone",
                category_level_1="Technology",
                category_level_2="Electronics",
                category_level_3="Phone",
                language="th",
                transcript_sha256=hashlib.sha256(
                    existing_transcript.encode()
                ).hexdigest(),
                is_training_eligible=True,
                is_active=True,
            )
        )
        self.db.commit()
        ids = [f"existingen{i:02d}" for i in range(4)]

        def youtube_getter(resource, **kwargs):
            if resource == "search":
                return _search_response(ids)
            if resource == "videos":
                return {
                    "items": [
                        _video(video_id, index)
                        for index, video_id in enumerate(kwargs["id"].split(","))
                    ]
                }
            raise AssertionError(resource)

        def english_transcript(video_id, _languages):
            transcript = f"English phone review transcript {video_id}"
            return {
                "language": "en",
                "caption_type": "manual",
                "segments": [
                    {"text": transcript, "start": 0.0, "duration": 20.0}
                ],
                "segment_count": 1,
                "start_seconds": 0.0,
                "end_seconds": 20.0,
                "transcript": transcript,
                "transcript_sha256": hashlib.sha256(
                    transcript.encode()
                ).hexdigest(),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates.jsonl",
                review_path=root / "review.csv",
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-existing-thai-v1",
                leaf_keys=["phone"],
                target_per_leaf=4,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                min_thai_per_leaf=1,
                max_pages_per_query=1,
                transcript_fetcher=english_transcript,
                youtube_getter=youtube_getter,
            )

        self.assertEqual(result["status"], "collected")
        self.assertNotIn(
            "non_thai_capacity_reserved",
            result["quality_filters"]["skipped_by_reason"],
        )
        leaf_progress = result["progress"]["by_leaf"][0]
        self.assertEqual(leaf_progress["language_counts"]["en"], 4)
        self.assertEqual(
            leaf_progress["existing_training_language_counts"]["th"],
            1,
        )
        self.assertEqual(
            leaf_progress["cumulative_training_language_counts"]["th"],
            1,
        )
        self.assertEqual(leaf_progress["thai_remaining"], 0)

    def test_collection_accepts_multiple_videos_from_the_same_channel(self):
        ids = [f"channelcap{i:02d}" for i in range(5)]

        def youtube_getter(resource, **kwargs):
            if resource == "search":
                return _search_response(ids)
            if resource == "videos":
                items = []
                for index, video_id in enumerate(kwargs["id"].split(",")):
                    item = _video(video_id, index)
                    item["snippet"]["channelId"] = (
                        "repeated-channel" if index < 3 else f"unique-channel-{index}"
                    )
                    items.append(item)
                return {"items": items}
            raise AssertionError(resource)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates.jsonl",
                review_path=root / "review.csv",
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-channel-cap-v1",
                leaf_keys=["phone"],
                target_per_leaf=4,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                min_thai_per_leaf=0,
                max_pages_per_query=1,
                transcript_fetcher=_transcript,
                youtube_getter=youtube_getter,
            )
            rows = [
                json.loads(line)
                for line in (root / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

        channels = Counter(row["channel_id"] for row in rows)
        self.assertEqual(result["status"], "collected")
        self.assertEqual(channels["repeated-channel"], 3)
        self.assertNotIn(
            "channel_cap_reached",
            result["quality_filters"]["skipped_by_reason"],
        )

    def test_quota_exhaustion_checkpoints_as_quota_waiting(self):
        callbacks = []

        def youtube_getter(resource, **_kwargs):
            raise YouTubeQuotaExceededError(resource, 429, "Quota exceeded")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(YouTubeQuotaExceededError):
                collect_youtube_cc_candidates(
                    self.db,
                    api_key="test-key",
                    candidate_path=root / "candidates.jsonl",
                    review_path=root / "review.csv",
                    manifest_path=root / "manifest.json",
                    dataset_version="youtube-cc-quota-v1",
                    leaf_keys=["phone"],
                    target_per_leaf=1,
                    performance_target_per_leaf=0,
                    languages=["th", "en"],
                    min_thai_per_leaf=0,
                    max_pages_per_query=1,
                    transcript_fetcher=_transcript,
                    youtube_getter=youtube_getter,
                    progress_callback=lambda manifest: callbacks.append(
                        manifest["status"]
                    ),
                )
            manifest = json.loads(
                (root / "manifest.json").read_text(encoding="utf-8")
            )
            run = self.db.query(DatasetCollectionRun).one()
            self.assertEqual(run.status, "quota_waiting")
            self.assertIsNone(run.completed_at)
            self.assertEqual(run.errors_count, 0)
            self.assertEqual(callbacks, ["running", "quota_waiting"])
            self.assertTrue(manifest["quota"]["retryable"])

            run.status = "failed"
            run.errors_count = 1
            run.completed_at = datetime.now()
            self.db.commit()
            repaired = repair_quota_waiting_run_statuses(self.db)
            self.db.refresh(run)

        self.assertEqual(repaired["run_ids"], [run.collection_run_id])
        self.assertEqual(run.status, "quota_waiting")
        self.assertEqual(run.errors_count, 0)
        self.assertIsNone(run.completed_at)

    def test_http_429_is_recognized_as_quota_exhaustion(self):
        error = urllib.error.HTTPError(
            "https://example.test",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"error":{"message":"Quota exceeded"}}'),
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(YouTubeQuotaExceededError):
                _youtube_get("search", api_key="test", timeout_seconds=1, q="phone")

    def test_transcript_ip_block_checkpoints_without_advancing_search_page(self):
        video_id = "blocked001"
        callbacks = []

        def youtube_getter(resource, **_kwargs):
            if resource == "search":
                return {
                    **_search_response([video_id]),
                    "nextPageToken": "NEXT_PAGE",
                }
            if resource == "videos":
                return {"items": [_video(video_id)]}
            raise AssertionError(resource)

        def blocked_transcript(requested_video_id, _languages):
            raise YouTubeTranscriptProviderBlockedError(
                requested_video_id,
                "IP blocked",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(YouTubeTranscriptProviderBlockedError):
                collect_youtube_cc_candidates(
                    self.db,
                    api_key="test-key",
                    candidate_path=root / "candidates.jsonl",
                    review_path=root / "review.csv",
                    manifest_path=root / "manifest.json",
                    dataset_version="youtube-cc-transcript-wait-v1",
                    leaf_keys=["phone"],
                    target_per_leaf=1,
                    performance_target_per_leaf=0,
                    languages=["th", "en"],
                    min_thai_per_leaf=0,
                    max_pages_per_query=1,
                    transcript_fetcher=blocked_transcript,
                    youtube_getter=youtube_getter,
                    progress_callback=lambda manifest: callbacks.append(
                        manifest["status"]
                    ),
                )

            manifest = json.loads(
                (root / "manifest.json").read_text(encoding="utf-8")
            )
            run = self.db.query(DatasetCollectionRun).one()

        self.assertEqual(run.status, "transcript_waiting")
        self.assertIsNone(run.completed_at)
        self.assertEqual(run.transcripts_collected, 0)
        self.assertEqual(manifest["search_state"], {})
        self.assertTrue(manifest["transcript_provider"]["retryable"])
        self.assertEqual(callbacks, ["running", "transcript_waiting"])

    def test_pacing_budget_checkpoints_and_resume_skips_attempted_transcripts(self):
        video_ids = ["paced00001", "paced00002", "paced00003"]
        transcript_calls = []

        def youtube_getter(resource, **kwargs):
            if resource == "search":
                return _search_response(video_ids)
            if resource == "videos":
                requested = kwargs["id"].split(",")
                return {
                    "items": [
                        _video(video_id, video_ids.index(video_id))
                        for video_id in requested
                    ]
                }
            raise AssertionError(resource)

        def recording_transcript(video_id, languages):
            transcript_calls.append(video_id)
            return _transcript(video_id, languages)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates.jsonl",
                review_path=root / "review.csv",
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-pacing-v1",
                leaf_keys=["phone"],
                target_per_leaf=3,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                min_thai_per_leaf=0,
                max_pages_per_query=1,
                max_transcript_attempts_per_execution=1,
                transcript_fetcher=recording_transcript,
                youtube_getter=youtube_getter,
            )
            run = self.db.query(DatasetCollectionRun).one()

            self.assertEqual(first["status"], "pacing_paused")
            self.assertTrue(first["pacing"]["retryable"])
            self.assertEqual(first["pacing"]["cooldown_minutes"], 30.0)
            self.assertIn("next_resume_at", first["pacing"])
            self.assertIsNone(run.completed_at)
            self.assertEqual(transcript_calls, [video_ids[0]])

            with self.assertRaises(YouTubeCollectionResumeCooldownError):
                resume_youtube_cc_collection(
                    self.db,
                    collection_run_id=run.collection_run_id,
                    api_key="test-key",
                    max_pages_per_query=1,
                    max_transcript_attempts_per_execution=3,
                    transcript_fetcher=recording_transcript,
                    youtube_getter=youtube_getter,
                )

            resumed = resume_youtube_cc_collection(
                self.db,
                collection_run_id=run.collection_run_id,
                api_key="test-key",
                max_pages_per_query=1,
                max_transcript_attempts_per_execution=3,
                resume_cooldown_minutes=0,
                transcript_fetcher=recording_transcript,
                youtube_getter=youtube_getter,
            )

        self.assertEqual(resumed["status"], "collected")
        self.assertEqual(transcript_calls, video_ids)
        self.db.refresh(run)
        self.assertEqual(run.resume_count, 1)
        self.assertEqual(run.transcripts_collected, 3)

    def test_retarget_run_to_thai_archives_non_thai_candidates(self):
        video_ids = ["retargetth1", "retargeten1", "retargetth2"]

        def youtube_getter(resource, **kwargs):
            if resource == "search":
                return _search_response(video_ids)
            if resource == "videos":
                requested = kwargs["id"].split(",")
                return {
                    "items": [
                        _video(video_id, video_ids.index(video_id))
                        for video_id in requested
                    ]
                }
            raise AssertionError(resource)

        def mixed_transcript(video_id, _languages):
            language = "en" if video_id == "retargeten1" else "th"
            transcript = f"{language} transcript {video_id}"
            return {
                "language": language,
                "caption_type": "manual",
                "segments": [
                    {"text": transcript, "start": 0.0, "duration": 20.0}
                ],
                "segment_count": 1,
                "start_seconds": 0.0,
                "end_seconds": 20.0,
                "transcript": transcript,
                "transcript_sha256": hashlib.sha256(
                    transcript.encode()
                ).hexdigest(),
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates.jsonl",
                review_path=root / "review.csv",
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-retarget-v1",
                leaf_keys=["phone"],
                target_per_leaf=3,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                min_thai_per_leaf=0,
                max_pages_per_query=1,
                max_transcript_attempts_per_execution=2,
                transcript_fetcher=mixed_transcript,
                youtube_getter=youtube_getter,
            )
            run = self.db.query(DatasetCollectionRun).one()
            self.assertEqual(first["status"], "pacing_paused")

            retargeted = retarget_youtube_cc_collection_languages(
                self.db,
                collection_run_id=run.collection_run_id,
                languages=("th",),
            )
            candidate_rows = [
                json.loads(line)
                for line in (root / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            review_rows = _review_rows(root / "review.csv")
            archive_path = Path(
                retargeted["retarget"]["excluded_artifact_path"]
            )
            archived_rows = [
                json.loads(line)
                for line in archive_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.db.refresh(run)
            config = json.loads(run.query_config_json)
            self.assertEqual(config["languages"], ["th"])
            self.assertEqual(config["language_balance_policy"], "thai_only_v1")
            self.assertEqual(config["min_thai_per_leaf"], 3)
            self.assertTrue(
                all(
                    any("\u0e00" <= character <= "\u0e7f" for character in query)
                    for query in config["queries_by_leaf"]["phone"]
                )
            )
            self.assertEqual(json.loads(run.languages_json), ["th"])
            self.assertEqual(run.transcripts_collected, 1)
            self.assertEqual(retargeted["progress"]["language_counts"], {"th": 1})
            self.assertEqual(len(candidate_rows), 1)
            self.assertEqual(candidate_rows[0]["transcript_language"], "th")
            self.assertEqual(candidate_rows[0]["run_key"], run.run_key)
            self.assertEqual(len(review_rows), 1)
            self.assertEqual(len(archived_rows), 1)
            self.assertEqual(archived_rows[0]["transcript_language"], "en")
            self.assertEqual(
                archived_rows[0]["exclusion"]["allowed_languages"],
                ["th"],
            )

            next_ids = ["retargeten1", "freshthai01"]
            transcript_calls = []

            def next_youtube_getter(resource, **kwargs):
                if resource == "search":
                    return _search_response(next_ids)
                if resource == "videos":
                    requested = kwargs["id"].split(",")
                    return {
                        "items": [
                            _video(video_id, next_ids.index(video_id))
                            for video_id in requested
                        ]
                    }
                raise AssertionError(resource)

            def next_transcript(video_id, languages):
                transcript_calls.append(video_id)
                return _transcript(video_id, languages)

            next_result = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates-next.jsonl",
                review_path=root / "review-next.csv",
                manifest_path=root / "manifest-next.json",
                dataset_version="youtube-cc-retarget-next-v1",
                leaf_keys=["phone"],
                target_per_leaf=1,
                performance_target_per_leaf=0,
                max_pages_per_query=1,
                transcript_fetcher=next_transcript,
                youtube_getter=next_youtube_getter,
            )
            next_rows = [
                json.loads(line)
                for line in (root / "candidates-next.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

            self.assertEqual(transcript_calls, ["freshthai01"])
            self.assertEqual(
                [row["source_youtube_id"] for row in next_rows],
                ["freshthai01"],
            )
            self.assertEqual(
                next_result["deduplication"]["prior_excluded_artifacts"],
                1,
            )
            self.assertEqual(
                next_result["deduplication"]["prior_excluded_artifact_rows"],
                1,
            )
            self.assertGreaterEqual(
                next_result["deduplication"]["skipped_by_reason"][
                    "duplicate_previous_video"
                ],
                1,
            )

    def test_empty_schema_three_run_upgrades_quality_controls_on_resume(self):
        video_id = "upgraded001"

        def quota_getter(resource, **_kwargs):
            raise YouTubeQuotaExceededError(resource, 429, "Quota exceeded")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(YouTubeQuotaExceededError):
                collect_youtube_cc_candidates(
                    self.db,
                    api_key="test-key",
                    candidate_path=root / "candidates.jsonl",
                    review_path=root / "review.csv",
                    manifest_path=root / "manifest.json",
                    dataset_version="youtube-cc-upgrade-v1",
                    leaf_keys=["phone"],
                    target_per_leaf=1,
                    performance_target_per_leaf=0,
                    languages=["th", "en"],
                    min_thai_per_leaf=0,
                    max_pages_per_query=1,
                    transcript_fetcher=_transcript,
                    youtube_getter=quota_getter,
                )
            run = self.db.query(DatasetCollectionRun).one()
            config = json.loads(run.query_config_json)
            for field in (
                "min_thai_per_leaf",
                "language_balance_policy",
                "queries_by_leaf",
            ):
                config.pop(field, None)
            config["schema_version"] = 3
            run.run_key = "legacy-empty-run-key"
            run.query_config_json = json.dumps(config)
            self.db.commit()

            def youtube_getter(resource, **kwargs):
                if resource == "search":
                    return _search_response([video_id])
                if resource == "videos":
                    return {"items": [_video(video_id)]}
                raise AssertionError(resource)

            resumed = resume_youtube_cc_collection(
                self.db,
                collection_run_id=run.collection_run_id,
                api_key="test-key",
                max_pages_per_query=1,
                transcript_fetcher=_transcript,
                youtube_getter=youtube_getter,
            )

        self.db.refresh(run)
        upgraded_config = json.loads(run.query_config_json)
        self.assertEqual(resumed["status"], "collected")
        self.assertEqual(upgraded_config["schema_version"], 5)
        self.assertEqual(upgraded_config["min_thai_per_leaf"], 1)
        self.assertNotIn("max_videos_per_channel_per_leaf", upgraded_config)
        self.assertNotIn("channel_diversity_policy", upgraded_config)
        self.assertIn("-case", " ".join(upgraded_config["queries_by_leaf"]["phone"]))

    def test_collection_deduplicates_candidates_across_runs(self):
        responses = [
            ["existing001"],
            ["existing001", "fresh00001"],
        ]
        collection_number = 0

        def make_getter(response_ids):
            def youtube_getter(resource, **kwargs):
                if resource == "search":
                    return _search_response(response_ids)
                if resource == "videos":
                    requested = kwargs["id"].split(",")
                    return {
                        "items": [
                            _video(video_id, response_ids.index(video_id))
                            for video_id in requested
                        ]
                    }
                raise AssertionError(resource)

            return youtube_getter

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for response_ids in responses:
                collection_number += 1
                collect_youtube_cc_candidates(
                    self.db,
                    api_key="test-key",
                    candidate_path=root / f"candidates-{collection_number}.jsonl",
                    review_path=root / f"review-{collection_number}.csv",
                    manifest_path=root / f"manifest-{collection_number}.json",
                    dataset_version=f"youtube-cc-dedup-v{collection_number}",
                    leaf_keys=["phone"],
                    target_per_leaf=1,
                    performance_target_per_leaf=0,
                    languages=["th", "en"],
                    max_pages_per_query=1,
                    transcript_fetcher=_transcript,
                    youtube_getter=make_getter(response_ids),
                )
            second_manifest = json.loads(
                (root / "manifest-2.json").read_text(encoding="utf-8")
            )
            second_rows = [
                json.loads(line)
                for line in (root / "candidates-2.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

        self.assertEqual(
            [row["source_youtube_id"] for row in second_rows],
            ["fresh00001"],
        )
        self.assertGreaterEqual(
            second_manifest["deduplication"]["skipped_by_reason"][
                "duplicate_previous_video"
            ],
            1,
        )
        self.assertEqual(self.db.query(DatasetCollectionRun).count(), 2)

    def test_prior_runs_do_not_limit_same_channel_candidates(self):
        first_ids = ["priorchannel1", "priorchannel2"]
        second_ids = ["priorchannel3", "otherchannel1"]

        def make_getter(response_ids):
            def youtube_getter(resource, **kwargs):
                if resource == "search":
                    return _search_response(response_ids)
                if resource == "videos":
                    items = []
                    for index, video_id in enumerate(kwargs["id"].split(",")):
                        item = _video(video_id, index)
                        item["snippet"]["channelId"] = (
                            "shared-channel"
                            if video_id != "otherchannel1"
                            else "other-channel"
                        )
                        items.append(item)
                    return {"items": items}
                raise AssertionError(resource)

            return youtube_getter

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates-1.jsonl",
                review_path=root / "review-1.csv",
                manifest_path=root / "manifest-1.json",
                dataset_version="youtube-cc-channel-history-v1",
                leaf_keys=["phone"],
                target_per_leaf=2,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                min_thai_per_leaf=0,
                max_pages_per_query=1,
                transcript_fetcher=_transcript,
                youtube_getter=make_getter(first_ids),
            )
            second = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates-2.jsonl",
                review_path=root / "review-2.csv",
                manifest_path=root / "manifest-2.json",
                dataset_version="youtube-cc-channel-history-v2",
                leaf_keys=["phone"],
                target_per_leaf=1,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                min_thai_per_leaf=0,
                max_pages_per_query=1,
                transcript_fetcher=_transcript,
                youtube_getter=make_getter(second_ids),
            )
            rows = [
                json.loads(line)
                for line in (root / "candidates-2.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

        self.assertEqual(
            [row["source_youtube_id"] for row in rows],
            ["priorchannel3"],
        )
        self.assertNotIn(
            "channel_cap_reached",
            second["quality_filters"]["skipped_by_reason"],
        )

    def test_partial_collection_resumes_from_saved_page_token(self):
        first_id = "resume00001"
        second_id = "resume00002"
        page_tokens = []

        def youtube_getter(resource, **kwargs):
            if resource == "search":
                page_token = kwargs.get("pageToken")
                page_tokens.append(page_token)
                if page_token == "next-page":
                    return _search_response([second_id])
                return {
                    **_search_response([first_id]),
                    "nextPageToken": "next-page",
                }
            if resource == "videos":
                requested = kwargs["id"].split(",")
                return {
                    "items": [
                        _video(video_id, 0 if video_id == first_id else 1)
                        for video_id in requested
                    ]
                }
            raise AssertionError(resource)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = collect_youtube_cc_candidates(
                self.db,
                api_key="test-key",
                candidate_path=root / "candidates.jsonl",
                review_path=root / "review.csv",
                manifest_path=root / "manifest.json",
                dataset_version="youtube-cc-resume-v1",
                leaf_keys=["phone"],
                target_per_leaf=2,
                performance_target_per_leaf=0,
                languages=["th", "en"],
                max_pages_per_query=1,
                transcript_fetcher=_transcript,
                youtube_getter=youtube_getter,
            )
            run = self.db.query(DatasetCollectionRun).one()
            self.assertEqual(first["status"], "partial")
            resumed = resume_youtube_cc_collection(
                self.db,
                collection_run_id=run.collection_run_id,
                api_key="test-key",
                max_pages_per_query=1,
                transcript_fetcher=_transcript,
                youtube_getter=youtube_getter,
            )
            rows = [
                json.loads(line)
                for line in (root / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]

        self.assertEqual(resumed["status"], "collected")
        self.assertEqual({row["source_youtube_id"] for row in rows}, {first_id, second_id})
        self.assertIn("next-page", page_tokens)
        self.db.refresh(run)
        self.assertEqual(run.resume_count, 1)
        self.assertEqual(run.transcripts_collected, 2)

    def test_resume_refuses_to_mutate_a_human_reviewed_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _result, _candidates, _reviews, _manifest = self._collect(root, count=1)
            run = self.db.query(DatasetCollectionRun).one()
            pending = list_youtube_cc_review_queue(self.db)["items"][0]
            review_youtube_cc_candidate(
                self.db,
                collection_run_id=run.collection_run_id,
                source_youtube_id=pending["source_youtube_id"],
                decision="approve",
                reviewer="admin@example.test [user:1]",
                reviewed_leaf_key="phone",
                transcript_quality="good",
                review_root=root / "events",
            )
            with self.assertRaisesRegex(YouTubeCCDatasetError, "immutable"):
                resume_youtube_cc_collection(
                    self.db,
                    collection_run_id=run.collection_run_id,
                    api_key="test-key",
                    transcript_fetcher=_transcript,
                    youtube_getter=lambda *_args, **_kwargs: {},
                )

    def test_resume_refuses_legacy_five_minute_source_filter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._collect(Path(temp_dir), count=1)
            run = self.db.query(DatasetCollectionRun).one()
            config = json.loads(run.query_config_json)
            config.pop("source_video_duration_policy")
            run.query_config_json = json.dumps(config)
            original_status = run.status
            self.db.commit()

            with self.assertRaisesRegex(YouTubeCCDatasetError, "legacy five-minute"):
                resume_youtube_cc_collection(
                    self.db,
                    collection_run_id=run.collection_run_id,
                    api_key="test-key",
                    transcript_fetcher=_transcript,
                    youtube_getter=lambda *_args, **_kwargs: self.fail(
                        "legacy resume must not call YouTube"
                    ),
                )

            self.db.refresh(run)
            self.assertEqual(run.status, original_status)
            self.assertEqual(run.resume_count, 0)

    def test_import_requires_explicit_human_review_and_audits_rejection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _result, candidates, reviews, _manifest = self._collect(Path(temp_dir))
            pending = import_reviewed_youtube_cc_dataset(
                self.db,
                candidate_path=candidates,
                review_path=reviews,
            )
            self.assertEqual(pending["pending"], 3)
            self.assertEqual(self.db.query(DatasetContent).count(), 0)
            self.assertEqual(self.db.query(DatasetCollectionRun).one().status, "review_pending")

            self._fill_review(reviews, ["approve", "reject", ""])
            imported = import_reviewed_youtube_cc_dataset(
                self.db,
                candidate_path=candidates,
                review_path=reviews,
            )

        self.assertEqual(imported["approved"], 1)
        self.assertEqual(imported["rejected"], 1)
        self.assertEqual(imported["pending"], 1)
        self.assertEqual(self.db.query(DatasetCollectionRun).one().status, "partially_reviewed")
        self.assertEqual(self.db.query(DatasetContent).count(), 1)
        self.assertEqual(self.db.query(DatasetReviewEvent).count(), 2)
        row = self.db.query(DatasetContent).one()
        self.assertEqual(row.dataset_source, "youtube_public_research")
        self.assertEqual(row.taxonomy_version, TAXONOMY_VERSION)
        self.assertEqual(row.verification_status, "human_verified")
        self.assertEqual(row.label_source, "human_review")
        self.assertTrue(row.is_training_eligible)
        self.assertEqual(row.is_keyword_recommendation_eligible, row.data_split == "train")
        self.assertEqual(row.is_duration_recommendation_eligible, row.data_split == "train")
        self.assertEqual(production_transcript_query(self.db).count(), 1)

    def test_import_is_atomic_when_any_review_is_invalid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _result, candidates, reviews, _manifest = self._collect(Path(temp_dir), count=2)
            self._fill_review(reviews, ["approve", "approve"])
            with reviews.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[1]["reviewer"] = ""
            with reviews.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(YouTubeCCDatasetError, "no rows were committed"):
                import_reviewed_youtube_cc_dataset(
                    self.db,
                    candidate_path=candidates,
                    review_path=reviews,
                )
        self.assertEqual(self.db.query(DatasetContent).count(), 0)
        self.assertEqual(self.db.query(DatasetReviewEvent).count(), 0)

    def test_admin_review_queue_approves_and_rejects_without_editing_csv(self):
        self.db.autoflush = False
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _result, _candidates, _reviews, _manifest = self._collect(root, count=2)
            run = self.db.query(DatasetCollectionRun).one()

            pending = list_youtube_cc_review_queue(self.db)
            self.assertEqual(pending["summary"]["pending"], 2)
            self.assertEqual(pending["items"][0]["review_status"], "pending")

            first = pending["items"][0]
            approved = review_youtube_cc_candidate(
                self.db,
                collection_run_id=run.collection_run_id,
                source_youtube_id=first["source_youtube_id"],
                decision="approve",
                reviewer="admin@example.test [user:1]",
                reviewed_leaf_key="phone",
                transcript_quality="good",
                notes="Video and transcript checked.",
                review_root=root / "events",
            )
            self.assertEqual(approved["decision"], "approve")
            self.assertEqual(approved["run_status"], "partially_reviewed")
            self.assertIsNotNone(approved["dataset_id"])

            remaining = list_youtube_cc_review_queue(self.db)
            self.assertEqual(remaining["summary"]["pending"], 1)
            second = remaining["items"][0]
            rejected = review_youtube_cc_candidate(
                self.db,
                collection_run_id=run.collection_run_id,
                source_youtube_id=second["source_youtube_id"],
                decision="reject",
                reviewer="admin@example.test [user:1]",
                notes="Transcript does not match the target category.",
                review_root=root / "events",
            )

            self.assertEqual(rejected["decision"], "reject")
            self.assertEqual(rejected["run_status"], "reviewed")
            self.assertEqual(self.db.query(DatasetContent).count(), 1)
            self.assertEqual(self.db.query(DatasetReviewEvent).count(), 2)
            approved_queue = list_youtube_cc_review_queue(
                self.db, review_status="approved"
            )
            self.assertEqual(approved_queue["total"], 1)
            self.assertEqual(approved_queue["items"][0]["reviewed_leaf_key"], "phone")

    def test_admin_can_approve_out_of_scope_as_evaluation_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._collect(root, count=1)
            run = self.db.query(DatasetCollectionRun).one()
            candidate = list_youtube_cc_review_queue(self.db)["items"][0]

            reviewed = review_youtube_cc_candidate(
                self.db,
                collection_run_id=run.collection_run_id,
                source_youtube_id=candidate["source_youtube_id"],
                decision="approve",
                reviewer="admin@example.test [user:1]",
                reviewed_leaf_key=UNKNOWN_LEAF_KEY,
                transcript_quality="good",
                notes="Accessory content is outside the supported taxonomy.",
                review_root=root / "events",
            )

        row = self.db.query(DatasetContent).one()
        self.assertEqual(reviewed["decision"], "approve")
        self.assertEqual(row.taxonomy_leaf_key, UNKNOWN_LEAF_KEY)
        self.assertFalse(row.is_training_eligible)
        self.assertFalse(row.is_keyword_recommendation_eligible)
        self.assertFalse(row.is_duration_recommendation_eligible)
        self.assertEqual(production_transcript_query(self.db).count(), 0)
        self.assertEqual(out_of_scope_evaluation_query(self.db).count(), 1)

    def test_eligibility_rejects_source_verified_or_unreviewed_rows(self):
        values = {
            "is_training_eligible": True,
            "dataset_source": "youtube_cc",
            "verification_status": "source_verified",
            "label_source": "search_query",
        }
        with self.assertRaisesRegex(ValueError, "human_verified"):
            validate_training_eligibility_values(values)

    def test_migration_adds_youtube_cc_columns_and_disables_old_sources(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE dataset_collection_runs ("
                    "collection_run_id INTEGER PRIMARY KEY)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE dataset_contents ("
                    "dataset_id INTEGER PRIMARY KEY, source_platform VARCHAR(50), "
                    "dataset_source VARCHAR(100), is_active BOOLEAN, "
                    "is_training_eligible BOOLEAN)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO dataset_contents VALUES "
                    "(1, 'youtube', 'mmsum', 1, 1), "
                    "(2, 'youtube_seed', 'demo_seed', 1, 1)"
                )
            )
        result = migrate_youtube_cc_dataset_schema(engine)
        columns = {item["name"] for item in inspect(engine).get_columns("dataset_contents")}
        run_columns = {
            item["name"]
            for item in inspect(engine).get_columns("dataset_collection_runs")
        }
        with engine.connect() as connection:
            active = connection.execute(
                text("SELECT SUM(is_active), SUM(is_training_eligible) FROM dataset_contents")
            ).one()
        self.assertIn("transcript_source", columns)
        self.assertIn("reviewed_by", columns)
        self.assertIn("collection_strategy", columns)
        self.assertIn("average_views_per_day", columns)
        self.assertIn("review_artifact_path", run_columns)
        self.assertIn("resume_count", run_columns)
        self.assertEqual(result["legacy_rows_deactivated"], 2)
        self.assertEqual(tuple(active), (0, 0))
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
