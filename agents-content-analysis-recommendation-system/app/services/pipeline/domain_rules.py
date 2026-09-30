from __future__ import annotations

import re
from typing import Dict, List


DOMAIN_HINTS = {
    "mouse": [
        "mouse",
        "เมาส์",
        "gaming mouse",
        "wireless mouse",
        "sensor",
        "dpi",
        "polling rate",
        "click latency",
        "line collection",
    ],
    "keyboard": [
        "keyboard",
        "คีย์บอร์ด",
        "mechanical",
        "switch",
        "keycap",
        "gasket",
        "hotswap",
        "hot swap",
        "75%",
    ],
    "audio": [
        "headphone",
        "headphones",
        "headset",
        "หูฟัง",
        "earbuds",
        "earphone",
        "iem",
        "microphone",
        "noise cancelling",
        "latency",
        "driver",
        "soundstage",
        "sound quality",
        "sound",
    ],
    "smartphone": [
        "smartphone",
        "phone",
        "android",
        "ios",
        "iphone",
        "camera",
        "chipset",
        "snapdragon",
        "dimensity",
        "battery",
        "display",
        "oled",
        "amoled",
        "120hz",
        "fast charge",
    ],
    "food_drink": [
        "food",
        "drink",
        "restaurant",
        "cafe",
        "อาหาร",
        "ร้านอาหาร",
        "คาเฟ่",
        "เครื่องดื่ม",
        "เมนู",
        "รสชาติ",
        "taste",
        "flavor",
        "texture",
        "portion",
        "delivery",
    ],
    "fashion": [
        "fashion",
        "outfit",
        "แฟชั่น",
        "เสื้อผ้า",
        "รองเท้า",
        "กระเป๋า",
        "ทรง",
        "ไซซ์",
        "shirt",
        "pants",
        "dress",
        "shoe",
        "sneaker",
        "bag",
        "fabric",
        "material",
        "fit",
        "size",
        "comfort",
        "durable",
    ],
    "skincare": [
        "skincare",
        "serum",
        "moisturizer",
        "cleanser",
        "sunscreen",
        "spf",
        "retinol",
        "niacinamide",
        "vitamin c",
        "aha",
        "bha",
        "ceramide",
        "hyaluronic",
        "sensitive skin",
        "fragrance free",
        "alcohol free",
        "skin barrier",
    ],
}

DOMAIN_BASE = {
    "mouse": ["gaming mouse", "sensor performance", "click latency", "ergonomic shape"],
    "keyboard": ["mechanical keyboard", "typing feel", "sound profile", "build quality"],
    "audio": ["gaming audio", "microphone quality", "soundstage", "wear comfort", "sound quality"],
    "smartphone": ["camera quality", "chip performance", "battery life", "display quality"],
    "food_drink": ["taste profile", "portion size", "value for money", "service quality"],
    "fashion": ["material quality", "fit", "comfort", "durability"],
    "skincare": ["hydration", "barrier support", "active ingredients", "skin compatibility"],
}

CATEGORY_ALIASES = {
    "smartphone": {"smartphone", "smartphones", "phone", "mobile", "mobile_phone"},
    "food_drink": {
        "food_drink",
        "food",
        "food & drink",
        "food and drink",
        "food_and_drink",
        "restaurant",
        "restaurants",
        "cafe",
    },
    "skincare": {"skincare", "skin care", "skin_care", "beauty skincare", "beauty_skincare", "beauty"},
    "audio": {"audio", "headphone", "headphones", "earbuds", "microphone"},
    "keyboard": {"keyboard", "keyboards", "mechanical keyboard", "mechanical_keyboard"},
    "mouse": {"mouse", "mice", "computer_mouse", "gaming_mouse"},
    "fashion": {"fashion", "clothing", "apparel", "outfit"},
    "general": {"general", "other", "unknown"},
}


