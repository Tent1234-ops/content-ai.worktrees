from sentence_transformers import SentenceTransformer, util

print("Loading Embedding Model (Recommender)...")

model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')


def recommend_content(user_text, dataset_texts, top_k=3):
    user_emb = model.encode(user_text, convert_to_tensor=True)
    data_emb = model.encode(dataset_texts, convert_to_tensor=True)

    scores = util.cos_sim(user_emb, data_emb)[0]

    ranked = sorted(
        zip(dataset_texts, scores.cpu().numpy()),
        key=lambda x: x[1],
        reverse=True
    )

    return [
        {"text": t, "score": float(s)}
        for t, s in ranked[:top_k]
    ]