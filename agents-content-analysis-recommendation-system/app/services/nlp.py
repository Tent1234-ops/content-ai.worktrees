import re
import os
from collections import Counter
from typing import Dict, List

from app.services.pipeline.domain_rules import domain_phrase_lexicon
from app.services.pipeline.core import normalize_asr_terms, normalize_space
from utils.text_clean import clean_text

USE_PYTHAINLP = os.getenv("NLP_USE_PYTHAINLP", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PYTHAINLP_ENGINE = os.getenv("NLP_PYTHAINLP_ENGINE", "newmm").strip() or "newmm"

try:
    from pythainlp.corpus.common import thai_stopwords
    from pythainlp.tokenize import word_tokenize
except Exception:
    thai_stopwords = None
    word_tokenize = None


THAI_STOPWORDS = {
    "\u0e41\u0e25\u0e30",
    "\u0e02\u0e2d\u0e07",
    "\u0e17\u0e35\u0e48",
    "\u0e43\u0e19",
    "\u0e43\u0e2b\u0e49",
    "\u0e40\u0e1b\u0e47\u0e19",
    "\u0e01\u0e47",
    "\u0e04\u0e37\u0e2d",
    "\u0e41\u0e1a\u0e1a",
    "\u0e40\u0e25\u0e22",
    "\u0e21\u0e32\u0e01",
    "\u0e19\u0e30",
    "\u0e04\u0e23\u0e31\u0e1a",
    "\u0e04\u0e48\u0e30",
    "\u0e40\u0e19\u0e35\u0e48\u0e22",
    "\u0e15\u0e31\u0e27",
    "\u0e2d\u0e30\u0e44\u0e23",
    "\u0e16\u0e49\u0e32",
    "\u0e17\u0e35\u0e48\u0e08\u0e30",
    "\u0e44\u0e14\u0e49",
    "\u0e08\u0e32\u0e01",
    "\u0e41\u0e25\u0e49\u0e27",
    "\u0e0b\u0e36\u0e48\u0e07",
    "\u0e2a\u0e33\u0e2b\u0e23\u0e31\u0e1a",
}
if thai_stopwords is not None:
    THAI_STOPWORDS.update(str(word).strip().lower() for word in thai_stopwords())

EN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "with",
}

DOMAIN_PHRASES = domain_phrase_lexicon()

COMPARABLE_SYNONYMS_BY_DOMAIN = {
    "smartphone": {
        "camera quality": (
            "กล้อง",
            "ภาพ",
            "เซนเซอร์",
            "กล้องหน้า",
            "กล้องหลัง",
            "ถ่ายรูป",
            "ถ่ายภาพ",
            "เลนส์",
            "camera",
            "photo",
            "portrait",
            "night mode",
        ),
        "chip performance": (
            "ชิป",
            "snapdragon",
            "dimensity",
            "ชิปเซ็ต",
            "หน่วยประมวลผล",
            "ประมวลผล",
            "ประสิทธิภาพ",
            "chip",
            "chipset",
            "processor",
            "cpu",
            "mediatek",
            "exynos",
            "antutu",
        ),
        "battery life": (
            "แบตเตอรี่",
            "แบต",
            "ความอึด",
            "แบตอึด",
            "ใช้งานได้ทั้งวัน",
            "มิลลิแอมป์",
            "battery life",
            "battery",
            "mah",
        ),
        "display quality": (
            "จอ",
            "หน้าจอ",
            "amoled",
            "oled",
            "ความสว่าง",
            "ความละเอียด",
            "นิต",
            "display",
            "screen",
            "brightness",
            "refresh rate",
        ),
        "charging speed": (
            "fast charge",
            "fast charging",
            "charging",
            "watt",
            "ชาร์จไว",
            "ชาร์จเร็ว",
            "การชาร์จ",
            "วัตต์",
        ),
        "thermal control": (
            "ระบายความร้อน",
            "ความร้อน",
            "เครื่องร้อน",
            "อุณหภูมิ",
            "พัดลม",
            "ห้องไอ",
            "thermal",
            "heat",
            "cooling",
            "cooler",
            "vapor chamber",
            "throttle",
            "ร้อน",
        ),
        "stabilization": (
            "stabilization",
            "ois",
            "กันสั่น",
            "ระบบกันสั่น",
        ),
        "software support": (
            "software",
            "update",
            "android",
            "ios",
            "ซอฟต์แวร์",
            "อัปเดต",
            "ระบบปฏิบัติการ",
        ),
        "value for money": (
            "value",
            "budget",
            "price",
            "ราคา",
            "คุ้ม",
            "คุ้มค่า",
        ),
        "build quality": (
            "build quality",
            "material",
            "วัสดุ",
            "งานประกอบ",
            "แข็งแรง",
            "ทนทาน",
        ),
    },
}


