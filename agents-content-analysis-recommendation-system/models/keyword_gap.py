from collections import Counter


def keyword_gap(user_keywords, viral_keywords):
    # รองรับทั้ง list string และ list dict
    if user_keywords and isinstance(user_keywords[0], dict):
        user_keywords = [k["keyword"] for k in user_keywords]

    user_set = set(user_keywords)

    freq = Counter(viral_keywords)

    gap = [(k, v) for k, v in freq.items() if k not in user_set]

    gap_sorted = sorted(gap, key=lambda x: x[1], reverse=True)

    return [k for k, _ in gap_sorted[:10]]