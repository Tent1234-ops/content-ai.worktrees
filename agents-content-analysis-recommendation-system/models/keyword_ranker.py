from sentence_transformers import SentenceTransformer, util

print("Loading Embedding Model (Keyword Ranker)...", flush=True)

model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')


def rank_keywords(text, keywords):
    if not keywords:
        return []

    text_emb = model.encode(text, convert_to_tensor=True)
    kw_emb = model.encode(keywords, convert_to_tensor=True)

    scores = util.cos_sim(text_emb, kw_emb)[0]

    ranked = sorted(
        zip(keywords, scores.cpu().numpy()),
        key=lambda x: x[1],
        reverse=True
    )

    # 🔥 return เป็น dict (สำคัญมาก)
    return [
        {"keyword": k, "score": float(s)}
        for k, s in ranked
    ]