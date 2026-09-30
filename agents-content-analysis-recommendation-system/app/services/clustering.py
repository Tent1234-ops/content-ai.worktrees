from collections import Counter
from typing import Dict, List, Tuple

import numpy as np

from app.services.nlp import filter_tokens, normalize_text_for_nlp, tokenize_text
from app.services.pipeline.core import detect_domain

try:
    import hdbscan
except Exception:
    hdbscan = None


DOMAIN_LABELS = {
    "audio": "Audio Review",
    "smartphone": "Smartphone Review",
    "food_drink": "Food & Drink Review",
    "fashion": "Fashion Review",
    "keyboard": "Keyboard Review",
    "mouse": "Mouse Review",
    "skincare": "Skincare Review",
    "general": "General Trend",
}


def build_vocabulary(texts: List[str], max_features: int = 50) -> List[str]:
    corpus_counts: Counter[str] = Counter()
    for text in texts:
        tokens = filter_tokens(tokenize_text(normalize_text_for_nlp(text)))
        corpus_counts.update(tokens)
    return [term for term, _count in corpus_counts.most_common(max_features)]


def vectorize_texts(texts: List[str], vocabulary: List[str]) -> Tuple[np.ndarray, List[Counter[str]]]:
    vocab_index = {term: idx for idx, term in enumerate(vocabulary)}
    vectors = np.zeros((len(texts), len(vocabulary)), dtype=float)
    token_counters: List[Counter[str]] = []

    for row, text in enumerate(texts):
        tokens = filter_tokens(tokenize_text(normalize_text_for_nlp(text)))
        counts = Counter(tokens)
        token_counters.append(counts)
        total = sum(counts.values()) or 1
        for term, count in counts.items():
            col = vocab_index.get(term)
            if col is not None:
                vectors[row, col] = count / total
    return vectors, token_counters