def normalize_text_for_nlp(text: str) -> str:
    normalized = normalize_asr_terms(text or "")
    normalized = clean_text(normalized)
    return normalize_space(normalized)


def tokenize_text(text: str) -> List[str]:
    normalized = normalize_text_for_nlp(text)
    if (
        USE_PYTHAINLP
        and word_tokenize is not None
        and re.search(r"[\u0E00-\u0E7F]", normalized)
    ):
        raw_tokens = word_tokenize(
            normalized.lower(),
            engine=PYTHAINLP_ENGINE,
            keep_whitespace=False,
        )
        tokens: List[str] = []
        for raw_token in raw_tokens:
            tokens.extend(
                re.findall(
                    r"[\u0E00-\u0E7F]+|[a-z0-9][a-z0-9\-]*",
                    str(raw_token).strip().lower(),
                )
            )
        return tokens

    return re.findall(r"[\u0E00-\u0E7Fa-zA-Z0-9][\u0E00-\u0E7Fa-zA-Z0-9\-]*", normalized.lower())


def filter_tokens(tokens: List[str]) -> List[str]:
    filtered: List[str] = []
    for token in tokens:
        if len(token) <= 1:
            continue
        if token in EN_STOPWORDS or token in THAI_STOPWORDS:
            continue
        if token.isdigit():
            continue
        filtered.append(token)
    return filtered


def _evidence_count(normalized: str, tokens: List[str], term: str) -> int:
    normalized_term = normalize_text_for_nlp(term)
    if not normalized_term:
        return 0
    if re.fullmatch(r"[a-z0-9][a-z0-9\s\-]*", normalized_term):
        return len(
            re.findall(
                rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])",
                normalized,
            )
        )
    term_tokens = tokenize_text(normalized_term)
    if len(term_tokens) <= 1:
        return sum(1 for token in tokens if token == normalized_term)
    return normalized.count(normalized_term)


def extract_comparable_keyword_candidates(
    text: str,
    domain: str,
) -> List[Dict[str, object]]:
    """Map explicit transcript evidence to canonical comparison dimensions."""
    normalized = normalize_text_for_nlp(text)
    tokens = tokenize_text(normalized)
    domain_lexicon = COMPARABLE_SYNONYMS_BY_DOMAIN.get(domain, {})
    candidates: List[Dict[str, object]] = []

    for canonical_keyword, synonyms in domain_lexicon.items():
        matched_terms: List[str] = []
        frequency = 0
        for synonym in dict.fromkeys(synonyms):
            match_count = _evidence_count(normalized, tokens, synonym)
            if match_count <= 0:
                continue
            matched_terms.append(synonym)
            frequency += match_count
        if not matched_terms:
            continue
        score = min(5.0, 2.6 + (0.35 * frequency) + (0.15 * len(matched_terms)))
        candidates.append(
            {
                "keyword": canonical_keyword,
                "score": round(score, 3),
                "frequency": frequency,
                "matched_terms": matched_terms,
            }
        )

    candidates.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item["frequency"]),
            str(item["keyword"]),
        )
    )
    return candidates


