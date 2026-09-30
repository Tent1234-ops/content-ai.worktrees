import subprocess
import unittest
from unittest.mock import patch

from app.services.media_validation import (
    MediaValidationError,
    validate_user_upload_duration,
)


class MediaValidationTests(unittest.TestCase):
    @staticmethod
    def _probe_result(duration: str, *, returncode: int = 0):
        return subprocess.CompletedProcess(
            args=["ffprobe"],
            returncode=returncode,
            stdout=duration,
            stderr="invalid media" if returncode else "",
        )

    @patch("app.services.media_validation.subprocess.run")
    def test_user_upload_accepts_exactly_five_minutes(self, run):
        run.return_value = self._probe_result("300.000000\n")
        self.assertEqual(validate_user_upload_duration("clip.mp4"), 300.0)

    @patch("app.services.media_validation.subprocess.run")
    def test_user_upload_rejects_video_over_five_minutes(self, run):
        run.return_value = self._probe_result("301.250000\n")
        with self.assertRaisesRegex(MediaValidationError, "maximum video duration"):
            validate_user_upload_duration("clip.mp4")

    @patch("app.services.media_validation.subprocess.run")
    def test_user_upload_rejects_unreadable_media(self, run):
        run.return_value = self._probe_result("", returncode=1)
        with self.assertRaisesRegex(MediaValidationError, "Could not read"):
            validate_user_upload_duration("broken.mp4")


if __name__ == "__main__":
    unittest.main()
