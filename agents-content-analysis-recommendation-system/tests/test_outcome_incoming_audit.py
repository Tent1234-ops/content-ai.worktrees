from datetime import datetime, timezone
import unittest

from scripts.audit_outcome_incoming_transcripts import (
    build_review, fetch_metadata, summarize, transcript_review,
)


class IncomingOutcomeAuditTests(unittest.TestCase):
    def test_missing_notice_not_accepted_as_speech(self):
        result = transcript_review("No usable captions found for YouTube video 'Example'.")
        self.assertTrue(result["missing_caption_notice"])
        self.assertFalse(result["fullness_confirmed"])
        self.assertFalse(result["language_review_required"])

    def test_long_text_does_not_prove_completeness(self):
        result = transcript_review("Example spoken content " * 1000)
        self.assertTrue(result["language_review_required"])
        self.assertTrue(result["fullness_review_required"])
        self.assertFalse(result["fullness_confirmed"])
        self.assertFalse(result["missing_caption_notice"])

    def test_requests_only_metadata_in_two_batches_for_67_ids(self):
        calls = []
        def getter(resource, **kwargs):
            calls.append((resource, kwargs))
            return {"items": [{"id": value} for value in kwargs["id"].split(",")] + [{"id": "unrequested"}]}
        result = fetch_metadata([f"id-{i}" for i in range(67)] + ["id-0"], api_key="fixture", getter=getter)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result), 67)
        for resource, kwargs in calls:
            self.assertEqual(resource, "videos")
            self.assertNotIn("statistics", kwargs["part"])
            self.assertNotIn("statistics", kwargs["fields"])
            self.assertLessEqual(len(kwargs["id"].split(",")), 50)

    def rows(self, *, owner_format=None, statement="", overlap=False, duplicate=False):
        entries = [{"path": "fixture.md", "leaf_key": "phone", "title": "Example",
                    "source_url": "https://www.youtube.com/watch?v=example", "transcript": "Example text"}]
        audits = [{"path": "fixture.md", "video_id": "example",
                   "status": "duplicate_video" if duplicate else "needs_metadata"}]
        metadata = {"example": {"snippet": {"publishedAt": "2026-10-05T12:00:00Z", "channelId": "channel"},
                                "contentDetails": {"duration": "PT1M"}}}
        return build_review(entries, audits, metadata,
                            {"channel": [{"dataset_id": 10, "split": "train"}]} if overlap else {},
                            checked_at=datetime(2026, 10, 12, 12, tzinfo=timezone.utc),
                            owner_format=owner_format, owner_format_statement=statement)

    def test_short_duration_and_watch_url_do_not_confirm_format(self):
        row = self.rows()[0]
        self.assertEqual(row["duration_seconds"], 60)
        self.assertEqual(row["confirmed_format"], "unknown")
        self.assertEqual(row["projected_age_context_not_statistics"], "age_7_30d")
        self.assertFalse(row["ready_for_outcome_holdout"])

    def test_owner_format_is_separate_from_fullness_and_sampling(self):
        row = self.rows(owner_format="long_form", statement="Owner confirms regular video")[0]
        self.assertEqual(row["format_evidence_type"], "owner_statement")
        self.assertEqual(row["confirmed_format"], "long_form")
        self.assertFalse(row["fullness_confirmed"])
        self.assertFalse(row["ready_for_outcome_holdout"])
        with self.assertRaises(ValueError):
            self.rows(owner_format="long_form")

    def test_old_channels_and_duplicate_videos_not_counted_as_new_independent(self):
        for rows in (self.rows(overlap=True), self.rows(duplicate=True)):
            result = summarize(rows)["phone"]
            self.assertEqual(result["no_existing_channel_overlap_and_new_video"], 0)
        self.assertEqual(summarize(self.rows())["phone"]["no_existing_channel_overlap_and_new_video"], 1)
        self.assertEqual(summarize(self.rows())["phone"]["ready_for_outcome_holdout"], 0)


if __name__ == "__main__":
    unittest.main()
