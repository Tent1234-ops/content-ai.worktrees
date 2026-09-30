import re


# =========================
# 🔥 RULE-BASED ENTITY EXTRACTOR
# =========================
def extract_product_entities(text: str):
    text = text.lower()

    results = []

    # 🔥 pattern หลัก (brand + model)
    patterns = [
        # vxe darkenfire r1
        r"\b[a-zA-Z]+\s+[a-zA-Z]+\s*\d+\b",

        # logitech g pro x
        r"\b[a-zA-Z]+\s+[a-zA-Z]+\s+[a-zA-Z]*\s*\d*\b",

        # r1 / g304
        r"\b[a-zA-Z]*\d+\b",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            results.append(m.strip())

    return list(dict.fromkeys(results))


# =========================
# 🔥 CLEAN ENTITY (กันมั่ว)
# =========================
def filter_entities(entities):
    clean = []

    for e in entities:
        e = e.lower().strip()

        # ❌ กัน hallucination จาก LLM (เผื่อมี)
        if "product" in e:
            continue

        # ❌ ต้องมีตัวเลข (model)
        if not any(c.isdigit() for c in e):
            continue

        # ❌ ยาวเกิน = garbage
        if len(e.split()) > 5:
            continue

        # ❌ noise จาก ASR
        if e in ["testeron", "armour", "permissions"]:
            continue

        clean.append(e)

    return list(dict.fromkeys(clean))