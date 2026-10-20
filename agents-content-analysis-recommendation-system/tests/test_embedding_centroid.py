"""Tests for embedding-space centroids, isolated from model downloads."""
import unittest
from unittest.mock import patch

import numpy as np

from app.services.embedding_centroid import _chunks, compare_text_centroids
from app.services.performance_clustering import cluster_and_compare
from tests.test_performance_clustering import HIGH, LOW, sample_records


class FakeEncoder:
    def encode(self, sentences, **kwargs):
        result = []
        for text in sentences:
            # Semantic stand-in: dimension 0 represents camera vocabulary,
            # dimension 1 represents battery vocabulary.
            camera = "camera" in text or "lens" in text
            battery = "battery" in text or "charging" in text
            if camera and battery:
                result.append([1.0, 1.0])
            elif camera:
                result.append([1.0, 0.0])
            elif battery:
                result.append([0.0, 1.0])
            else:
                result.append([0.5, 0.5])
        return np.asarray(result, dtype=float)


class TextCentroidTests(unittest.TestCase):
    def test_chunk_sampling_covers_end_of_long_text(self):
        chunks = _chunks("camera " * 300 + "battery " * 300)
        self.assertLessEqual(len(chunks), 12)
        self.assertIn("camera", chunks[0])
        self.assertIn("battery", chunks[-1])

    def test_kpi_clusters_stay_fixed_but_new_video_is_assigned_by_text(self):
        rows = sample_records()
        with patch("app.services.embedding_centroid._load_encoder", return_value=FakeEncoder()):
            high = cluster_and_compare(rows, user_transcript=HIGH * 2,
                category="camera", minimum_views=25000,
                comparison_method="embedding_centroid")
            low = cluster_and_compare(rows, user_transcript=LOW * 2,
                category="camera", minimum_views=25000,
                comparison_method="embedding_centroid")
        self.assertEqual(high["clustering"], low["clustering"])
        self.assertEqual(high["content_similarity"]["closest_group"], "high")
        self.assertEqual(low["content_similarity"]["closest_group"], "low")
        self.assertEqual(high["content_similarity"]["method"],
                         "sentence_embedding_text_centroid_cosine")
        self.assertEqual(high["content_similarity"]["evidence_strength"], "not_validated")
        self.assertEqual(len(high["reference_videos"]), 10)
        self.assertEqual(high["content_similarity"]["k_used"], 0)
        self.assertGreater(high["content_similarity"]["high_score"],
                           high["content_similarity"]["low_score"])

    def test_tied_text_centroids_abstain_without_faking_confidence(self):
        rows = [{"dataset_id": 1, "transcript": HIGH * 3},
                {"dataset_id": 2, "transcript": LOW * 3}]
        result = compare_text_centroids(rows, ["high", "low"], HIGH + LOW,
                                        encoder=FakeEncoder())
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["reason"], "text_centroid_tie")
        self.assertIsNone(result["closest_group"])

    def test_model_failure_is_nonfatal_and_not_mislabeled_as_low(self):
        with patch("app.services.embedding_centroid._load_encoder",
                   side_effect=OSError("No cached weights")):
            response = cluster_and_compare(sample_records(), user_transcript=HIGH * 2,
                category="camera", minimum_views=25000,
                comparison_method="embedding_centroid")
        self.assertEqual(response["clustering"]["status"], "ready")
        self.assertEqual(response["content_similarity"]["reason"], "embedding_unavailable")
        self.assertIsNone(response["content_similarity"]["closest_group"])

    def test_legacy_tfidf_remains_default(self):
        legacy = cluster_and_compare(sample_records(), user_transcript=HIGH * 2,
                                     category="camera", minimum_views=25000)
        self.assertEqual(legacy["content_similarity"]["method"], "tfidf_cosine_similarity")


if __name__ == "__main__":
    unittest.main()