def _category_slug(value: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return slug.strip("_")


_CATEGORY_TO_DOMAIN = {
    _category_slug(alias): domain
    for domain, aliases in CATEGORY_ALIASES.items()
    for alias in aliases
}


def normalize_domain(value: str | None) -> str:
    """Map category labels to the canonical recommendation taxonomy."""
    slug = _category_slug(value)
    return _CATEGORY_TO_DOMAIN.get(slug, slug if slug in DOMAIN_BASE else "general")


def category_query_values(domain: str) -> List[str]:
    """Return normalized category labels accepted by a same-domain DB query."""
    canonical = normalize_domain(domain)
    return sorted(CATEGORY_ALIASES.get(canonical, {canonical}))

COMPARABLE_KEYWORDS_BY_DOMAIN = {
    "mouse": {
        "dpi",
        "polling rate",
        "weight",
        "battery life",
        "wireless",
        "bluetooth",
        "sensor performance",
        "click latency",
        "tracking stability",
        "ergonomics",
        "software tuning",
        "build quality",
    },
    "keyboard": {
        "switch type",
        "layout",
        "build quality",
        "typing feel",
        "sound profile",
        "connectivity",
        "battery life",
        "software tuning",
    },
    "audio": {
        "microphone quality",
        "sound quality",
        "soundstage",
        "latency",
        "noise cancelling",
        "battery life",
        "comfort",
        "connectivity",
        "value for money",
    },
    "skincare": {
        "active ingredients",
        "concentration",
        "hydration",
        "barrier support",
        "acne control",
        "brightening",
        "sun protection",
        "irritation risk",
        "skin compatibility",
        "texture finish",
    },
    "smartphone": {
        "camera quality",
        "chip performance",
        "battery life",
        "display quality",
        "charging speed",
        "thermal control",
        "stabilization",
        "value for money",
        "build quality",
        "software support",
    },
    "food_drink": {
        "taste profile",
        "portion size",
        "value for money",
        "location convenience",
        "service quality",
        "menu variety",
        "texture quality",
        "drink quality",
        "hygiene",
    },
    "fashion": {
        "material quality",
        "fit",
        "size accuracy",
        "comfort",
        "durability",
        "style versatility",
        "care requirement",
        "value for money",
    },
}

DOMAIN_DIMENSIONS_ORDER = {
    "mouse": [
        "dpi",
        "polling rate",
        "weight",
        "battery life",
        "wireless",
        "bluetooth",
        "tracking stability",
        "sensor performance",
        "click latency",
        "ergonomics",
        "software tuning",
        "build quality",
    ],
    "keyboard": [
        "switch type",
        "layout",
        "typing feel",
        "sound profile",
        "build quality",
        "connectivity",
        "battery life",
        "software tuning",
    ],
    "audio": [
        "sound quality",
        "soundstage",
        "microphone quality",
        "latency",
        "noise cancelling",
        "comfort",
        "connectivity",
        "battery life",
        "value for money",
    ],
    "skincare": [
        "active ingredients",
        "concentration",
        "hydration",
        "barrier support",
        "acne control",
        "brightening",
        "sun protection",
        "irritation risk",
        "skin compatibility",
        "texture finish",
    ],
    "smartphone": [
        "camera quality",
        "chip performance",
        "battery life",
        "display quality",
        "charging speed",
        "thermal control",
        "stabilization",
        "value for money",
        "build quality",
        "software support",
    ],
    "food_drink": [
        "taste profile",
        "portion size",
        "value for money",
        "location convenience",
        "service quality",
        "menu variety",
        "texture quality",
        "drink quality",
        "hygiene",
    ],
    "fashion": [
        "material quality",
        "fit",
        "size accuracy",
        "comfort",
        "durability",
        "style versatility",
        "care requirement",
        "value for money",
    ],
}

DOMAIN_PRIORITY = {
    "mouse": {
        "must_have_any": ["sensor performance", "ergonomic shape", "gaming mouse"],
        "prefer": [
            "high dpi sensor",
            "high polling rate",
            "ultra lightweight",
            "line collection mode",
            "tracking stability",
            "wireless connectivity",
            "long battery life",
        ],
    },
    "keyboard": {
        "must_have_any": ["mechanical keyboard", "typing feel", "build quality"],
        "prefer": ["hot swappable", "gasket mount", "rgb lighting", "sound profile"],
    },
    "audio": {
        "must_have_any": ["gaming audio", "microphone quality", "soundstage"],
        "prefer": ["noise cancelling", "wear comfort", "low latency", "value for money"],
    },
    "skincare": {
        "must_have_any": ["active ingredients", "hydration", "skin compatibility"],
        "prefer": ["sun protection", "barrier support", "irritation risk", "texture finish"],
    },
    "smartphone": {
        "must_have_any": ["camera quality", "chip performance", "battery life"],
        "prefer": ["display quality", "charging speed", "value for money", "software support"],
    },
    "food_drink": {
        "must_have_any": ["taste profile", "portion size", "value for money"],
        "prefer": ["service quality", "menu variety", "hygiene", "location convenience"],
    },
    "fashion": {
        "must_have_any": ["material quality", "fit", "comfort"],
        "prefer": ["size accuracy", "durability", "style versatility", "value for money"],
    },
}

PRESENT_THRESHOLD = 0.85
WEAK_THRESHOLD = 0.60
INFERRED_CONFIDENCE = 0.58
GAP_DELTA_THRESHOLD = 0.20

EXTRA_DOMAIN_PHRASES = {
    "fast charge",
    "low latency",
    "wired connectivity",
    "wireless connectivity",
    "menu variety",
    "style versatility",
    "skin compatibility",
    "barrier support",
}


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def detect_domain(text: str, visual_text: str = "") -> str:
    combined = f"{text} {visual_text}".lower()
    scores = {}

    for domain, hints in DOMAIN_HINTS.items():
        score = 0
        for raw_hint in hints:
            hint = _normalize_space((raw_hint or "").lower())
            if not hint:
                continue
            if re.search(r"[a-z]", hint):
                if re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", combined):
                    score += 1
            elif hint in combined:
                score += 1
        scores[domain] = score

    best_domain = max(scores, key=scores.get) if scores else "general"
    return normalize_domain(best_domain if scores.get(best_domain, 0) > 0 else "general")


def infer_domain_from_features(features: Dict[str, object], detected_domain: str) -> str:
    detected_domain = normalize_domain(detected_domain)
    def score(keys: List[str]) -> int:
        return sum(1 for key in keys if features.get(key))

    domain_scores = {
        "audio": (
            (2 if features.get("audio_product") else 0)
            + score(["mic_focus", "soundstage", "low_latency", "noise_cancelling", "comfort"])
            + (1 if features.get("connection_mode") else 0)
            + (1 if features.get("impedance_ohm") else 0)
        ),
        "smartphone": (
            (2 if features.get("smartphone_product") else 0)
            + (1 if features.get("smartphone_mention") else 0)
            + score(
                [
                    "camera_focus",
                    "chip_focus",
                    "display_focus",
                    "charging_focus",
                    "thermal_focus",
                    "stabilization_focus",
                ]
            )
            + (1 if features.get("battery_mah") else 0)
        ),
        "food_drink": (
            (2 if features.get("food_product") else 0)
            + score(
                [
                    "taste_focus",
                    "portion_focus",
                    "service_focus",
                    "menu_focus",
                    "hygiene_focus",
                    "location_focus",
                    "food_texture_focus",
                ]
            )
        ),
        "fashion": (
            (2 if features.get("fashion_product") else 0)
            + score(
                [
                    "material_focus",
                    "fit_focus",
                    "size_focus",
                    "fashion_comfort_focus",
                    "durability_focus",
                    "style_focus",
                    "care_focus",
                ]
            )
        ),
        "keyboard": (
            score(["switch_type", "hot_swap", "gasket", "layout", "keycap_quality"])
            + (1 if features.get("connection_mode") else 0)
        ),
        "mouse": score(["dpi", "polling_rate_hz", "line_collection", "fps_focus", "ergonomic_claim"]),
        "skincare": (
            (2 if features.get("skincare_product") else 0)
            + score(
                [
                    "active_ingredients",
                    "concentration_percent",
                    "hydration_claim",
                    "barrier_claim",
                    "acne_claim",
                    "brightening_claim",
                    "sun_protection",
                    "low_irritation_claim",
                    "texture_claim",
                ]
            )
        ),
    }

    if domain_scores["audio"] >= 3 and domain_scores["smartphone"] <= 2:
        return "audio"

    best_domain = max(domain_scores, key=domain_scores.get)
    best_score = domain_scores[best_domain]
    if best_score <= 0:
        return detected_domain

    ties = [domain for domain, score_value in domain_scores.items() if score_value == best_score]
    if len(ties) > 1:
        if detected_domain in ties:
            return detected_domain
        if "audio" in ties and features.get("audio_product"):
            return "audio"

    return best_domain


def domain_phrase_lexicon() -> List[str]:
    phrases = set(EXTRA_DOMAIN_PHRASES)
    for hints in DOMAIN_HINTS.values():
        phrases.update(hints)
    for keywords in DOMAIN_BASE.values():
        phrases.update(keywords)
    for keywords in COMPARABLE_KEYWORDS_BY_DOMAIN.values():
        phrases.update(keywords)
    for dimensions in DOMAIN_DIMENSIONS_ORDER.values():
        phrases.update(dimensions)
    for priority in DOMAIN_PRIORITY.values():
        phrases.update(priority.get("must_have_any", []))
        phrases.update(priority.get("prefer", []))
    cleaned = {
        _normalize_space(phrase.lower())
        for phrase in phrases
        if phrase and len(_normalize_space(phrase)) >= 3
    }
    return sorted(cleaned, key=lambda item: (-len(item.split()), -len(item), item))