def _initialize_centroids(vectors: np.ndarray, n_clusters: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if len(vectors) <= n_clusters:
        return vectors.copy()

    centroids = [vectors[rng.integers(0, len(vectors))]]
    while len(centroids) < n_clusters:
        distances = np.array([min(np.sum((vec - c) ** 2) for c in centroids) for vec in vectors])
        total = distances.sum()
        if total <= 0:
            centroids.append(vectors[rng.integers(0, len(vectors))])
            continue
        probabilities = distances / total
        next_index = rng.choice(len(vectors), p=probabilities)
        centroids.append(vectors[next_index])
    return np.array(centroids)


def _assign_clusters(vectors: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    distances = np.linalg.norm(vectors[:, np.newaxis, :] - centroids[np.newaxis, :, :], axis=2)
    return np.argmin(distances, axis=1)


def _recompute_centroids(vectors: np.ndarray, labels: np.ndarray, n_clusters: int) -> np.ndarray:
    centroids = np.zeros((n_clusters, vectors.shape[1]), dtype=float)
    for cluster_id in range(n_clusters):
        members = vectors[labels == cluster_id]
        if len(members) == 0:
            continue
        centroids[cluster_id] = members.mean(axis=0)
    return centroids


def _top_terms_from_centroid(centroid: np.ndarray, vocabulary: List[str], limit: int = 5) -> List[str]:
    pairs = [(vocabulary[idx], float(weight)) for idx, weight in enumerate(centroid) if weight > 0]
    pairs.sort(key=lambda item: (-item[1], item[0]))
    return [term for term, _weight in pairs[:limit]]


def infer_cluster_label(top_terms: List[str]) -> str:
    hint_text = " ".join(top_terms)
    domain = detect_domain(hint_text)
    domain_label = DOMAIN_LABELS.get(domain, "General Trend")
    focus = ", ".join(top_terms[:2]) if top_terms else "mixed topics"
    return f"{domain_label}: {focus}"


def _build_assignments(texts: List[str], labels: List[int], token_counters: List[Counter[str]]) -> List[Dict[str, object]]:
    assignments = []
    for index, (text, label) in enumerate(zip(texts, labels), start=1):
        top_terms = [term for term, _count in token_counters[index - 1].most_common(5)]
        assignments.append(
            {
                "item_id": index,
                "cluster_id": int(label),
                "text": text,
                "top_terms": top_terms,
            }
        )
    return assignments


def _build_clusters_from_labels(
    labels: List[int],
    vectors: np.ndarray,
    vocabulary: List[str],
) -> List[Dict[str, object]]:
    clusters = []
    for cluster_id in sorted(set(labels)):
        member_indexes = [idx for idx, label in enumerate(labels) if label == cluster_id]
        if not member_indexes:
            continue
        centroid = vectors[member_indexes].mean(axis=0)
        cluster_terms = _top_terms_from_centroid(centroid, vocabulary)
        label_name = "Noise / Outlier" if cluster_id == -1 else infer_cluster_label(cluster_terms)
        clusters.append(
            {
                "cluster_id": int(cluster_id),
                "label": label_name,
                "size": len(member_indexes),
                "top_terms": cluster_terms,
                "member_item_ids": [idx + 1 for idx in member_indexes],
            }
        )
    return clusters


def cluster_texts_kmeans(
    texts: List[str],
    n_clusters: int,
    max_features: int = 50,
    max_iterations: int = 25,
    seed: int = 42,
) -> Dict[str, object]:
    if len(texts) < n_clusters:
        raise ValueError("Number of texts must be greater than or equal to n_clusters")

    vocabulary = build_vocabulary(texts, max_features=max_features)
    if not vocabulary:
        raise ValueError("Could not build vocabulary from the provided texts")

    vectors, token_counters = vectorize_texts(texts, vocabulary)
    centroids = _initialize_centroids(vectors, n_clusters=n_clusters, seed=seed)
    labels = np.zeros(len(texts), dtype=int)

    for _ in range(max_iterations):
        new_labels = _assign_clusters(vectors, centroids)
        new_centroids = _recompute_centroids(vectors, new_labels, n_clusters)

        # Re-seed empty centroids from the farthest documents.
        for cluster_id in range(n_clusters):
            if np.any(new_labels == cluster_id):
                continue
            farthest_index = int(np.argmax(np.linalg.norm(vectors - centroids[new_labels], axis=1)))
            new_centroids[cluster_id] = vectors[farthest_index]

        if np.array_equal(new_labels, labels):
            centroids = new_centroids
            labels = new_labels
            break

        labels = new_labels
        centroids = new_centroids

    label_list = labels.tolist()
    assignments = _build_assignments(texts, label_list, token_counters)

    clusters = _build_clusters_from_labels(label_list, vectors, vocabulary)

    inertia = 0.0
    for idx, vector in enumerate(vectors):
        inertia += float(np.sum((vector - centroids[labels[idx]]) ** 2))

    return {
        "algorithm": "kmeans",
        "n_clusters": n_clusters,
        "vocabulary": vocabulary,
        "clusters": clusters,
        "assignments": assignments,
        "feature_dimension": len(vocabulary),
        "iterations": max_iterations,
        "inertia": round(inertia, 6),
    }


def cluster_texts_hdbscan(
    texts: List[str],
    max_features: int = 50,
    min_cluster_size: int = 2,
    min_samples: int | None = None,
) -> Dict[str, object]:
    if hdbscan is None:
        raise ValueError("HDBSCAN is not installed. Run `pip install hdbscan` first.")
    if len(texts) < min_cluster_size:
        raise ValueError("Number of texts must be greater than or equal to min_cluster_size")

    vocabulary = build_vocabulary(texts, max_features=max_features)
    if not vocabulary:
        raise ValueError("Could not build vocabulary from the provided texts")

    vectors, token_counters = vectorize_texts(texts, vocabulary)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        prediction_data=False,
    )
    labels = clusterer.fit_predict(vectors)
    label_list = [int(label) for label in labels.tolist()]
    assignments = _build_assignments(texts, label_list, token_counters)
    clusters = _build_clusters_from_labels(label_list, vectors, vocabulary)
    unique_non_noise = {label for label in label_list if label >= 0}
    noise_count = sum(1 for label in label_list if label == -1)

    return {
        "algorithm": "hdbscan",
        "n_clusters": len(unique_non_noise),
        "vocabulary": vocabulary,
        "clusters": clusters,
        "assignments": assignments,
        "feature_dimension": len(vocabulary),
        "iterations": 1,
        "inertia": 0.0,
        "noise_count": noise_count,
    }
