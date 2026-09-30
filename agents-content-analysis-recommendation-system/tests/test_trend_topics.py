import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from app.services.trend_topics import (
    TitleTopicExtractor, alias_suggestions, analyze_topic_titles, load_catalog,
)
from app.services.trend_topic_discovery import read_discovery_corpus
from app.services.trend_topic_preparation import (
    title_fingerprint, write_preparation_bundle, validate_preparation_bundle,
)


class FakeSemantic:
    metadata = {"status": "test_fake"}

    def score(self, titles, vocabulary, present):
        return [{key: 0.75 for key in words} for words in present]

    def similar_pairs(self, labels, threshold):
        return [(i, j, 0.95) for i in range(len(labels)) for j in range(i+1, len(labels))]


def document(number, title, channel=None):
    video_id = f"v{number:010d}"
    return {"video_id": video_id, "title": title, "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "channel_title": channel or f"Channel {number}", "description": "Must not become a topic",
            "provenance": {"run_id": number, "observed_at": "2026-09-25T09:00:00Z", "ranking_scope": "global"}}


class TitleTopicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor = TitleTopicExtractor()

    def test_known_thai_aliases_resolve_to_same_topic_with_exact_spans(self):
        for text in ("แกะกล่องสกุชชี้", "บีบสกุชชี่", "Squishy toy unboxing"):
            topics = self.extractor.known_topics(text)
            self.assertEqual([topic["topic_id"] for topic in topics], ["squishy"])
            for span in topics[0]["evidence"]:
                self.assertEqual(text[span["start"]:span["end"]], span["text"])

    def test_english_alias_needs_toy_context_and_whole_word(self):
        for title in ("A squishy cake recipe", "Squishy software problem", "unsquishy toy", "squishyness"):
            self.assertEqual(self.extractor.known_topics(title), [])

    def test_related_known_topics_are_not_merged_or_combined_into_a_phrase(self):
        title = "แกะกล่องสกุชชี้กับกล่องสุ่ม"
        self.assertEqual({t["topic_id"] for t in self.extractor.known_topics(title)}, {"squishy", "blind_box"})
        self.assertFalse(any("กับ" in phrase for phrase in self.extractor.candidates(title)))
        self.assertEqual(alias_suggestions([], load_catalog(), FakeSemantic()), [])

    def test_product_and_game_phrases_and_hashtags_preserve_offsets(self):
        title = "รีวิว Samsung Galaxy S26 Ultra เล่น Genshin Impact #Labubu"
        candidates = self.extractor.candidates(title)
        for term in ("samsung galaxy s26 ultra", "genshin impact", "labubu"):
            span = candidates[term]
            self.assertEqual(title[span["start"]:span["end"]], span["text"])
        self.assertEqual(candidates["labubu"]["kind"], "hashtag")
        self.assertFalse(any("เล่น" in phrase for phrase in candidates))

    def test_plain_dates_are_not_topics_but_named_events_with_years_survive(self):
        candidates = self.extractor.candidates("เอเชียนเกมส์ 2026 วันที่ 24 กันยายน 2569")
        self.assertNotIn("24 กันยายน 2569", candidates)
        self.assertNotIn("กันยายน", candidates)
        self.assertNotIn("กันยายน 2569", candidates)
        self.assertIn("เอเชียนเกมส์ 2026", candidates)

    def test_context_evidence_is_a_real_title_span(self):
        title = "A squishy toy unboxing"
        context = self.extractor.known_topics(title)[0]["evidence"][0]["context_evidence"]
        self.assertTrue(context)
        for span in context:
            self.assertEqual(title[span["start"]:span["end"]], span["text"])

    def test_vague_title_abstains_and_ignores_description(self):
        row = document(1, "ไม่คิดว่าจะเจอสิ่งนี้!")
        row["description"] = "Squishy toy unboxing"
        result = analyze_topic_titles([row], semantic=FakeSemantic())
        self.assertEqual(result["documents"][0]["status"], "unknown")
        self.assertEqual(result["documents"][0]["known_topics"], [])
        self.assertEqual(result["candidates"], [])

    def test_new_object_discovery_does_not_require_seed_dictionary(self):
        rows = [document(1, "Unboxing #Zorvani edition 1"), document(2, "Review #Zorvani edition 2"),
                document(3, "New #Zorvani edition 3")]
        catalog = load_catalog()
        before = copy.deepcopy(catalog)
        result = analyze_topic_titles(rows, catalog=catalog, semantic=FakeSemantic())
        candidate = next(c for c in result["candidates"] if c["normalized"] == "zorvani")
        self.assertEqual(candidate["distinct_videos"], 3)
        self.assertEqual(candidate["status"], "needs_human_review")
        self.assertEqual(candidate["semantic_similarity"], 0.75)
        self.assertEqual(catalog, before)
        self.assertEqual(len(candidate["evidence"]), 3)
        self.assertTrue(all(row["known_topics"] == [] for row in result["documents"]))

    def test_repeated_mentions_snapshots_and_copied_titles_do_not_inflate_support(self):
        row = document(1, "#Zorvani #Zorvani #Zorvani")
        result = analyze_topic_titles([row, row, document(2, row["title"])], semantic=FakeSemantic())
        self.assertEqual(result["summary"]["unique_documents"], 1)
        self.assertEqual(result["candidates"], [])

    def test_single_channel_or_unknown_channel_is_insufficient_support(self):
        rows = [document(n, f"#Zorvani edition {n}", channel="Same channel") for n in range(1, 4)]
        self.assertEqual(analyze_topic_titles(rows)["candidates"], [])
        for row in rows:
            row["channel_title"] = None
        self.assertEqual(analyze_topic_titles(rows)["candidates"], [])

    def test_semantic_off_never_fakes_a_similarity_score(self):
        rows = [document(n, f"#Zorvani edition {n}") for n in range(1, 4)]
        result = analyze_topic_titles(rows)
        self.assertTrue(result["candidates"])
        self.assertTrue(all(c["semantic_similarity"] is None for c in result["candidates"]))
        self.assertEqual(result["alias_suggestions"], [])

    def test_invalid_semantic_scores_are_rejected(self):
        class BrokenSemantic(FakeSemantic):
            def score(self, titles, vocabulary, present):
                return [{key: float('nan') for key in words} for words in present]
        rows = [document(n, f"#Zorvani edition {n}") for n in range(1, 4)]
        with self.assertRaisesRegex(ValueError, "non-finite"):
            analyze_topic_titles(rows, semantic=BrokenSemantic())

    def test_product_model_numbers_block_alias_merge(self):
        candidates = [{"candidate_id": "a", "label": "Galaxy S26 Ultra"},
                      {"candidate_id": "b", "label": "Galaxy S27 Ultra"}]
        rows = alias_suggestions(candidates, {"topics": [], "never_merge": []}, FakeSemantic())
        self.assertEqual(rows[0]["relation"], "different_product_variant")
        self.assertFalse(rows[0]["automatically_merged"])

    def test_pro_and_pro_max_are_not_assumed_same_product(self):
        candidates = [{"candidate_id": "a", "label": "iPhone 18 Pro"}, {"candidate_id": "b", "label": "iPhone 18 Pro Max"}]
        rows = alias_suggestions(candidates, {"topics": [], "never_merge": []}, FakeSemantic())
        self.assertEqual(rows[0]["relation"], "different_product_variant")

    def test_semantic_similarity_alone_is_only_related_not_an_alias(self):
        candidates = [{"candidate_id": "a", "label": "Squishy"}, {"candidate_id": "b", "label": "Blind box"}]
        rows = alias_suggestions(candidates, {"topics": [], "never_merge": []}, FakeSemantic())
        self.assertEqual(rows[0]["relation"], "related_only")
        self.assertFalse(rows[0]["automatically_merged"])

    def test_empty_corpus_has_no_invented_topics(self):
        result = analyze_topic_titles([], semantic=FakeSemantic())
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["candidates"], [])


class HoldoutDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bundle = Path(self.temp.name) / "bundle"
        candidates = []
        for n in range(1, 5):
            row = document(n, f"Frozen object {n}")
            row.update(category="Test category", title_variants=[title_fingerprint(row["title"])],
                title_sha256=hashlib.sha256(row["title"].encode()).hexdigest(),
                title_fingerprint=title_fingerprint(row["title"]))
            candidates.append(row)
        observations = [{"platform": "youtube", "run_id": 1, "observed_at": "2026-09-25T09:00:00Z", "ranking_scope": "global",
            "items": [{"video_id": c["video_id"], "title": c["title"], "title_valid": True, "rank_valid": True,
                "rank": i+1, "identity_source": "source_url", "channel_title": c["channel_title"]} for i, c in enumerate(candidates)]}]
        report = {"generated_at": "2026-09-25T09:00:00Z", "region": "TH", "requested_from": "2026-09-24T09:00:00Z",
            "requested_to": "2026-09-25T09:00:00Z", "candidate_videos": 4, "scopes": [], "limitations": []}
        write_preparation_bundle(self.bundle, report, candidates, observations, size=4, test_size=2)

    def tearDown(self):
        self.temp.cleanup()

    def test_discovery_excludes_test_video_ids_before_any_extraction(self):
        heldout = set(json.loads((self.bundle / "heldout_video_ids.json").read_text())["video_ids"])
        rows, report = read_discovery_corpus(self.bundle, source="discovery")
        self.assertEqual(len(rows), 2)
        self.assertFalse(heldout & {row["video_id"] for row in rows})
        self.assertEqual(report["heldout_ids_excluded"], 2)
        self.assertFalse(report["test_used_for_discovery"])
        self.assertEqual(report["label_status"], "awaiting_human_annotation")

    def test_development_does_not_change_human_labels_and_test_mode_is_rejected(self):
        before = (self.bundle / "development" / "labels.csv").read_bytes()
        rows, _ = read_discovery_corpus(self.bundle)
        analyze_topic_titles(rows)
        self.assertEqual(before, (self.bundle / "development" / "labels.csv").read_bytes())
        self.assertTrue(validate_preparation_bundle(self.bundle)["valid"])
        with self.assertRaises(ValueError):
            read_discovery_corpus(self.bundle, source="test")

    def test_changed_denylist_is_rejected_not_silently_bypassed(self):
        (self.bundle / "heldout_video_ids.json").write_text('{"video_ids": []}')
        with self.assertRaises(ValueError):
            read_discovery_corpus(self.bundle, source="discovery")

    def test_copy_of_a_test_title_with_another_video_id_is_excluded(self):
        heldout_row = json.loads((self.bundle / "test" / "samples.jsonl").read_text().splitlines()[0])
        source = self.bundle / "observations.jsonl"
        observation = json.loads(source.read_text())
        duplicate = dict(observation["items"][0], video_id="v9999999999", title=heldout_row["title"])
        observation["items"].append(duplicate)
        source.write_text(json.dumps(observation) + "\n", encoding="utf-8", newline="\n")
        manifest_file = self.bundle / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        manifest["files"]["observations.jsonl"] = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        rows, report = read_discovery_corpus(self.bundle, source="discovery")
        self.assertNotIn("v9999999999", {row["video_id"] for row in rows})
        self.assertEqual(report["heldout_title_copies_excluded"], 1)


if __name__ == "__main__":
    unittest.main()
