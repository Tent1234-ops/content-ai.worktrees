"""Evidence-first title topics. Proposals are never automatic catalog approvals."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from pythainlp.corpus.common import thai_stopwords, thai_words
from pythainlp.tokenize import word_tokenize
from pythainlp.util import dict_trie
from sklearn.feature_extraction.text import CountVectorizer, ENGLISH_STOP_WORDS

EXTRACTOR_VERSION = "title-topics-hybrid-v1"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "data" / "trend_topics" / "catalog.v1.json"
GENERIC = frozenset("""review reviews video videos today new latest official full live shorts short
    clip clips youtube tiktok fyp viral trending trend subscribe like comment comments share
    noads ads ad unboxing unbox reaction ep episode part feat ft mv hd 4k highlight highlights
    best amazing watch shocking wow believe happened happens secret must know thing things
    toy toys collection funny fun challenge
    รีวิว คลิป วิดีโอ วันนี้ ล่าสุด ใหม่ ช่อง ฝาก กด ติดตาม ไลก์ คอมเมนต์ แชร์ มาแรง
    เทรนด์ กระแส ไวรัล ห้ามพลาด เปิดกล่อง แกะกล่อง ไม่คิด เจอ สิ่ง สิ่งนี้ เรื่องนี้
    ที่สุด สุด อะไร ยังไง ทำไม บอกเลย เต็ม อัปเดต แนะนำ ทดลอง ลอง สรุป เล่น แกะ เปิด กล่อง""".split())
PHRASE_BREAKS = frozenset("กับ และ หรือ เทียบ ปะทะ เล่น รีวิว ลอง แนะนำ แกะกล่อง เปิดกล่อง vs versus review unboxing".split())
CALENDAR_WORDS = frozenset("""january february march april may june july august september october november december
    jan feb mar apr jun jul aug sep sept oct nov dec monday tuesday wednesday thursday friday saturday sunday
    มกราคม กุมภาพันธ์ มีนาคม เมษายน พฤษภาคม มิถุนายน กรกฎาคม สิงหาคม กันยายน ตุลาคม พฤศจิกายน ธันวาคม
    จันทร์ อังคาร พุธ พฤหัสบดี ศุกร์ เสาร์ อาทิตย์ วันที่ วัน ปี เวลา พ ศ ค ศ""".split())


def normalized_phrase(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    ids, aliases = set(), {}
    for topic in catalog["topics"]:
        if not topic.get("id") or topic["id"] in ids or not topic.get("label"):
            raise ValueError("Catalog topic IDs must be unique and have labels")
        ids.add(topic["id"])
        if not topic.get("aliases"):
            raise ValueError("Every known topic needs explicit aliases")
        for alias in topic["aliases"]:
            key = normalized_phrase(alias["text"])
            if not key or (key in aliases and aliases[key] != topic["id"]):
                raise ValueError("Ambiguous catalog alias; resolve it before extraction")
            aliases[key] = topic["id"]
    for pair in catalog.get("never_merge", []):
        if len(pair) != 2 or not set(pair) <= ids:
            raise ValueError("Invalid never-merge pair")
    return catalog


def _matches(text: str, phrase: str):
    pattern = re.escape(phrase).replace(r"\ ", r"\s+")
    # ASCII boundaries prevent matching e.g. squishy inside unsquishy.
    if phrase[0].isascii() and phrase[0].isalnum():
        pattern = r"(?<![A-Za-z0-9_])" + pattern
    if phrase[-1].isascii() and phrase[-1].isalnum():
        pattern += r"(?![A-Za-z0-9_])"
    return re.finditer(pattern, text, flags=re.IGNORECASE)


def _has_context(text: str, phrases: list[str]) -> bool:
    return any(next(_matches(text, phrase), None) is not None for phrase in phrases)


def evidence_span(title: str, start: int, end: int) -> dict:
    return {"field": "title", "start": start, "end": end, "text": title[start:end]}


class TitleTopicExtractor:
    def __init__(self, catalog: dict | None = None):
        self.catalog = catalog if catalog is not None else load_catalog()
        self.aliases = {normalized_phrase(a["text"]) for t in self.catalog["topics"] for a in t["aliases"]}
        self.stopwords = set(thai_stopwords()) | set(ENGLISH_STOP_WORDS) | set(GENERIC)
        self.dictionary = dict_trie(set(thai_words()) | set(GENERIC) | {a["text"] for t in self.catalog["topics"] for a in t["aliases"]})

    def tokens(self, title: str) -> list[dict]:
        tokens = []
        for match in re.finditer(r"[\u0E00-\u0E7F]+|[A-Za-z0-9][A-Za-z0-9._+-]*|[^\W_]+", title):
            text = match.group()
            parts = word_tokenize(text, engine="newmm", custom_dict=self.dictionary, keep_whitespace=True) \
                if re.search(r"[\u0E00-\u0E7F]", text) else [text]
            offset = match.start()
            for part in parts:
                if not part:
                    continue
                if title[offset:offset+len(part)] != part:
                    raise ValueError("Tokenizer did not preserve original title offsets")
                tokens.append({"text": part, "start": offset, "end": offset+len(part)})
                offset += len(part)
        return tokens

    def known_topics(self, title: str) -> list[dict]:
        result = []
        for topic in self.catalog["topics"]:
            spans = []
            for alias in topic["aliases"]:
                for match in _matches(title, alias["text"]):
                    left, right = max(0, match.start()-80), min(len(title), match.end()+80)
                    context = [evidence_span(title, *m.span()) for phrase in alias.get("context_any", [])
                               for m in _matches(title, phrase) if left <= m.start() and m.end() <= right]
                    if alias.get("context_any") and not context:
                        continue
                    if alias.get("exclude_any") and _has_context(title[left:right], alias["exclude_any"]):
                        continue
                    spans.append(dict(evidence_span(title, *match.span()), alias=alias["text"], context_evidence=context))
            if spans:
                result.append({"topic_id": topic["id"], "label": topic["label"],
                               "method": "catalog_alias_with_context", "evidence": spans})
        return result

    def candidates(self, title: str) -> dict[str, dict]:
        tokens = self.tokens(title)
        result = {}

        def add(start, end, kind):
            phrase = title[start:end]
            key = normalized_phrase(phrase)
            words = [normalized_phrase(t["text"]) for t in tokens if start <= t["start"] and t["end"] <= end]
            letters = set(re.findall(r"[a-z\u0E00-\u0E7F]+", key))
            if letters and letters <= CALENDAR_WORDS:
                return
            if not words or key in self.aliases or key in self.stopwords or not 2 <= len(key) <= 80:
                return
            if words[0] in self.stopwords or words[-1] in self.stopwords:
                return
            if not any(any(c.isalpha() for c in word) and word not in self.stopwords for word in words):
                return
            if len(words) == 1 and key.isascii() and len(key) < 3:
                return
            if key not in result or kind == "hashtag":
                result[key] = dict(evidence_span(title, start, end), normalized=key, kind=kind)

        for match in re.finditer(r"(?<!\w)#([^\W_][\w]*)", title):
            add(*match.span(1), "hashtag")
        for i, first in enumerate(tokens):
            for last in tokens[i:i+5]:
                span_tokens = [t for t in tokens[i:i+5] if t["end"] <= last["end"]]
                if any(normalized_phrase(t["text"]) in PHRASE_BREAKS for t in span_tokens):
                    break
                if any(re.search(r"[^\s'-]", title[a["end"]:b["start"]]) for a, b in zip(span_tokens, span_tokens[1:])):
                    break
                add(first["start"], last["end"], "phrase" if len(span_tokens) > 1 else "word")
        return result


class LocalSemanticRanker:
    """Lazy, CPU/local-cache-only inference; never downloads during discovery."""
    def __init__(self, *, cache_dir: Path | None = None):
        from huggingface_hub import snapshot_download
        from sentence_transformers import SentenceTransformer
        from keybert import KeyBERT

        path = snapshot_download(MODEL_NAME, cache_dir=str(cache_dir or ROOT / "models_cache" / "sentence_transformers"),
                                 local_files_only=True)
        self.model = SentenceTransformer(path, device="cpu", local_files_only=True)
        self.keybert = KeyBERT(model=self.model)
        self.metadata = {"status": "ready", "model": MODEL_NAME, "revision": Path(path).name,
                         "device": "cpu", "network": "disabled", "ranker": "KeyBERT",
                         "max_sequence_tokens": self.model.max_seq_length,
                         "score_meaning": "semantic similarity, not confidence, popularity, or engagement"}

    def score(self, titles: list[str], vocabulary: list[str], present: list[set[str]]) -> list[dict]:
        if not vocabulary:
            return [{} for _ in titles]
        by_title = {title: terms for title, terms in zip(titles, present)}
        vectorizer = CountVectorizer(vocabulary=vocabulary, analyzer=lambda title: list(by_title.get(title, set())))
        document_embeddings = self.model.encode(titles, batch_size=32, show_progress_bar=False)
        word_embeddings = self.model.encode(vocabulary, batch_size=32, show_progress_bar=False)
        scores = self.keybert.extract_keywords(titles, vectorizer=vectorizer,
            doc_embeddings=document_embeddings, word_embeddings=word_embeddings, top_n=len(vocabulary))
        if len(titles) == 1:
            scores = [scores]
        return [dict(values) for values in scores]

    def similar_pairs(self, labels: list[str], threshold: float) -> list[tuple[int, int, float]]:
        if len(labels) < 2:
            return []
        embeddings = self.model.encode(labels, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        matrix = embeddings @ embeddings.T
        return [(i, j, float(matrix[i, j])) for i in range(len(labels)) for j in range(i+1, len(labels))
                if matrix[i, j] >= threshold]


def alias_suggestions(candidates: list[dict], catalog: dict, semantic, *, threshold=0.82) -> list[dict]:
    if semantic is None:
        return []
    entities = [{"id": row["candidate_id"], "label": row["label"], "type": "candidate"} for row in candidates[:100]]
    entities += [{"id": topic["id"], "label": topic["label"], "type": "known"} for topic in catalog["topics"]]
    prohibited = {frozenset(pair) for pair in catalog.get("never_merge", [])}
    result = []
    for i, j, similarity in semantic.similar_pairs([e["label"] for e in entities], threshold):
        a, b = entities[i], entities[j]
        if frozenset((a["id"], b["id"])) in prohibited or a["type"] == b["type"] == "known":
            continue
        left, right = normalized_phrase(a["label"]), normalized_phrase(b["label"])
        number_conflict = re.findall(r"\d+", left) != re.findall(r"\d+", right)
        variant_words = {"pro", "max", "ultra", "plus", "lite", "mini", "air"}
        left_words = {t.casefold() for t in re.findall(r"[A-Z][a-z]*|[a-z]+|\d+", a["label"])}
        right_words = {t.casefold() for t in re.findall(r"[A-Z][a-z]*|[a-z]+|\d+", b["label"])}
        variant_conflict = bool(re.search(r"\d", left+right) and
                                (left_words & variant_words) != (right_words & variant_words))
        lexical = SequenceMatcher(None, left, right).ratio()
        relation = "different_product_variant" if number_conflict or variant_conflict else "possible_alias" if lexical >= 0.65 else "related_only"
        result.append({"left": a, "right": b, "semantic_similarity": round(similarity, 4),
                       "relation": relation, "status": "needs_human_review", "automatically_merged": False})
    return sorted(result, key=lambda r: (-r["semantic_similarity"], r["left"]["id"], r["right"]["id"]))[:50]


def analyze_topic_titles(documents: list[dict], *, catalog: dict | None = None, semantic=None,
                         min_videos=3, min_channel_titles=2, min_similarity=0.30,
                         max_candidates=2000) -> dict:
    if min_videos < 2 or min_channel_titles < 1 or not -1 <= min_similarity <= 1 or not 1 <= max_candidates <= 2000:
        raise ValueError("Invalid topic proposal thresholds")
    extractor = TitleTopicExtractor(catalog)
    unique, seen_ids, seen_titles = [], set(), set()
    for doc in documents:
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", doc["video_id"]) or not doc["title"].strip():
            raise ValueError("Discovery requires a verified Video ID and a nonempty title")
        title_key = normalized_phrase(doc["title"])
        if doc["video_id"] in seen_ids or title_key in seen_titles:
            continue
        seen_ids.add(doc["video_id"])
        seen_titles.add(title_key)
        unique.append(doc)
    results, proposals = [], defaultdict(list)
    for doc in unique:
        title = doc["title"]
        known = extractor.known_topics(title)
        spans = extractor.candidates(title)
        index = len(results)
        results.append({"video_id": doc["video_id"], "title": title, "video_url": doc["video_url"],
                        "provenance": doc.get("provenance"), "known_topics": known, "candidate_ids": [],
                        "status": "matched_known" if known else "unknown", "input_fields": ["title"]})
        for key, span in spans.items():
            proposals[key].append({"index": index, "video_id": doc["video_id"], "title": title,
                "video_url": doc["video_url"], "channel_title": doc.get("channel_title"),
                "provenance": doc.get("provenance"), "evidence": span})
    supported = {key: rows for key, rows in proposals.items() if len(rows) >= min_videos and
                 len({normalized_phrase(row["channel_title"]) for row in rows if row["channel_title"]}) >= min_channel_titles}
    vocabulary = sorted(supported, key=lambda key: (-len(supported[key]), key))[:max_candidates]
    present = [set() for _ in results]
    for key in vocabulary:
        for row in supported[key]:
            present[row["index"]].add(key)
    scores = semantic.score([r["title"] for r in results], vocabulary, present) if semantic else [{} for _ in results]
    if len(scores) != len(results):
        raise ValueError("Semantic ranker returned mismatched document results")
    candidates = []
    for key in vocabulary:
        rows = supported[key]
        values = [float(scores[row["index"]][key]) for row in rows if key in scores[row["index"]]]
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Semantic ranker produced a non-finite similarity")
        score = sum(values)/len(values) if values else None
        if semantic and (score is None or score < min_similarity):
            continue
        label = Counter(row["evidence"]["text"] for row in rows).most_common(1)[0][0]
        candidate_id = "candidate-" + digest(key)[:16]
        evidence = [{k: v for k, v in row.items() if k != "index"} for row in rows]
        candidates.append({"candidate_id": candidate_id, "label": label, "normalized": key,
            "status": "needs_human_review", "distinct_videos": len(rows),
            "distinct_channel_titles": len({normalized_phrase(r["channel_title"]) for r in rows if r["channel_title"]}),
            "semantic_similarity": round(score, 4) if score is not None else None,
            "method": "KeyBERT_and_document_support" if semantic else "document_support_only",
            "evidence": evidence})
        for row in rows:
            result = results[row["index"]]
            result["candidate_ids"].append(candidate_id)
            if not result["known_topics"]:
                result["status"] = "needs_review"
    candidates.sort(key=lambda c: (-(c["semantic_similarity"] if c["semantic_similarity"] is not None else -1),
                                    -c["distinct_videos"], c["normalized"]))
    return {"extractor_version": EXTRACTOR_VERSION, "catalog_version": extractor.catalog["version"],
            "input_fields": ["title"], "documents": results, "candidates": candidates,
            "alias_suggestions": alias_suggestions(candidates, extractor.catalog, semantic),
            "summary": {"input_documents": len(documents), "unique_documents": len(results),
                "duplicate_documents_excluded": len(documents)-len(results),
                "statuses": dict(Counter(r["status"] for r in results)), "candidate_phrases": len(proposals),
                "supported_phrases": len(supported), "semantic_budget_excluded": max(0, len(supported)-max_candidates),
                "review_candidates": len(candidates)},
            "thresholds": {"min_videos": min_videos, "min_channel_titles": min_channel_titles,
                "min_semantic_similarity": min_similarity, "max_candidates": max_candidates},
            "limitations": ["Proposal support is across the input corpus, not a current trend score.",
                "Channel titles are proxies, not verified distinct channel IDs.",
                "Semantic similarity is not accuracy or probability that a topic is viral.",
                "Unknown means insufficient title evidence, not proof the video has no topic.",
                "New proposals and alias suggestions require human review; nothing is auto-approved."]}
