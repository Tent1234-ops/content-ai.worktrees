from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from pythainlp.tokenize import word_tokenize
from pythainlp.corpus.common import thai_stopwords
import numpy as np
import re

print("Loading Semantic Keyword Extractor V12...", flush=True)

model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
thai_stop = set(thai_stopwords())

# =========================
# normalize
# =========================
def normalize_text(text):
    text = text.lower()

    corrections = {
        "fixie": "rgb",
        "ppt": "pbt",
        "mcnical": "mechanical",
        "mechanial": "mechanical",
    }

    for k, v in corrections.items():
        text = text.replace(k, v)

    text = re.sub(r"[^ก-๙a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()

# =========================
# candidate keywords (fallback)
# =========================
def extract_candidates(text):
    tokens = word_tokenize(text, engine="newmm")

    tokens = [
        t for t in tokens
        if t not in thai_stop
        and len(t) > 2
        and not t.isnumeric()
    ]

    bigrams = [
        tokens[i] + " " + tokens[i+1]
        for i in range(len(tokens)-1)
    ]

    return list(set(tokens + bigrams))

# =========================
# semantic ranking (core)
# =========================
def semantic_keywords(text, keywords=None, top_k=10):
    try:
        text = normalize_text(text)

        # 🔥 ถ้าไม่มี keyword → generate candidate เอง
        if not keywords or len(keywords) == 0:
            candidates = extract_candidates(text)
        else:
            candidates = keywords

        # 🔥 กัน empty
        if len(candidates) == 0:
            return []

        # 🔥 ensure top_k
        if top_k is None:
            top_k = len(candidates)

        top_k = max(1, int(top_k))

        # =========================
        # Embedding
        # =========================
        text_emb = model.encode([text])
        cand_emb = model.encode(candidates)

        # =========================
        # Similarity
        # =========================
        sims = cosine_similarity(text_emb, cand_emb)[0]

        # =========================
        # Score + Boost
        # =========================
        scored = []

        for kw, score in zip(candidates, sims):

            boost = 0

            # 🔥 model name เช่น ak820
            if re.search(r"[a-z]+\d{2,5}", kw):
                boost += 0.25

            # 🔥 phrase สำคัญกว่า
            if len(kw.split()) > 1:
                boost += 0.1

            # 🔥 keyword สั้นเกิน = ลดคะแนน
            if len(kw) <= 3:
                boost -= 0.1

            scored.append((kw, float(score + boost)))

        # =========================
        # Sort
        # =========================
        scored = sorted(scored, key=lambda x: x[1], reverse=True)

        # =========================
        # Filter garbage (สำคัญมาก)
        # =========================
        final = []
        seen = set()

        for kw, score in scored:

            # ❌ ตัด phrase มั่ว
            if len(kw.split()) > 3:
                continue

            # ❌ ตัด stopword ซ้ำ
            if kw in thai_stop:
                continue

            base = kw.strip()

            if base not in seen:
                final.append((base, score))
                seen.add(base)

        # =========================
        # Return top_k
        # =========================
        return [k for k, _ in final[:top_k]]

    except Exception as e:
        print("Semantic keyword error:", e)
        return keywords[:10] if keywords else []