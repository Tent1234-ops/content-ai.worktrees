import subprocess
import unittest
from unittest.mock import patch

from app.services.pipeline.core import (
    analyze_video,
    extract_audio,
    segment_count_for_time_window,
    transcript_for_time_window,
)


class FullClipAnalysisTests(unittest.TestCase):
    @patch("app.services.pipeline.core.os.path.getsize", return_value=1024)
    @patch("app.services.pipeline.core.os.path.exists", return_value=True)
    @patch("app.services.pipeline.core.subprocess.run")
    def test_full_clip_audio_extraction_has_no_time_cutoff(
        self,
        run,
        _exists,
        _getsize,
    ):
        run.return_value = subprocess.CompletedProcess(
            args=["ffmpeg"],
            returncode=0,
        )

        self.assertTrue(extract_audio("clip.mp4", "clip.wav"))

        command = run.call_args.args[0]
        options = run.call_args.kwargs
        self.assertNotIn("-t", command)
        self.assertNotIn("timeout", options)

    def test_hook_transcript_uses_only_segments_starting_inside_window(self):
        segments = [
            {"start": 0.0, "end": 8.0, "text": "opening"},
            {"start": 52.5, "end": 61.0, "text": "hook detail"},
            {"start": 60.0, "end": 72.0, "text": "main content"},
            {"start": 180.0, "end": 190.0, "text": "conclusion"},
        ]

        self.assertEqual(
            transcript_for_time_window(segments, 60),
            "opening hook detail",
        )

    def test_hook_transcript_ignores_segments_without_timestamps(self):
        segments = [
            {"start": None, "text": "unknown time"},
            {"start": "invalid", "text": "invalid time"},
            {"start": 4.0, "text": "known time"},
        ]

        self.assertEqual(
            transcript_for_time_window(segments, 30),
            "known time",
        )
        self.assertEqual(segment_count_for_time_window(segments, 30), 1)

    @patch("models.speech_to_text.transcribe_with_meta")
    @patch("app.services.pipeline.core.extract_audio", return_value=True)
    def test_pipeline_keeps_full_transcript_and_slices_hook_by_timestamp(
        self,
        _extract_audio,
        transcribe,
    ):
        transcribe.return_value = {
            "text": "opening phone review camera battery conclusion",
            "language": "en",
            "language_probability": 0.99,
            "segment_count": 3,
            "avg_no_speech_prob": 0.01,
            "segments": [
                {
                    "start": 0.0,
                    "end": 15.0,
                    "text": "opening phone review",
                    "no_speech_prob": 0.01,
                },
                {
                    "start": 45.0,
                    "end": 58.0,
                    "text": "camera battery",
                    "no_speech_prob": 0.01,
                },
                {
                    "start": 90.0,
                    "end": 105.0,
                    "text": "conclusion",
                    "no_speech_prob": 0.01,
                },
            ],
        }

        result = analyze_video(
            "clip.mp4",
            display_name="clip.mp4",
            hook_duration_seconds=60,
            asr_model_size="small",
        )
        self.assertEqual(transcribe.call_args.kwargs["model_size"], "small")

        self.assertIn("conclusion", result["transcript"])
        self.assertEqual(result["raw_transcript"], result["transcript"])
        self.assertTrue(result["cleaned_transcript"])
        self.assertEqual(
            result["analysis"]["hook_transcript"],
            "opening phone review camera battery",
        )
        self.assertEqual(
            result["analysis"]["hook_raw_transcript"],
            "opening phone review camera battery",
        )
        self.assertEqual(
            result["analysis"]["stt_meta"]["transcript_scope"],
            "full_clip",
        )
        self.assertEqual(
            result["analysis"]["stt_meta"]["hook_segment_count"],
            2,
        )
        shorter_hook = analyze_video("clip.mp4", hook_duration_seconds=30, asr_model_size="base")
        self.assertEqual(transcribe.call_args.kwargs["model_size"], "base")
        self.assertEqual(shorter_hook["analysis"]["hook_transcript"], "opening phone review")
        self.assertIn("conclusion", shorter_hook["transcript"])

    @patch("models.speech_to_text.transcribe_with_meta", side_effect=RuntimeError("unavailable"))
    @patch("app.services.pipeline.core.extract_audio", return_value=True)
    def test_explicit_whisper_failure_does_not_silently_change_model(self, _extract, _transcribe):
        with self.assertRaisesRegex(RuntimeError, "Whisper base"):
            analyze_video("clip.mp4", asr_model_size="base")


if __name__ == "__main__":
    unittest.main()
