"""Tests for embedding-space centroids, isolated from model downloads."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from app.services.embedding_centroid import _chunks, _document_vectors, compare_text_centroids, POLICY
from app.schemas.performance_clustering import ContentSimilarity
from app.services.performance_clustering import cluster_and_compare
from tests.test_performance_clustering import HIGH, LOW, sample_records


class CharacterTokenizer:
    is_fast = True

    def num_special_tokens_to_add(self, pair=False):
        return 2

    def __call__(self, text, **kwargs):
        return {"input_ids": list(text),
                "offset_mapping": [(i, i + 1) for i in range(len(text))]}


class FakeEncoder:
    tokenizer = CharacterTokenizer()
    max_seq_length = 128

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
    def test_full_text_is_covered_without_sampling_or_truncation(self):
        text = ("camera " * 300 + "battery " * 300).strip()
        chunks, weights = _chunks(text, FakeEncoder())
        self.assertGreater(len(chunks), 12)
        self.assertEqual("".join(chunks), text)
        self.assertEqual(sum(weights), len(text))
        self.assertTrue(all(0 < size <= 126 for size in weights))
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
        self.assertEqual(high["content_similarity"]["evidence_strength"], "descriptive_not_prediction")
        self.assertEqual(len(high["reference_videos"]), 10)
        self.assertEqual(high["content_similarity"]["k_used"], 0)
        self.assertGreater(high["content_similarity"]["high_score"],
                           high["content_similarity"]["low_score"])
        self.assertLess(high["content_similarity"]["high_distance"],
                        high["content_similarity"]["low_distance"])
        self.assertTrue(high["content_similarity"]["coverage"]["all_text_processed"])
        ContentSimilarity.model_validate(high["content_similarity"])

    def test_tied_text_centroids_abstain_without_faking_confidence(self):
        rows = [{"dataset_id": 1, "transcript": "camera battery"},
                {"dataset_id": 2, "transcript": "camera battery"}]
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

    def test_legacy_tfidf_is_explicitly_available(self):
        legacy = cluster_and_compare(sample_records(), user_transcript=HIGH * 2,
                                     category="camera", minimum_views=25000,
                                     comparison_method="tfidf")
        self.assertEqual(legacy["content_similarity"]["method"], "tfidf_cosine_similarity")

    def test_negative_cosine_preserved_and_distance_can_exceed_one(self):
        class SignedEncoder(FakeEncoder):
            def encode(self, texts, **kwargs):
                return [[-1, 0] if t == "opposite" else [1, 0] for t in texts]
        rows = [{"dataset_id": 1, "transcript": "opposite"},
                {"dataset_id": 2, "transcript": "matching"}]
        result = compare_text_centroids(rows, ["low", "high"], "matching",
                                        encoder=SignedEncoder())
        self.assertEqual(result["low_score"], -1)
        self.assertEqual(result["low_distance"], 2)
        self.assertEqual(result["high_distance"], 0)
        self.assertEqual(result["closest_group"], "high")
        ContentSimilarity.model_validate(result)

    def test_document_pooling_is_token_weighted_and_each_clip_counts_once(self):
        class PoolEncoder(FakeEncoder):
            max_seq_length = 6
            def encode(self, texts, **kwargs):
                return [[1, 0] if t.startswith("a") else [0, 1] for t in texts]
        vectors, coverage = _document_vectors(["aaaaBB", "aaaa", "B"], PoolEncoder())
        np.testing.assert_allclose(vectors[0], np.array([4, 2]) / np.sqrt(20))
        self.assertEqual(coverage[0], {"chunk_count": 2, "token_count": 6})
        result = compare_text_centroids([
            {"dataset_id": 1, "transcript": "a" * 80},
            {"dataset_id": 2, "transcript": "B"},
            {"dataset_id": 3, "transcript": "a"}],
            ["low", "low", "high"], "a", encoder=PoolEncoder())
        self.assertAlmostEqual(result["low_score"], 1 / np.sqrt(2))

    def test_near_tie_abstains_and_invalid_vectors_fail_closed(self):
        class CloseEncoder(FakeEncoder):
            def encode(self, texts, **kwargs):
                return [[1, 0] if t == "low" else [0.999, 0.04] for t in texts]
        rows = [{"dataset_id": 1, "transcript": "low"},
                {"dataset_id": 2, "transcript": "high"}]
        result = compare_text_centroids(rows, ["low", "high"], "high", encoder=CloseEncoder())
        self.assertEqual(result["reason"], "overlapping_text_centroids")
        self.assertIsNone(result["closest_group"])
        class BrokenEncoder(FakeEncoder):
            def encode(self, texts, **kwargs):
                return [[float("nan"), 0] for _ in texts]
        result = compare_text_centroids(rows, ["low", "high"], "high", encoder=BrokenEncoder())
        self.assertEqual(result["reason"], "embedding_unavailable")
        self.assertIsNone(result["high_distance"])

    def test_default_is_text_centroid_and_policy_has_no_legacy_top_k(self):
        with patch("app.services.embedding_centroid._load_encoder", return_value=FakeEncoder()):
            result = cluster_and_compare(sample_records(), user_transcript=HIGH, category="camera")
        self.assertEqual(result["content_similarity"]["method"], "sentence_embedding_text_centroid_cosine")
        self.assertNotIn("top_k", result["policy"])
        self.assertIn("embedding", result["policy"])

    def test_reference_cache_invalidates_on_text_or_policy_and_never_caches_user(self):
        class CacheEncoder(FakeEncoder):
            def __init__(self):
                self.calls = []
            def encode(self, texts, **kwargs):
                self.calls.append(len(texts))
                return np.pad(super().encode(texts), ((0, 0), (0, 382)))
        model = CacheEncoder()
        with TemporaryDirectory() as directory, \
                patch("app.services.embedding_centroid.CACHE", Path(directory)):
            texts = ["camera", "battery", "camera"]
            original, _ = _document_vectors(texts, model, cache_references=True)
            cached, _ = _document_vectors(texts, model, cache_references=True)
            np.testing.assert_allclose(cached, original)
            self.assertEqual(model.calls, [3, 1])
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 2)
            _document_vectors(["camera lens", "battery", "camera"], model, cache_references=True)
            self.assertEqual(model.calls[-1], 2)
            with patch.dict(POLICY, {"version": "test-new-policy"}):
                _document_vectors(texts, model, cache_references=True)
            self.assertEqual(model.calls[-1], 3)


if __name__ == "__main__":
    unittest.main()