def _dedupe_ranked_keywords(ranked: List[Dict[str, float]]) -> List[Dict[str, float]]:
    deduped: List[Dict[str, float]] = []
    selected_phrases: List[str] = []
    seen = set()

    for item in ranked:
        keyword = str(item["keyword"]).strip().lower()
        if not keyword or keyword in seen:
            continue

        is_single_token = " " not in keyword
        if is_single_token and float(item.get("score", 0.0)) <= 2.0 and any(
            keyword in phrase.split() for phrase in selected_phrases
        ):
            continue

        seen.add(keyword)
        deduped.append(item)
        if not is_single_token:
            selected_phrases.append(keyword)

    return deduped


def _count_phrase_matches(normalized: str, phrase: str) -> int:
    if re.fullmatch(r"[a-z0-9][a-z0-9\s\-]*", phrase):
        return len(re.findall(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", normalized))
    return normalized.count(phrase)


def extract_keyword_candidates(text: str) -> List[Dict[str, float]]:
    normalized = normalize_text_for_nlp(text)
    tokens = tokenize_text(normalized)
    filtered_tokens = filter_tokens(tokens)
    counts = Counter(filtered_tokens)
    candidates: Dict[str, float] = {}

    for phrase in DOMAIN_PHRASES:
        phrase_count = _count_phrase_matches(normalized, phrase)
        if phrase_count > 0:
            phrase_weight = 2.8 if len(phrase.split()) >= 2 else 1.8
            candidates[phrase] = round((phrase_count * phrase_weight) + (len(phrase.split()) * 0.35), 3)

    for token, freq in counts.items():
        score = float(freq)
        if len(token) >= 6:
            score += 0.2
        candidates[token] = max(candidates.get(token, 0.0), round(score, 3))

    bigrams = Counter(" ".join(pair) for pair in zip(filtered_tokens, filtered_tokens[1:]))
    for phrase, freq in bigrams.items():
        if freq < 2:
            continue
        if phrase in EN_STOPWORDS or phrase in THAI_STOPWORDS:
            continue
        candidates[phrase] = max(candidates.get(phrase, 0.0), round((freq * 1.8) + 0.3, 3))

    trigrams = Counter(" ".join(triple) for triple in zip(filtered_tokens, filtered_tokens[1:], filtered_tokens[2:]))
    for phrase, freq in trigrams.items():
        if freq < 2 and phrase not in DOMAIN_PHRASES:
            continue
        candidates[phrase] = max(candidates.get(phrase, 0.0), round((freq * 2.2) + 0.4, 3))

    ranked = [
        {"keyword": keyword, "score": score, "frequency": counts.get(keyword, normalized.count(keyword))}
        for keyword, score in candidates.items()
    ]
    ranked.sort(key=lambda item: (-item["score"], -item["frequency"], item["keyword"]))
    return _dedupe_ranked_keywords(ranked)


def summarize_feature_attributes(text: str) -> Dict[str, object]:
    normalized = normalize_text_for_nlp(text)
    tokens = tokenize_text(normalized)
    filtered_tokens = filter_tokens(tokens)
    token_counts = Counter(filtered_tokens)
    return {
        "character_count": len(normalized),
        "token_count": len(tokens),
        "filtered_token_count": len(filtered_tokens),
        "unique_token_count": len(token_counts),
        "top_terms": [{"term": term, "count": count} for term, count in token_counts.most_common(10)],
    }


def run_nlp_pipeline(text: str, max_keywords: int = 10) -> Dict[str, object]:
    normalized = normalize_text_for_nlp(text)
    tokens = tokenize_text(normalized)
    filtered_tokens = filter_tokens(tokens)
    candidates = extract_keyword_candidates(normalized)
    return {
        "normalized_text": normalized,
        "tokens": tokens,
        "filtered_tokens": filtered_tokens,
        "keyword_candidates": candidates[: max(max_keywords * 2, 10)],
        "top_keywords": candidates[:max_keywords],
        "feature_attributes": summarize_feature_attributes(normalized),
    }
