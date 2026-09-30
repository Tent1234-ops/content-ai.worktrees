import re

print("Loading Keyword Extractor V11 (Clean Candidates)...")

# =========================
# Normalize
# =========================
def normalize_text(text):
    text = text.lower()

    corrections = {
        "fixie": "rgb",
        "ppt": "pbt",
        "mcnical": "mechanical",
        "mechanial": "mechanical",
        "พอสวอป": "hot swap",
    }

    for k, v in corrections.items():
        text = text.replace(k, v)

    text = re.sub(r"[^ก-๙a-zA-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================
# Candidate Generator (สำคัญสุด)
# =========================
def extract_keywords(text, corpus=None):
    try:
        text = normalize_text(text)

        keywords = set()

        # 🔥 model
        models = re.findall(r"[a-z]+\d{2,5}", text)
        keywords.update(models)

        # 🔥 tech keywords (generic ไม่ hardcode domain เดียว)
        patterns = [
            "hot swap", "rgb", "gasket", "switch",
            "linear", "wireless", "bluetooth",
            "latency", "sound", "typing", "battery",
        ]

        for p in patterns:
            if p in text:
                keywords.add(p)

        # 🔥 combine logic
        if "linear" in keywords and "switch" in keywords:
            keywords.add("linear switch")

        if "typing" in keywords and "sound" in keywords:
            keywords.add("typing sound")

        # 🔥 platform
        if "android" in text:
            keywords.add("android")

        if "ios" in text:
            keywords.add("ios")

        if "windows" in text:
            keywords.add("windows")

        if "mac" in text:
            keywords.add("mac")

        # 🔥 IMPORTANT: add base concept
        if "keyboard" in text or "คีย์บอร์ด" in text:
            keywords.add("keyboard")

        return list(keywords)

    except Exception as e:
        print("Keyword error:", e)
        return []