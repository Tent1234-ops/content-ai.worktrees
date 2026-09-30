import os
import re
import subprocess
import tempfile
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from app.services.pipeline.domain_rules import (
    detect_domain as shared_detect_domain,
    infer_domain_from_features as shared_infer_domain_from_features,
    DOMAIN_HINTS as SHARED_DOMAIN_HINTS,
    DOMAIN_BASE as SHARED_DOMAIN_BASE,
)
from app.services.jobs import update_current_job
from utils.text_clean import clean_text

try:
    from models.scene_detect import detect_scenes
except Exception:
    detect_scenes = None


# =========================
# Utils
# =========================
def convert_numpy(obj):
    if isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, list):
        return [convert_numpy(i) for i in obj]
    if isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    return obj


def extract_audio(
    video_path: str,
    audio_path: str,
    max_seconds: int | None = None,
) -> bool:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
    ]
    if max_seconds is not None and max_seconds > 0:
        command.extend(["-t", str(max_seconds)])
    command.append(audio_path)
    try:
        run_options = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "check": False,
        }
        if max_seconds is not None and max_seconds > 0:
            run_options["timeout"] = max(30, max_seconds + 45)
        result = subprocess.run(command, **run_options)
        return result.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
    except Exception:
        return False


def transcript_for_time_window(
    segments: Iterable[Dict[str, object]],
    duration_seconds: int,
) -> str:
    """Return text from timestamped ASR segments that begin inside a time window."""
    window_end = max(0.0, float(duration_seconds))
    parts: List[str] = []
    for segment in segments:
        text = normalize_space(str(segment.get("text") or ""))
        if not text:
            continue
        try:
            start = float(segment.get("start"))
        except (TypeError, ValueError):
            continue
        if start < 0 or start >= window_end:
            continue
        parts.append(text)
    return normalize_space(" ".join(parts))


def segment_count_for_time_window(
    segments: Iterable[Dict[str, object]],
    duration_seconds: int,
) -> int:
    window_end = max(0.0, float(duration_seconds))
    count = 0
    for segment in segments:
        try:
            start = float(segment.get("start"))
        except (TypeError, ValueError):
            continue
        if 0 <= start < window_end:
            count += 1
    return count


def simple_summarize(text: str):
    raw_text = normalize_space(text or "")
    if not raw_text:
        return ""

    # Thai ASR often has very long run-on text without sentence punctuation.
    # Split with discourse markers as a fallback.
    sentences = [normalize_space(s) for s in re.split(r"[.!?]", raw_text) if normalize_space(s)]
    if len(sentences) <= 1:
        clauses = [normalize_space(s) for s in re.split(r"\s+(?:แล้วก็|แล้ว|และ|ก็คือ|ซึ่ง|แต่|เพราะ|สำหรับ)\s+", raw_text) if normalize_space(s)]
        if clauses:
            sentences = clauses

    if not sentences:
        return ""

    # Prefer the most informative sentence instead of always taking the first one.
    signal_terms = [
        "ราคา", "คุ้ม", "หูฟัง", "ไมค์", "เสียง", "กล้อง", "ชิป", "แบต", "หน้าจอ",
        "รสชาติ", "ปริมาณ", "บริการ", "วัสดุ", "ทรง", "ไซซ์", "สบาย", "ทน",
        "price", "value", "camera", "chip", "battery", "display", "sound", "taste", "material", "fit",
    ]

    penalty_terms = ["คลิปหน้า", "ติดตาม", "เจอกันใหม่", "จับจุ๊บ", "subscribe", "follow"]

    def score_sentence(sentence: str) -> Tuple[int, int, int]:
        low = sentence.lower()
        signal_score = sum(1 for t in signal_terms if t in low)
        penalty = sum(1 for t in penalty_terms if t in low)
        # Slightly prefer medium-length descriptive sentences.
        length = len(sentence)
        if length < 20:
            length_score = -10
        elif length > 170:
            length_score = -5
        else:
            length_score = min(80, length)
        return signal_score, -penalty, length_score

    best = max(sentences, key=score_sentence)
    best = re.sub(r"\b(ครับ|ค่ะ|นะ|เว้ย)\b", "", best, flags=re.IGNORECASE)
    best = normalize_space(best)
    return best[:150] + "..." if len(best) > 150 else best


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# =========================
# Noise and Domain
# =========================
ASR_NOISE_PATTERNS = [
    r"\b(testeron|permissions|olution|mis)\b",
    r"\b(uh|um|erm)\b",
]


def remove_asr_noise(text: str) -> str:
    cleaned = text
    for pattern in ASR_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    return normalize_space(cleaned)


# Optional Thai NLP helpers
try:
    from pythainlp.tokenize import word_tokenize as pythai_word_tokenize
except Exception:
    pythai_word_tokenize = None


def normalize_asr_terms(text: str, aggressive: bool = False) -> str:
    """Normalize only explicitly reviewed ASR terminology.

    ``aggressive`` remains in the signature for compatibility with older
    callers, but Phase 19 intentionally performs no fuzzy or dictionary-wide
    spelling correction on the transcript.
    """
    replacements = {
        "เกรมมิ้ง": "เกมมิ่ง",
        "เกรมมิ่ง": "เกมมิ่ง",
        "เคมมิง": "เกมมิ่ง",
        "เคมมิ้ง": "เกมมิ่ง",
        "เคมมิ่ง": "เกมมิ่ง",
        "gaming": "เกมมิ่ง",
        "เมาส": "เมาส์",
        "พอสวอป": "hot swap",
        "ฮอตสวอป": "hot swap",
        "หอตสวอป": "hot swap",
        "ลิเนียร์": "linear",
        "เลียเนียร์": "linear",
        "สวิช": "switch",
        "สวิทช์": "switch",
        "สวิตช์": "switch",
        "คีย์บอด": "คีย์บอร์ด",
        "คียบอร์ด": "คีย์บอร์ด",
        "ppt": "pbt",
        "fixie": "fixed rgb",
        "ดองเกิ้ล": "dongle",
        "ดองเกิล": "dongle",
        "บลูทูธ": "bluetooth",
        "ไรสาย": "ไร้สาย",
        "ชารจ": "ชาร์จ",
        "แบท": "แบต",
        "แบตเตอร์รี่": "แบตเตอรี่",
        "แบตตารี่": "แบตเตอรี่",
        "ชิพ": "ชิป",
        "สแนปดรากอน": "snapdragon",
        "สแนปดราก้อน": "snapdragon",
        "เดมเซตี": "dimensity",
        "ไดเมนซิตี้": "dimensity",
        "อะโมเล็ด": "amoled",
        "อะโมเลด": "amoled",
        "simgott": "simgot",
        "simgod": "simgot",
        "e g": "eg",
        "aem": "iem",
        # Quick fixes observed in dataset/artifacts
        "โคตเทป": "โคตรเทพ",
        "โคต": "โคตร",
    }
    normalized = text or ""
    for wrong, right in replacements.items():
        normalized = normalized.replace(wrong, right)

    return normalize_space(normalized)


def normalize_spoken_model_text(text: str) -> str:
    normalized = text

    # Convert Thai spoken digits in model names, e.g. "สองแปดศูนย์" -> "280"
    digit_words = {
        "ศูนย์": "0",
        "หนึ่ง": "1",
        "สอง": "2",
        "สาม": "3",
        "สี่": "4",
        "ห้า": "5",
        "หก": "6",
        "เจ็ด": "7",
        "แปด": "8",
        "เก้า": "9",
    }
    for w, d in digit_words.items():
        normalized = normalized.replace(w, d)

    # Merge fragmented alphabet model tokens: "e g" -> "eg"
    prev = None
    while prev != normalized:
        prev = normalized
        normalized = re.sub(r"\b([a-z])\s+([a-z])\b", r"\1\2", normalized)

    return normalize_space(normalized)


DOMAIN_HINTS = {
    "mouse": [
        "mouse",
        "เมาส์",
        "เมาส",
        "gaming mouse",
        "เกมมิ่ง",
        "เกมมิ้ง",
        "เกรมมิ้ง",
        "wireless mouse",
        "ไร้สาย",
        "sensor",
        "dpi",
        "polling rate",
        "click latency",
        "line collection",
        "สะบัดเมาส์",
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
        "เฮดเซต",
        "earbuds",
        "earphone",
        "microphone",
        "noise cancelling",
        "latency",
        "driver",
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
        "sweet",
        "salty",
        "spicy",
        "texture",
        "portion",
        "price",
        "menu",
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
        "non-comedogenic",
        "skin barrier",
    ],
}


def detect_domain(text: str, visual_text: str = "") -> str:
    return shared_detect_domain(text, visual_text)

    combined = f"{text} {visual_text}".lower()
    scores = {}

    for domain, hints in DOMAIN_HINTS.items():
        score = 0
        for h in hints:
            hint = normalize_space((h or "").lower())
            if not hint or "?" in hint:
                continue
            # Skip obviously broken/mis-encoded hints to reduce false positives.
            if "à" in hint:
                continue
            if re.search(r"[a-z]", hint):
                if re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", combined):
                    score += 1
            elif hint in combined:
                score += 1
        scores[domain] = score

    best_domain = max(scores, key=scores.get) if scores else "general"
    return best_domain if scores.get(best_domain, 0) > 0 else "general"


def infer_domain_from_features(features: Dict[str, object], detected_domain: str) -> str:
    return shared_infer_domain_from_features(features, detected_domain)

    def score(keys: List[str]) -> int:
        return sum(1 for k in keys if features.get(k))

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
            + score(["camera_focus", "chip_focus", "display_focus", "charging_focus", "thermal_focus", "stabilization_focus"])
            + (1 if features.get("battery_mah") else 0)
        ),
        "food_drink": (
            (2 if features.get("food_product") else 0)
            + score(["taste_focus", "portion_focus", "service_focus", "menu_focus", "hygiene_focus", "location_focus", "food_texture_focus"])
        ),
        "fashion": (
            (2 if features.get("fashion_product") else 0)
            + score(["material_focus", "fit_focus", "size_focus", "fashion_comfort_focus", "durability_focus", "style_focus", "care_focus"])
        ),
        "keyboard": (
            score(["switch_type", "hot_swap", "gasket", "layout", "keycap_quality"])
            + (1 if features.get("connection_mode") else 0)
        ),
        "mouse": score(["dpi", "polling_rate_hz", "line_collection", "fps_focus", "ergonomic_claim"]),
        "skincare": (
            (2 if features.get("skincare_product") else 0)
            + score(["active_ingredients", "concentration_percent", "hydration_claim", "barrier_claim", "acne_claim", "brightening_claim", "sun_protection", "low_irritation_claim", "texture_claim"])
        ),
    }

    # Guard against accessory mentions like "use with smartphone"
    # in audio reviews; require stronger smartphone evidence.
    if domain_scores["audio"] >= 3 and domain_scores["smartphone"] <= 2:
        return "audio"

    best_domain = max(domain_scores, key=domain_scores.get)
    best_score = domain_scores[best_domain]
    if best_score <= 0:
        return detected_domain

    ties = [d for d, s in domain_scores.items() if s == best_score]
    if len(ties) > 1:
        if detected_domain in ties:
            return detected_domain
        if "audio" in ties and features.get("audio_product"):
            return "audio"

    return best_domain


# =========================
# Product and Features
# =========================
BRANDS = [
    # Common gaming/peripheral brands
    "logitech",
    "razer",
    "steelseries",
    "hyperx",
    "corsair",
    "cooler master",
    "msi",
    "asus",
    "lenovo",
    "dell",
    "keychron",
    "akko",
    "royal kludge",
    "fantech",
    "ajazz",
    "vxe",
    "darkenfire",
    # Audio-focused brands
    "sony",
    "bose",
    "sennheiser",
    "shure",
    "beyerdynamic",
    "jbl",
    "marshall",
    "edifier",
    "anker",
    "soundcore",
    "anker soundcore",
    "simgot",
    "fiio",
    "ifi",
    "audeze",
    "meze",
    "kz",
    "blon",
    "truthear",
    "qcy",
    "xiaomi",
    "realme",
    "oneplus",
    "huawei",
    "samsung",
    "apple",
]


def extract_main_product(text: str) -> Optional[str]:
    lower = normalize_spoken_model_text(normalize_asr_terms(text.lower()))

    # brand + model style: "logitech g304" or "razer deathadder v3"
    for brand in BRANDS:
        pattern = rf"\b({re.escape(brand)}\s+[a-z0-9\-]+(?:\s+[a-z0-9\-]+){{0,2}})\b"
        m = re.search(pattern, lower)
        if m:
            candidate = normalize_space(m.group(1))
            compact_model = re.match(r"^([a-z]+)\s+([a-z]{1,4})\s+(\d{2,4})$", candidate)
            if compact_model:
                candidate = f"{compact_model.group(1)} {compact_model.group(2)}{compact_model.group(3)}"
            if any(ch.isdigit() for ch in candidate) or len(candidate.split()) >= 2:
                return candidate

    # audio-style spoken model, e.g. "simgot eg 280" -> "simgot eg280"
    m_audio = re.search(r"\b(simgot)\s+([a-z]{1,4})\s*(\d{2,4})\b", lower)
    if m_audio:
        return f"{m_audio.group(1)} {m_audio.group(2)}{m_audio.group(3)}"

    # fallback model token
    m = re.search(r"\b[a-z]{1,6}\d{2,5}[a-z0-9\-]*\b", lower)
    if m:
        return m.group(0)

    return None


def parse_int(num_text: str) -> int:
    return int(num_text.replace(",", "").strip())


def parse_thai_price_hint(text: str) -> Optional[int]:
    low = text.lower()

    direct = {
        "หกร้อย": 600,
        "เจ็ดร้อย": 700,
        "แปดร้อย": 800,
        "เก้าร้อย": 900,
        "พัน": 1000,
        "สองพัน": 2000,
        "สามพัน": 3000,
    }

    if "ไม่ถึงสองพัน" in low or "ไม่เกินสองพัน" in low:
        return 2000

    for token, value in direct.items():
        if token in low:
            return value

    m = re.search(r"(?:ประมาณ|ราว|แค่)?\s*(\d{3,4})\s*(?:กว่าบาท|บาท)", low)
    if m:
        return int(m.group(1))

    return None


def extract_features(text: str) -> Dict[str, object]:
    features: Dict[str, object] = {}
    low = normalize_asr_terms(text.lower())

    weight = re.search(r"(\d{1,3}(?:\.\d+)?)\s*(?:g|gram|กรัม)", low)
    if weight:
        features["weight_g"] = float(weight.group(1))

    price = re.search(r"(\d{2,6}(?:,\d{3})?)\s*(?:baht|thb|bath|บาท)\b", low)
    if price:
        features["price_thb"] = parse_int(price.group(1))
    else:
        thai_price = parse_thai_price_hint(low)
        if thai_price:
            features["price_thb"] = thai_price

    dpi = re.search(r"(\d{1,2})\s*k\s*(?:dpi)?|(?<!\d)(\d{3,5})\s*dpi", low)
    if dpi:
        if dpi.group(1):
            features["dpi"] = int(dpi.group(1)) * 1000
        elif dpi.group(2):
            features["dpi"] = int(dpi.group(2))

    polling = re.search(r"(\d{3,4})\s*(?:hz|เฮิร์ตซ์)", low)
    if polling:
        features["polling_rate_hz"] = int(polling.group(1))

    battery = re.search(r"(\d{1,3})\s*(?:hours|hrs|hour|ชั่วโมง|ชม)\b", low)
    if battery:
        features["battery_hours"] = int(battery.group(1))
    elif any(
        phrase in low
        for phrase in [
            "ไม่ต้องชาร์จ",
            "ไม่ต้องชารจ",
            "แบตอึด",
            "แบตเตอรี่อึด",
            "ความอึด",
            "ใช้งานได้ทั้งวัน",
        ]
    ):
        features["battery_claim_long"] = True

    battery_mah = re.search(r"(\d{3,5})\s*(?:mah\b|มิลลิแอมป์)", low)
    if battery_mah is None:
        battery_mah = re.search(
            r"(?:battery|แบต(?:เตอรี่)?)\s*(\d{3,5})",
            low,
        )
    if battery_mah:
        features["battery_mah"] = int(battery_mah.group(1))

    impedance = re.search(r"(\d{1,3})\s*ohm\b", low)
    if impedance:
        features["impedance_ohm"] = int(impedance.group(1))

    if "wireless" in low or "ไร้สาย" in low:
        features["wireless"] = True
    if "bluetooth" in low:
        features["bluetooth"] = True
    if "rgb" in low:
        features["rgb"] = True
    if "hotswap" in low or "hot swap" in low:
        features["hot_swap"] = True
    if "gasket" in low:
        features["gasket"] = True
    if "noise cancelling" in low:
        features["noise_cancelling"] = True
    if "line collection" in low:
        features["line_collection"] = True
    if "fps" in low or "เกมยิงปืน" in low:
        features["fps_focus"] = True
    if "ถนัดมือ" in low:
        features["ergonomic_claim"] = True

    if "linear" in low:
        features["switch_type"] = "linear"
    elif "tactile" in low:
        features["switch_type"] = "tactile"
    elif "clicky" in low:
        features["switch_type"] = "clicky"
    elif "red switch" in low:
        features["switch_type"] = "linear"

    layout_pct = re.search(r"\b(60|65|68|75|80|96|100)\s*%", low)
    if layout_pct:
        features["layout"] = f"{layout_pct.group(1)}%"
    elif "tkl" in low:
        features["layout"] = "tkl"
    elif "เจ็ดสิบห้าเปอร์เซ็นต์" in low:
        features["layout"] = "75%"

    wired_hint = ("เสียบสาย" in low) or ("wired" in low)
    wireless_hint = ("wireless" in low) or ("ไร้สาย" in low)
    bt_hint = ("bluetooth" in low)

    if wired_hint and (wireless_hint or bt_hint):
        features["connection_mode"] = "tri-mode"
        features["wireless"] = True
    elif wireless_hint or bt_hint:
        features["connection_mode"] = "wireless"
        features["wireless"] = True
    elif wired_hint:
        features["connection_mode"] = "wired"

    if re.search(r"\bwindows\b", low) or "วินโด" in low:
        features["supports_windows"] = True
    if re.search(r"\bmac\b", low) or "แมค" in low:
        features["supports_mac"] = True
    if re.search(r"\bandroid\b", low):
        features["supports_android"] = True
    if re.search(r"\bios\b", low):
        features["supports_ios"] = True

    if "pbt" in low or "double shot" in low:
        features["keycap_quality"] = "pbt_double_shot"

    if "fixy" in low or "fixed rgb" in low:
        features["lighting_mode"] = "fixed_rgb"

    if "headphone" in low or "headset" in low or "earphone" in low or "earbuds" in low or "iem" in low or "หูฟัง" in low:
        features["audio_product"] = True
    if "mic" in low or "microphone" in low or "ไมโครโฟน" in low or "ไมค์" in low:
        features["mic_focus"] = True
    if "anc" in low or "noise cancelling" in low or "ตัดเสียงรบกวน" in low:
        features["noise_cancelling"] = True
    if "low latency" in low or "หน่วงต่ำ" in low:
        features["low_latency"] = True
    driver_mm = re.search(r"(\d{1,2})\s*mm", low)
    if driver_mm:
        features["driver_mm"] = int(driver_mm.group(1))
    if (
        "soundstage" in low
        or "เวทีเสียง" in low
        or "เสียงมีความกว้าง" in low
        or "เสียงปืน" in low
        or "ฝีเท้า" in low
    ):
        features["soundstage"] = True
    if "ใส่สบาย" in low or "comfort" in low:
        features["comfort"] = True

    if features.get("audio_product") and features.get("connection_mode") is None:
        if ("สาย" in low and "เมตร" in low) or ("cable" in low and "meter" in low):
            features["connection_mode"] = "wired"

    # Skincare / beauty signals
    if any(k in low for k in ["serum", "moisturizer", "cleanser", "sunscreen", "spf", "เซรั่ม", "ครีม", "กันแดด"]):
        features["skincare_product"] = True

    actives = []
    for ing in ["retinol", "niacinamide", "vitamin c", "aha", "bha", "pha", "ceramide", "hyaluronic"]:
        if ing in low:
            actives.append(ing)
    if actives:
        features["active_ingredients"] = sorted(set(actives))

    conc = re.findall(r"(\d{1,2}(?:\.\d+)?)\s*%", low)
    if conc:
        features["concentration_percent"] = [float(c) for c in conc[:3]]

    if any(k in low for k in ["hydrat", "moist", "ชุ่มชื้น"]):
        features["hydration_claim"] = True
    if any(k in low for k in ["barrier", "ceramide", "เกราะผิว"]):
        features["barrier_claim"] = True
    if any(k in low for k in ["acne", "สิว", "oil control", "คุมมัน"]):
        features["acne_claim"] = True
    if any(k in low for k in ["bright", "กระจ่าง", "จุดด่างดำ", "tone up"]):
        features["brightening_claim"] = True
    if "spf" in low or "pa+" in low or "กันแดด" in low:
        features["sun_protection"] = True
    if any(k in low for k in ["fragrance free", "alcohol free", "อ่อนโยน", "แพ้ง่าย"]):
        features["low_irritation_claim"] = True
    if any(k in low for k in ["texture", "finish", "ซึมไว", "เหนอะหนะ", "sticky"]):
        features["texture_claim"] = True

    # Smartphone signals
    phone_strong = any(
        keyword in low
        for keyword in [
            "smartphone",
            "iphone",
            "android phone",
            "สมาร์ตโฟน",
            "โทรศัพท์มือถือ",
            "มือถือ",
            "review phone",
        ]
    )
    phone_generic = bool(
        re.search(r"\bphone\b", low)
        or ("โทรศัพท์" in low)
        or ("มือถือ" in low)
    )
    if phone_strong:
        features["smartphone_product"] = True
    elif phone_generic:
        features["smartphone_mention"] = True
    if any(
        keyword in low
        for keyword in [
            "camera",
            "กล้อง",
            "ถ่ายรูป",
            "ถ่ายภาพ",
            "ภาพ",
            "เลนส์",
            "เซนเซอร์",
            "night mode",
            "portrait",
        ]
    ):
        features["camera_focus"] = True
    if any(
        keyword in low
        for keyword in [
            "snapdragon",
            "dimensity",
            "mediatek",
            "exynos",
            "chipset",
            "chip",
            "ชิป",
            "ชิปเซ็ต",
            "ประมวลผล",
        ]
    ):
        features["chip_focus"] = True
    if any(
        keyword in low
        for keyword in [
            "display",
            "oled",
            "amoled",
            "screen",
            "refresh rate",
            "จอ",
            "หน้าจอ",
            "ความสว่าง",
            "นิต",
        ]
    ):
        features["display_focus"] = True
    if any(
        keyword in low
        for keyword in [
            "fast charge",
            "watt",
            "ชาร์จไว",
            "ชาร์จเร็ว",
            "วัตต์",
        ]
    ) or re.search(r"\b\d{2,3}\s*w\b", low):
        features["charging_focus"] = True
    if any(
        keyword in low
        for keyword in [
            "heat",
            "thermal",
            "cooling",
            "cooler",
            "throttle",
            "ระบายความร้อน",
            "ความร้อน",
            "เครื่องร้อน",
            "อุณหภูมิ",
            "พัดลม",
        ]
    ):
        features["thermal_focus"] = True
    if any(k in low for k in ["stabilization", "ois", "กันสั่น"]):
        features["stabilization_focus"] = True
    if features.get("smartphone_mention") and any(
        features.get(k) for k in ["camera_focus", "chip_focus", "display_focus", "charging_focus", "thermal_focus", "stabilization_focus"]
    ):
        features["smartphone_product"] = True

    # Food / drink signals
    if any(k in low for k in ["restaurant", "cafe", "food", "drink", "อาหาร", "เครื่องดื่ม"]):
        features["food_product"] = True
    if any(k in low for k in ["taste", "flavor", "อร่อย", "รสชาติ"]):
        features["taste_focus"] = True
    if any(k in low for k in ["portion", "ปริมาณ", "จานใหญ่", "เยอะ"]):
        features["portion_focus"] = True
    if any(k in low for k in ["service", "พนักงาน", "บริการ"]):
        features["service_focus"] = True
    if any(k in low for k in ["menu", "เมนู", "หลากหลาย"]):
        features["menu_focus"] = True
    if any(k in low for k in ["สะอาด", "hygiene", "clean"]):
        features["hygiene_focus"] = True
    if any(k in low for k in ["location", "เดินทาง", "ที่จอดรถ"]):
        features["location_focus"] = True
    if any(k in low for k in ["texture", "สัมผัส", "หนึบ", "กรอบ"]):
        features["food_texture_focus"] = True

    # Fashion signals
    if any(k in low for k in ["fashion", "outfit", "shirt", "pants", "dress", "เสื้อ", "กางเกง", "รองเท้า"]):
        features["fashion_product"] = True
    if any(k in low for k in ["material", "fabric", "ผ้า", "วัสดุ"]):
        features["material_focus"] = True
    if any(k in low for k in ["fit", "ทรง", "เข้ารูป"]):
        features["fit_focus"] = True
    if any(k in low for k in ["size", "ไซซ์", "size chart"]):
        features["size_focus"] = True
    if any(k in low for k in ["comfortable", "comfort", "ใส่สบาย"]):
        features["fashion_comfort_focus"] = True
    if any(k in low for k in ["durable", "ทน", "ซักแล้ว", "เย็บ"]):
        features["durability_focus"] = True
    if any(k in low for k in ["mix and match", "style", "แต่งตัว"]):
        features["style_focus"] = True
    if any(k in low for k in ["ดูแล", "care", "ซักมือ", "dry clean"]):
        features["care_focus"] = True
    if features.get("fashion_comfort_focus") and not features.get("fashion_product"):
        features.pop("fashion_comfort_focus", None)

    return features


# =========================
# Keyword Rules
# =========================
DOMAIN_BASE = {
    "mouse": ["gaming mouse", "sensor performance", "click latency", "ergonomic shape"],
    "keyboard": ["mechanical keyboard", "typing feel", "sound profile", "build quality"],
    "audio": ["gaming audio", "microphone quality", "soundstage", "wear comfort"],
    "smartphone": ["camera quality", "chip performance", "battery life", "display quality"],
    "food_drink": ["taste profile", "portion size", "value for money", "service quality"],
    "fashion": ["material quality", "fit", "comfort", "durability"],
    "skincare": ["hydration", "barrier support", "active ingredients", "skin compatibility"],
}

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

PRESENT_THRESHOLD = 0.90
WEAK_THRESHOLD = 0.65
INFERRED_CONFIDENCE = 0.60
GAP_DELTA_THRESHOLD = 0.25

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


CANONICAL = {
    "lightweight": "ultra lightweight",
    "high dpi": "high dpi sensor",
    "polling": "high polling rate",
    "battery": "long battery life",
    "rgb": "rgb lighting",
    "wireless": "wireless connectivity",
    "bluetooth": "bluetooth support",
    "hotswap": "hot swappable",
    "hot swap": "hot swappable",
    "noise cancelling": "noise cancelling",
    "comfort": "comfortable fit",
    "ergonomic": "ergonomic design",
}


def feature_to_keywords(features: Dict[str, object], domain: str) -> List[str]:
    kws = []

    dpi = features.get("dpi", 0)
    if isinstance(dpi, int):
        if dpi >= 8000:
            kws.append("high dpi sensor")
        elif dpi >= 3200:
            kws.append("balanced dpi range")

    polling = features.get("polling_rate_hz", 0)
    if isinstance(polling, int) and polling >= 1000:
        kws.append("high polling rate")

    weight = features.get("weight_g", 999)
    if isinstance(weight, (int, float)) and weight < 65:
        kws.append("ultra lightweight")

    battery_hours = features.get("battery_hours", 0)
    if isinstance(battery_hours, int) and battery_hours >= 40:
        kws.append("long battery life")
    elif features.get("battery_claim_long"):
        kws.append("long battery life")

    if features.get("wireless"):
        kws.append("wireless connectivity")
    if features.get("bluetooth"):
        kws.append("bluetooth support")
    if features.get("rgb"):
        kws.append("rgb lighting")
    if features.get("hot_swap"):
        kws.append("hot swappable")
    if features.get("gasket"):
        kws.append("gasket mount")
    if features.get("noise_cancelling"):
        kws.append("noise cancelling")
    if features.get("line_collection"):
        kws.append("line collection mode")
    if features.get("fps_focus"):
        kws.append("fps gaming")
    if features.get("ergonomic_claim"):
        kws.append("ergonomic design")

    switch_type = features.get("switch_type")
    if isinstance(switch_type, str):
        kws.append(f"{switch_type} switches")
        if domain == "keyboard":
            kws.append("switch type")

    if domain == "keyboard":
        if features.get("hot_swap"):
            kws.append("hot swappable")
            kws.append("switch type")
        if features.get("layout"):
            kws.append("layout")
        if features.get("connection_mode") == "wired":
            kws.append("wired connectivity")
        elif features.get("connection_mode") in {"wireless", "tri-mode"}:
            kws.append("wireless connectivity")
        if features.get("keycap_quality"):
            kws.append("build quality")
        if any(
            features.get(k)
            for k in ["supports_windows", "supports_mac", "supports_android", "supports_ios"]
        ):
            kws.append("software support")

    if domain == "audio" and features.get("impedance_ohm"):
        kws.append("low impedance")
    if domain == "audio":
        if features.get("mic_focus"):
            kws.append("microphone quality")
        if features.get("soundstage"):
            kws.append("soundstage")
            kws.append("sound quality")
        if features.get("low_latency"):
            kws.append("low latency")
        if features.get("comfort"):
            kws.append("wear comfort")
        if features.get("wireless") or features.get("bluetooth"):
            kws.append("wireless connectivity")
        elif features.get("connection_mode") == "wired":
            kws.append("wired connectivity")
        if features.get("price_thb"):
            kws.append("value for money")
    if domain == "skincare":
        if features.get("active_ingredients"):
            kws.append("active ingredients")
        if features.get("concentration_percent"):
            kws.append("concentration")
        if features.get("hydration_claim"):
            kws.append("hydration")
        if features.get("barrier_claim"):
            kws.append("barrier support")
        if features.get("acne_claim"):
            kws.append("acne control")
        if features.get("brightening_claim"):
            kws.append("brightening")
        if features.get("sun_protection"):
            kws.append("sun protection")
        if features.get("low_irritation_claim"):
            kws.append("irritation risk")
        if features.get("texture_claim"):
            kws.append("texture finish")
        if features.get("skincare_product"):
            kws.append("skin compatibility")
    if domain == "smartphone":
        if features.get("camera_focus"):
            kws.append("camera quality")
        if features.get("chip_focus"):
            kws.append("chip performance")
        if features.get("display_focus"):
            kws.append("display quality")
        if features.get("charging_focus"):
            kws.append("charging speed")
        if features.get("thermal_focus"):
            kws.append("thermal control")
        if features.get("stabilization_focus"):
            kws.append("stabilization")
        if features.get("smartphone_product"):
            kws.append("software support")
    if domain == "food_drink":
        if features.get("taste_focus"):
            kws.append("taste profile")
        if features.get("portion_focus"):
            kws.append("portion size")
        if features.get("service_focus"):
            kws.append("service quality")
        if features.get("menu_focus"):
            kws.append("menu variety")
        if features.get("hygiene_focus"):
            kws.append("hygiene")
        if features.get("location_focus"):
            kws.append("location convenience")
        if features.get("food_texture_focus"):
            kws.append("texture quality")
        if features.get("food_product"):
            kws.append("drink quality")
    if domain == "fashion":
        if features.get("material_focus"):
            kws.append("material quality")
        if features.get("fit_focus"):
            kws.append("fit")
        if features.get("size_focus"):
            kws.append("size accuracy")
        if features.get("fashion_comfort_focus"):
            kws.append("comfort")
        if features.get("durability_focus"):
            kws.append("durability")
        if features.get("style_focus"):
            kws.append("style versatility")
        if features.get("care_focus"):
            kws.append("care requirement")
        if features.get("fashion_product"):
            kws.append("value for money")

    if features.get("price_thb"):
        kws.append("budget value")

    return kws


def filter_ml_keywords(keywords: List[str], domain: str) -> List[str]:
    if not keywords:
        return []

    allowed_domain_tokens = {
        "mouse": {
            "mouse", "เมาส์", "sensor", "dpi", "polling", "fps", "wireless",
            "battery", "ergonomic", "line", "collection", "latency", "software",
            "dongle", "lightweight", "gaming", "shape", "click", "usb"
        },
        "keyboard": {
            "keyboard", "switch", "keycap", "gasket", "hotswap", "rgb", "typing", "sound"
        },
        "audio": {
            "headset", "earphone", "earbuds", "microphone", "noise", "latency", "driver", "bass"
        },
        "smartphone": {
            "smartphone", "phone", "camera", "chip", "snapdragon", "dimensity", "battery",
            "display", "oled", "amoled", "refresh", "charging", "watt", "thermal", "stabilization"
        },
        "food_drink": {
            "food", "drink", "taste", "flavor", "sweet", "salty", "spicy", "portion", "menu",
            "restaurant", "cafe", "service", "hygiene", "delivery", "location", "price"
        },
        "fashion": {
            "fashion", "outfit", "shirt", "pants", "dress", "shoe", "sneaker", "bag", "material",
            "fabric", "fit", "size", "comfort", "durable", "style", "look"
        },
        "skincare": {
            "skincare", "serum", "moisturizer", "cleanser", "sunscreen", "spf", "retinol",
            "niacinamide", "vitamin", "aha", "bha", "pha", "ceramide", "hyaluronic",
            "acne", "brightening", "hydration", "barrier", "texture", "fragrance"
        },
        "general": set(),
    }

    domain_tokens = allowed_domain_tokens.get(domain, set())
    cleaned = []
    seen = set()

    for kw in keywords:
        k = normalize_space(clean_text(kw.lower()))
        if not k:
            continue

        # Canonical rescue for noisy phrases
        if "line collection" in k:
            k = "line collection mode"
        elif "fps" in k:
            k = "fps gaming"
        elif re.search(r"\b8k\b|\b8000\b", k):
            k = "high dpi sensor"

        words = k.split()
        if len(words) == 0 or len(words) > 4:
            continue
        if len(k) < 4:
            continue

        # Remove obvious gibberish chunks from ASR/keyword model.
        if re.search(r"[ก-๙]{1,2}\s", k):
            continue
        if re.search(r"(นะคร|ปกรณ|เวณได|เกรมม|ดโหมด)", k):
            continue

        if domain_tokens:
            if not any(tok in k for tok in domain_tokens):
                # Keep product-like model names even if not in token list.
                if not re.search(r"\b[a-z]{1,8}\d{2,5}[a-z0-9\-]*\b", k):
                    continue

        if k not in seen:
            seen.add(k)
            cleaned.append(k)

    return cleaned


def normalize_keywords(keywords: List[str]) -> List[str]:
    results: List[str] = []
    seen = set()

    for kw in keywords:
        if not kw:
            continue
        canon = CANONICAL.get(kw.strip().lower(), kw.strip().lower())
        canon = normalize_space(canon)
        if len(canon) < 3:
            continue
        if canon not in seen:
            seen.add(canon)
            results.append(canon)

    return results


def dedupe_redundant_keywords(keywords: List[str]) -> List[str]:
    # Keep the more specific phrase when one is a substring of another.
    sorted_keywords = sorted(set(keywords), key=lambda x: (-len(x), x))
    kept = []
    for kw in sorted_keywords:
        if any(kw in existing for existing in kept):
            continue
        kept.append(kw)
    return kept


def keyword_evidence_score(text: str, keyword: str) -> float:
    low_text = text.lower()
    low_kw = keyword.lower()
    freq = low_text.count(low_kw)

    if freq > 0:
        return min(1.0, 0.35 + (0.12 * freq))

    # Approx evidence by token overlap.
    kw_tokens = [t for t in low_kw.split() if len(t) > 2]
    if not kw_tokens:
        return 0.0
    overlap = sum(1 for t in kw_tokens if t in low_text)
    if overlap == 0:
        return 0.0
    return min(0.9, 0.2 + (0.18 * overlap))


def rank_score_to_confidence(raw_score: float) -> float:
    # Convert open-ended ranking score to bounded confidence with variation.
    try:
        s = float(raw_score)
    except Exception:
        return 0.5
    return max(0.45, min(0.9, 0.35 + (0.22 * s)))


def is_product_like_keyword(keyword: str) -> bool:
    kw = keyword.lower().strip()
    if re.search(r"\b[a-z]{1,10}\d{2,5}[a-z0-9\-]*\b", kw):
        return True
    brand_count = sum(1 for b in BRANDS if b in kw)
    return brand_count > 0 and len(kw.split()) >= 2


def to_comparable_keyword(domain: str, keyword: str) -> Optional[str]:
    kw = keyword.lower().strip()

    if domain == "mouse":
        if "dpi" in kw:
            return "dpi"
        if "polling" in kw or "hz" in kw:
            return "polling rate"
        if "lightweight" in kw or "weight" in kw or "gram" in kw:
            return "weight"
        if "battery" in kw:
            return "battery life"
        if "wireless" in kw:
            return "wireless"
        if "bluetooth" in kw:
            return "bluetooth"
        if "sensor" in kw:
            return "sensor performance"
        if "latency" in kw:
            return "click latency"
        if "tracking" in kw or "line collection" in kw:
            return "tracking stability"
        if "ergonomic" in kw or "shape" in kw or "comfort" in kw:
            return "ergonomics"
        if "software" in kw or "driver" in kw:
            return "software tuning"
        if "build" in kw:
            return "build quality"

    if domain == "keyboard":
        if "switch" in kw:
            return "switch type"
        if "hot swappable" in kw:
            return "switch type"
        if "layout" in kw or "75%" in kw or "tkl" in kw:
            return "layout"
        if "typing" in kw:
            return "typing feel"
        if "sound" in kw:
            return "sound profile"
        if "wireless" in kw or "wired" in kw or "connectivity" in kw:
            return "connectivity"
        if "battery" in kw:
            return "battery life"
        if "software" in kw or "driver" in kw:
            return "software tuning"
        if "build" in kw or "gasket" in kw:
            return "build quality"

    if domain == "audio":
        if "microphone" in kw:
            return "microphone quality"
        if "soundstage" in kw:
            return "soundstage"
        if "latency" in kw:
            return "latency"
        if "noise" in kw:
            return "noise cancelling"
        if "battery" in kw:
            return "battery life"
        if "comfort" in kw or "wear comfort" in kw:
            return "comfort"
        if "wireless" in kw or "bluetooth" in kw or "wired" in kw or "connectivity" in kw:
            return "connectivity"
        if "sound" in kw or "bass" in kw:
            return "sound quality"
        if "value" in kw or "budget" in kw or "price" in kw:
            return "value for money"

    if domain == "skincare":
        if "retinol" in kw or "niacinamide" in kw or "vitamin c" in kw or "aha" in kw or "bha" in kw or "ceramide" in kw or "hyaluronic" in kw:
            return "active ingredients"
        if "percent" in kw or "%" in kw or "concentration" in kw:
            return "concentration"
        if "hydrat" in kw or "moist" in kw:
            return "hydration"
        if "barrier" in kw or "ceramide" in kw:
            return "barrier support"
        if "acne" in kw or "oil control" in kw:
            return "acne control"
        if "bright" in kw or "tone" in kw:
            return "brightening"
        if "spf" in kw or "pa+" in kw or "sunscreen" in kw:
            return "sun protection"
        if "irrit" in kw or "fragrance" in kw or "alcohol" in kw:
            return "irritation risk"
        if "sensitive skin" in kw or "skin type" in kw or "non-comedogenic" in kw:
            return "skin compatibility"
        if "texture" in kw or "finish" in kw or "sticky" in kw:
            return "texture finish"

    if domain == "smartphone":
        if any(term in kw for term in ["camera", "กล้อง", "ถ่ายภาพ", "ถ่ายรูป", "ภาพ", "เลนส์", "เซนเซอร์"]):
            return "camera quality"
        if any(term in kw for term in ["chip", "snapdragon", "dimensity", "mediatek", "exynos", "ชิป", "ประมวลผล"]):
            return "chip performance"
        if any(term in kw for term in ["battery", "แบต", "ความอึด", "มิลลิแอมป์"]):
            return "battery life"
        if any(term in kw for term in ["display", "oled", "amoled", "screen", "จอ", "ความสว่าง", "นิต"]):
            return "display quality"
        if any(term in kw for term in ["charge", "charging", "watt", "ชาร์จ", "วัตต์"]):
            return "charging speed"
        if any(term in kw for term in ["thermal", "heat", "cooling", "cooler", "ความร้อน", "ร้อน", "พัดลม"]):
            return "thermal control"
        if "stabilization" in kw or "ois" in kw or "กันสั่น" in kw:
            return "stabilization"
        if "build" in kw:
            return "build quality"
        if "software" in kw or "update" in kw:
            return "software support"
        if "value" in kw or "budget" in kw:
            return "value for money"

    if domain == "food_drink":
        if "taste" in kw or "flavor" in kw:
            return "taste profile"
        if "portion" in kw:
            return "portion size"
        if "value" in kw or "budget" in kw or "price" in kw:
            return "value for money"
        if "location" in kw:
            return "location convenience"
        if "service" in kw:
            return "service quality"
        if "menu" in kw:
            return "menu variety"
        if "texture" in kw:
            return "texture quality"
        if "drink" in kw:
            return "drink quality"
        if "hygiene" in kw or "clean" in kw:
            return "hygiene"

    if domain == "fashion":
        if "material" in kw or "fabric" in kw:
            return "material quality"
        if "fit" == kw or "fit " in kw:
            return "fit"
        if "size" in kw:
            return "size accuracy"
        if "comfort" in kw:
            return "comfort"
        if "durable" in kw or "durability" in kw:
            return "durability"
        if "style" in kw or "versatile" in kw:
            return "style versatility"
        if "care" in kw or "wash" in kw:
            return "care requirement"
        if "value" in kw or "budget" in kw:
            return "value for money"

    return None


def build_comparison_profile(domain: str, features: Dict[str, object], ranked_keywords: List[Dict[str, float]], text: str):
    comparable_score: Dict[str, float] = {}
    evidence_text = text.lower()
    inferred_values: Dict[str, object] = {}

    def add_comp(name: str, score: float):
        current = comparable_score.get(name, 0.0)
        comparable_score[name] = max(current, float(score))

    if domain == "mouse":
        if features.get("dpi") is not None:
            add_comp("dpi", 1.0)
        if features.get("polling_rate_hz") is not None:
            add_comp("polling rate", 1.0)
        if features.get("weight_g") is not None:
            add_comp("weight", 1.0)
        if features.get("battery_hours") is not None or features.get("battery_claim_long"):
            add_comp("battery life", 0.95)
        if features.get("wireless"):
            add_comp("wireless", 0.95)
        if features.get("bluetooth"):
            add_comp("bluetooth", 0.95)
        if features.get("line_collection"):
            add_comp("tracking stability", 0.92)
        if features.get("ergonomic_claim"):
            add_comp("ergonomics", 0.9)
    elif domain == "keyboard":
        if features.get("switch_type") or features.get("hot_swap"):
            add_comp("switch type", 0.95)
        if features.get("layout"):
            add_comp("layout", 0.95)
        if features.get("gasket") or features.get("keycap_quality"):
            add_comp("build quality", 0.9)
        if features.get("connection_mode") == "wired":
            add_comp("connectivity", 0.9)
            inferred_values["connectivity"] = "wired"
        elif features.get("connection_mode") in {"wireless", "tri-mode"}:
            add_comp("connectivity", 0.95)
            inferred_values["connectivity"] = features.get("connection_mode")
        if any(features.get(k) for k in ["supports_windows", "supports_mac", "supports_android", "supports_ios"]):
            add_comp("software tuning", 0.75)
        if features.get("battery_hours"):
            add_comp("battery life", 0.9)
    elif domain == "audio":
        if features.get("noise_cancelling"):
            add_comp("noise cancelling", 0.92)
        if features.get("wireless") or features.get("bluetooth"):
            add_comp("connectivity", 0.9)
        elif features.get("connection_mode") == "wired":
            add_comp("connectivity", 0.86)
        if features.get("battery_hours") or features.get("battery_claim_long"):
            add_comp("battery life", 0.85)
        if features.get("mic_focus"):
            add_comp("microphone quality", 0.88)
        if features.get("soundstage"):
            add_comp("soundstage", 0.88)
            add_comp("sound quality", 0.82)
        if features.get("comfort"):
            add_comp("comfort", 0.82)
        if features.get("low_latency"):
            add_comp("latency", 0.85)
        if features.get("price_thb"):
            add_comp("value for money", 0.84)
    elif domain == "skincare":
        if features.get("active_ingredients"):
            add_comp("active ingredients", 0.95)
        if features.get("concentration_percent"):
            add_comp("concentration", 0.9)
        if features.get("hydration_claim"):
            add_comp("hydration", 0.88)
        if features.get("barrier_claim"):
            add_comp("barrier support", 0.88)
        if features.get("acne_claim"):
            add_comp("acne control", 0.88)
        if features.get("brightening_claim"):
            add_comp("brightening", 0.88)
        if features.get("sun_protection"):
            add_comp("sun protection", 0.92)
        if features.get("low_irritation_claim"):
            add_comp("irritation risk", 0.85)
        if features.get("texture_claim"):
            add_comp("texture finish", 0.82)
        if features.get("skincare_product"):
            add_comp("skin compatibility", 0.8)
    elif domain == "smartphone":
        if features.get("camera_focus"):
            add_comp("camera quality", 0.92)
        if features.get("chip_focus"):
            add_comp("chip performance", 0.92)
        if features.get("battery_hours") or features.get("battery_mah") or features.get("battery_claim_long"):
            add_comp("battery life", 0.88)
        if features.get("display_focus"):
            add_comp("display quality", 0.9)
        if features.get("charging_focus"):
            add_comp("charging speed", 0.88)
        if features.get("thermal_focus"):
            add_comp("thermal control", 0.85)
        if features.get("stabilization_focus"):
            add_comp("stabilization", 0.85)
        if features.get("smartphone_product"):
            add_comp("software support", 0.8)
    elif domain == "food_drink":
        if features.get("taste_focus"):
            add_comp("taste profile", 0.92)
        if features.get("portion_focus"):
            add_comp("portion size", 0.9)
        if features.get("price_thb"):
            add_comp("value for money", 0.86)
        if features.get("location_focus"):
            add_comp("location convenience", 0.84)
        if features.get("service_focus"):
            add_comp("service quality", 0.86)
        if features.get("menu_focus"):
            add_comp("menu variety", 0.82)
        if features.get("food_texture_focus"):
            add_comp("texture quality", 0.85)
        if features.get("food_product"):
            add_comp("drink quality", 0.8)
    elif domain == "fashion":
        if features.get("material_focus"):
            add_comp("material quality", 0.9)
        if features.get("fit_focus"):
            add_comp("fit", 0.9)
        if features.get("size_focus"):
            add_comp("size accuracy", 0.88)
        if features.get("fashion_comfort_focus"):
            add_comp("comfort", 0.88)
        if features.get("durability_focus"):
            add_comp("durability", 0.86)
        if features.get("style_focus"):
            add_comp("style versatility", 0.85)
        if features.get("care_focus"):
            add_comp("care requirement", 0.82)
        if features.get("price_thb"):
            add_comp("value for money", 0.84)

    for item in ranked_keywords:
        kw = item["keyword"]
        mapped = to_comparable_keyword(domain, kw)
        if mapped:
            score = rank_score_to_confidence(item["score"])
            if domain == "mouse" and mapped in {"wireless", "bluetooth"} and not features.get(mapped):
                score = min(score, 0.7)
            if domain == "keyboard" and mapped == "connectivity" and not features.get("connection_mode"):
                score = min(score, 0.7)
            if domain == "smartphone" and mapped in {"charging speed", "thermal control", "stabilization"} and not features.get("charging_focus") and not features.get("thermal_focus") and not features.get("stabilization_focus"):
                score = min(score, 0.72)
            add_comp(mapped, score)

    hint_map = {
        "dpi": ["dpi", "8k", "8000"],
        "polling rate": ["hz", "polling"],
        "weight": ["gram", "g ", "lightweight"],
        "battery life": ["battery", "แบต", "แบตเตอรี่", "ความอึด", "มิลลิแอมป์", "hours"],
        "wireless": ["wireless", "dongle"],
        "ergonomics": ["ergonomic", "shape", "comfort"],
        "tracking stability": ["line collection", "tracking", "stable"],
        "connectivity": ["wired", "wireless", "bluetooth", "dongle", "usb cable"],
        "layout": ["60%", "65%", "75%", "80%", "tkl"],
        "switch type": ["switch", "hot swap", "linear", "tactile", "clicky"],
        "microphone quality": ["microphone", "mic", "voice"],
        "soundstage": ["soundstage", "spatial audio"],
        "comfort": ["comfort", "wear comfort"],
        "active ingredients": ["retinol", "niacinamide", "vitamin c", "aha", "bha", "ceramide", "hyaluronic"],
        "concentration": ["%", "percent", "concentration"],
        "hydration": ["hydration", "moist", "humectant"],
        "barrier support": ["barrier", "ceramide"],
        "acne control": ["acne", "oil control", "salicylic"],
        "brightening": ["bright", "dark spot", "tone"],
        "sun protection": ["spf", "pa+", "sunscreen"],
        "irritation risk": ["fragrance", "alcohol", "irritation", "sensitive skin"],
        "skin compatibility": ["sensitive skin", "skin type", "non-comedogenic"],
        "texture finish": ["texture", "finish", "sticky", "absorb"],
        "camera quality": ["camera", "photo", "video", "portrait", "night mode", "กล้อง", "ถ่ายภาพ", "ถ่ายรูป", "ภาพ", "เลนส์", "เซนเซอร์"],
        "chip performance": ["chip", "snapdragon", "dimensity", "mediatek", "exynos", "benchmark", "ชิป", "ประมวลผล"],
        "display quality": ["display", "screen", "oled", "amoled", "brightness", "จอ", "หน้าจอ", "ความสว่าง", "นิต"],
        "charging speed": ["fast charge", "watt", "charge", "ชาร์จไว", "ชาร์จเร็ว", "วัตต์"],
        "thermal control": ["thermal", "heat", "cooling", "cooler", "throttle", "ระบายความร้อน", "ความร้อน", "ร้อน", "พัดลม"],
        "stabilization": ["ois", "stabilization", "shake", "กันสั่น"],
        "software support": ["software", "update", "ui"],
        "value for money": ["budget", "value", "price"],
        "taste profile": ["taste", "flavor", "sweet", "salty", "spicy"],
        "portion size": ["portion", "serving", "จานใหญ่"],
        "location convenience": ["location", "parking", "เดินทาง"],
        "service quality": ["service", "staff", "พนักงาน"],
        "menu variety": ["menu", "variety", "เมนู"],
        "texture quality": ["texture", "crispy", "หนึบ", "กรอบ"],
        "drink quality": ["drink", "beverage", "coffee", "ชา"],
        "hygiene": ["clean", "hygiene", "สะอาด"],
        "material quality": ["material", "fabric", "ผ้า", "วัสดุ"],
        "fit": ["fit", "tailor", "ทรง"],
        "size accuracy": ["size", "ไซซ์", "size chart"],
        "durability": ["durable", "stitch", "เย็บ", "ทน"],
        "style versatility": ["style", "match", "แต่งตัว"],
        "care requirement": ["care", "wash", "dry clean", "ซัก"],
    }
    for comp, hints in hint_map.items():
        if comp not in comparable_score and any(h in evidence_text for h in hints):
            add_comp(comp, INFERRED_CONFIDENCE)
            if comp in {"wireless", "battery life", "tracking stability", "ergonomics", "connectivity"}:
                inferred_values[comp] = "inferred"

    comparable_keywords = sorted(comparable_score.keys(), key=lambda k: comparable_score[k], reverse=True)

    allowed = COMPARABLE_KEYWORDS_BY_DOMAIN.get(domain, set())
    if allowed:
        comparable_keywords = [k for k in comparable_keywords if k in allowed]

    dimensions = []
    for name in comparable_keywords:
        value = None
        if name == "dpi":
            value = features.get("dpi")
        elif name == "polling rate":
            value = features.get("polling_rate_hz")
        elif name == "weight":
            value = features.get("weight_g")
        elif name == "battery life":
            value = features.get("battery_hours") or ("claim_long" if features.get("battery_claim_long") else None)
        elif name == "wireless":
            value = True if features.get("wireless") is True else inferred_values.get("wireless")
        elif name == "bluetooth":
            value = True if features.get("bluetooth") is True else None
        elif domain == "keyboard" and name == "switch type":
            value = features.get("switch_type") or ("hot_swap" if features.get("hot_swap") else None)
        elif domain == "keyboard" and name == "layout":
            value = features.get("layout")
        elif domain == "keyboard" and name == "connectivity":
            if features.get("connection_mode") == "wired":
                value = "wired"
            elif features.get("connection_mode") in {"wireless", "tri-mode"}:
                value = features.get("connection_mode")
            else:
                value = inferred_values.get("connectivity")
        elif domain == "audio" and name == "connectivity":
            if features.get("connection_mode") == "wired":
                value = "wired"
            elif features.get("connection_mode") in {"wireless", "tri-mode"}:
                value = features.get("connection_mode")
            elif features.get("wireless") or features.get("bluetooth"):
                value = True
            else:
                value = inferred_values.get("connectivity")
        elif name == "latency":
            value = "low_latency" if features.get("low_latency") else None
        elif name == "microphone quality":
            value = "mentioned" if features.get("mic_focus") else None
        elif name == "soundstage":
            value = "mentioned" if features.get("soundstage") else None
        elif name == "sound quality":
            if any(k in evidence_text for k in ["sound quality", "bass"]) or (
                domain == "audio"
                and comparable_score.get("sound quality", 0.0) >= 0.8
                and (features.get("soundstage") or features.get("audio_product"))
            ):
                value = "mentioned"
            else:
                value = None
        elif name == "comfort":
            value = "mentioned" if features.get("comfort") else None
        elif domain == "skincare" and name == "active ingredients":
            value = features.get("active_ingredients")
        elif domain == "skincare" and name == "concentration":
            value = features.get("concentration_percent")
        elif domain == "skincare" and name == "hydration":
            value = "mentioned" if features.get("hydration_claim") else None
        elif domain == "skincare" and name == "barrier support":
            value = "mentioned" if features.get("barrier_claim") else None
        elif domain == "skincare" and name == "acne control":
            value = "mentioned" if features.get("acne_claim") else None
        elif domain == "skincare" and name == "brightening":
            value = "mentioned" if features.get("brightening_claim") else None
        elif domain == "skincare" and name == "sun protection":
            value = "mentioned" if features.get("sun_protection") else None
        elif domain == "skincare" and name == "irritation risk":
            value = "mentioned" if features.get("low_irritation_claim") else None
        elif domain == "skincare" and name == "skin compatibility":
            value = "mentioned" if features.get("skincare_product") else None
        elif domain == "skincare" and name == "texture finish":
            value = "mentioned" if features.get("texture_claim") else None
        elif domain == "smartphone" and name == "camera quality":
            value = "mentioned" if features.get("camera_focus") else None
        elif domain == "smartphone" and name == "chip performance":
            value = "mentioned" if features.get("chip_focus") else None
        elif domain == "smartphone" and name == "display quality":
            value = "mentioned" if features.get("display_focus") else None
        elif domain == "smartphone" and name == "charging speed":
            value = "mentioned" if features.get("charging_focus") else None
        elif domain == "smartphone" and name == "thermal control":
            value = "mentioned" if features.get("thermal_focus") else None
        elif domain == "smartphone" and name == "stabilization":
            value = "mentioned" if features.get("stabilization_focus") else None
        elif name == "value for money":
            if features.get("price_thb"):
                value = features.get("price_thb")
            elif any(k in evidence_text for k in ["value", "budget", "price", "คุ้ม", "ไม่แพง", "งบ"]):
                value = "mentioned"
            else:
                value = None
        elif domain == "smartphone" and name == "software support":
            value = "mentioned" if features.get("smartphone_product") else None
        elif domain == "food_drink" and name == "taste profile":
            value = "mentioned" if features.get("taste_focus") else None
        elif domain == "food_drink" and name == "portion size":
            value = "mentioned" if features.get("portion_focus") else None
        elif domain == "food_drink" and name == "location convenience":
            value = "mentioned" if features.get("location_focus") else None
        elif domain == "food_drink" and name == "service quality":
            value = "mentioned" if features.get("service_focus") else None
        elif domain == "food_drink" and name == "menu variety":
            value = "mentioned" if features.get("menu_focus") else None
        elif domain == "food_drink" and name == "texture quality":
            value = "mentioned" if features.get("food_texture_focus") else None
        elif domain == "food_drink" and name == "drink quality":
            value = "mentioned" if features.get("food_product") else None
        elif domain == "food_drink" and name == "hygiene":
            value = "mentioned" if features.get("hygiene_focus") else None
        elif domain == "fashion" and name == "material quality":
            value = "mentioned" if features.get("material_focus") else None
        elif domain == "fashion" and name == "fit":
            value = "mentioned" if features.get("fit_focus") else None
        elif domain == "fashion" and name == "size accuracy":
            value = "mentioned" if features.get("size_focus") else None
        elif domain == "fashion" and name == "durability":
            value = "mentioned" if features.get("durability_focus") else None
        elif domain == "fashion" and name == "style versatility":
            value = "mentioned" if features.get("style_focus") else None
        elif domain == "fashion" and name == "care requirement":
            value = "mentioned" if features.get("care_focus") else None
        elif name in inferred_values:
            value = inferred_values[name]

        dimensions.append(
            {
                "name": name,
                "confidence": round(float(comparable_score[name]), 3),
                "value": value,
            }
        )

    return comparable_keywords, dimensions


def classify_dimension_status(name: str, confidence: float, value) -> str:
    if name in {"wireless", "bluetooth", "connectivity"} and value in {None, "inferred"}:
        return "weak" if confidence > 0.0 else "missing"
    if name in {
        "sound quality", "soundstage", "microphone quality", "comfort",
        "hydration", "barrier support", "acne control", "brightening",
        "sun protection", "irritation risk", "skin compatibility", "texture finish",
        "camera quality", "chip performance", "display quality", "charging speed",
        "thermal control", "stabilization", "software support", "taste profile",
        "portion size", "location convenience", "service quality", "menu variety",
        "texture quality", "drink quality", "hygiene", "material quality", "fit",
        "size accuracy", "durability", "style versatility", "care requirement",
        "value for money", "build quality", "software tuning"
    } and value is None:
        return "weak" if confidence > 0.0 else "missing"
    if isinstance(value, bool):
        return "present"
    if isinstance(value, (int, float)) and value > 0:
        return "present"
    if value == "mentioned":
        return "present"
    if value == "inferred":
        return "weak"
    if confidence >= PRESENT_THRESHOLD:
        return "present"
    if confidence > 0.0:
        return "weak"
    return "missing"


def build_dimension_status(domain: str, comparison_dimensions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    expected = DOMAIN_DIMENSIONS_ORDER.get(domain, [])
    dim_map = {d["name"]: d for d in comparison_dimensions}
    status_rows: List[Dict[str, object]] = []

    for name in expected:
        d = dim_map.get(name)
        if d is None:
            status_rows.append(
                {
                    "name": name,
                    "status": "missing",
                    "confidence": 0.0,
                    "value": None,
                }
            )
            continue

        confidence = float(d.get("confidence", 0.0))
        value = d.get("value")
        status_rows.append(
            {
                "name": name,
                "status": classify_dimension_status(name, confidence, value),
                "confidence": round(confidence, 3),
                "value": value,
            }
        )

    return status_rows


def enforce_domain_priority(domain: str, ranked: List[Dict[str, float]], fallback_keywords: List[str]) -> List[Dict[str, float]]:
    if domain not in DOMAIN_PRIORITY:
        return ranked

    profile = DOMAIN_PRIORITY[domain]
    present = {item["keyword"] for item in ranked}

    # Ensure at least one foundational keyword exists.
    if not any(k in present for k in profile["must_have_any"]):
        for k in profile["must_have_any"]:
            if k in fallback_keywords and k not in present:
                ranked.append({"keyword": k, "score": 0.72})
                present.add(k)
                break

    # Soft add preferred keywords if there is room.
    for k in profile["prefer"]:
        if len(ranked) >= 18:
            break
        if k in fallback_keywords and k not in present:
            ranked.append({"keyword": k, "score": 0.58})
            present.add(k)

    return ranked


def extract_rule_keywords_from_text(text: str) -> List[str]:
    low = normalize_asr_terms(text.lower())
    candidates = []

    rule_map = {
        "unboxing": ["unboxing", "box contents"],
        "latency": ["low latency"],
        "build quality": ["build quality"],
        "software": ["software support"],
        "driver": ["driver tuning"],
        "microphone": ["microphone quality"],
        "typing": ["typing feel"],
        "sound": ["sound profile"],
        "fps": ["fps gaming"],
        "line collection": ["line collection mode", "tracking stability"],
        "hot swap": ["hot swappable", "switch type"],
        "switch": ["switch type"],
        "75%": ["layout"],
        "wired": ["wired connectivity"],
        "wireless": ["wireless connectivity"],
        "bluetooth": ["connectivity"],
        "headset": ["connectivity", "microphone quality"],
        "earbuds": ["connectivity", "sound quality"],
        "iem": ["connectivity", "sound quality"],
        "หูฟัง": ["connectivity", "sound quality"],
        "ไมโครโฟน": ["microphone quality"],
        "ไมค์": ["microphone quality"],
        "เวทีเสียง": ["soundstage"],
        "เสียงปืน": ["soundstage"],
        "ฝีเท้า": ["soundstage"],
        "noise cancelling": ["noise cancelling"],
        "soundstage": ["soundstage"],
        "comfort": ["comfort"],
        "serum": ["active ingredients", "skin compatibility"],
        "moisturizer": ["hydration", "barrier support"],
        "sunscreen": ["sun protection", "skin compatibility"],
        "spf": ["sun protection"],
        "retinol": ["active ingredients"],
        "niacinamide": ["active ingredients", "brightening"],
        "vitamin c": ["active ingredients", "brightening"],
        "aha": ["active ingredients", "texture finish"],
        "bha": ["active ingredients", "acne control"],
        "acne": ["acne control"],
        "fragrance free": ["irritation risk"],
        "sensitive skin": ["skin compatibility"],
        "camera": ["camera quality"],
        "snapdragon": ["chip performance"],
        "dimensity": ["chip performance"],
        "display": ["display quality"],
        "oled": ["display quality"],
        "fast charge": ["charging speed"],
        "thermal": ["thermal control"],
        "ois": ["stabilization"],
        "taste": ["taste profile"],
        "flavor": ["taste profile"],
        "portion": ["portion size"],
        "restaurant": ["location convenience", "service quality"],
        "menu": ["menu variety"],
        "hygiene": ["hygiene"],
        "fabric": ["material quality"],
        "fit": ["fit"],
        "size": ["size accuracy"],
        "durable": ["durability"],
        "style": ["style versatility"],
        "wash": ["care requirement"],
        "overpowered": ["competitive advantage"],
        "stable": ["tracking stability"],
        "ergonomic": ["ergonomic design"],
        "54g": ["ultra lightweight"],
        "dongle": ["wireless connectivity"],
    }

    for trigger, kws in rule_map.items():
        if trigger in low:
            candidates.extend(kws)

    return candidates


# =========================
# Visual Fallback
# =========================
def visual_context(video_path: str, max_frames: int = 6) -> Tuple[str, List[str]]:
    if os.getenv("ANALYZE_ENABLE_VISUAL", "0").strip().lower() not in {"1", "true", "yes"}:
        return "", []
    if detect_scenes is None:
        return "", []

    try:
        # Lazy import so API can start even if visual deps are not installed yet.
        from models.frame_extract import extract_frames
        from models.blip_caption import caption_image

        scenes = detect_scenes(video_path)
        if not scenes:
            return "", []

        frames = extract_frames(video_path, scenes[:max_frames])
        if not frames:
            return "", []

        captions = []
        for frame in frames:
            try:
                cap = caption_image(frame)
            except Exception:
                cap = ""
            cap = normalize_space(cap)
            if cap:
                captions.append(cap)

        return " ".join(captions), captions
    except Exception:
        return "", []


def keyword_frequency_boost(text: str, keywords: List[str]) -> Dict[str, float]:
    low = text.lower()
    boosts = {}
    for kw in keywords:
        token = kw.lower()
        if len(token) < 3:
            continue
        freq = low.count(token)
        if freq > 0:
            boosts[kw] = min(0.45, 0.1 * freq)
    return boosts


# =========================
# Local keyword extractor (KeyBERT -> TF-IDF -> frequency fallback)
# =========================

def _local_extract_keywords(text: str, top_k: int = 15, domain: str | None = None) -> list:
    """Try KeyBERT if available; otherwise TF-IDF n-grams; final fallback: simple frequency.
    Returns list of keyword strings.
    """
    text = (text or "").strip()
    if not text:
        return []

    # 1) KeyBERT if installed
    try:
        from keybert import KeyBERT

        try:
            kb = KeyBERT()
            kw = kb.extract_keywords(text, keyphrase_ngram_range=(1, 2), stop_words=None, top_n=top_k)
            return [k for k, s in kw]
        except Exception:
            # fall through to TF-IDF
            pass
    except Exception:
        pass

    # 2) TF-IDF n-grams (sklearn)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        # For Thai, if pythainlp tokenizer available, use it to pre-tokenize to space-separated tokens
        try:
            if pythai_word_tokenize:
                tokens = pythai_word_tokenize(text)
                text_for_tfidf = " ".join(tokens)
            else:
                text_for_tfidf = text
        except Exception:
            text_for_tfidf = text

        vec = TfidfVectorizer(ngram_range=(1, 2), max_df=0.85, min_df=1)
        X = vec.fit_transform([text_for_tfidf])
        features = vec.get_feature_names_out()
        scores = X.toarray().sum(axis=0)
        paired = sorted(zip(features, scores), key=lambda x: -x[1])[:top_k]
        return [f for f, s in paired]
    except Exception:
        pass

    # 3) Frequency-based fallback
    try:
        if pythai_word_tokenize:
            toks = pythai_word_tokenize(text)
        else:
            toks = re.findall(r"[\u0E00-\u0E7Fa-z0-9]+", text)
        freq: Dict[str, int] = {}
        for t in toks:
            t = t.strip().lower()
            if not t or len(t) < 2:
                continue
            freq[t] = freq.get(t, 0) + 1
        items = sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:top_k]
        return [k for k, v in items]
    except Exception:
        return []


# =========================
# Main Pipeline
# =========================
def analyze_video(
    video_path: str,
    display_name: str | None = None,
    hook_duration_seconds: int = 60,
    asr_model_size: str | None = None,
):
    print(f"[pipeline] analyze_video start: {video_path}", flush=True)
    # Lazy import heavy NLP models to avoid failing app startup
    # when model files are not cached yet.
    from models.speech_to_text import transcribe_with_meta

    keybert_keywords = None
    rank_keywords = None
    semantic_keywords = None
    ml_import_ok = True

    enable_ml_keywords = os.getenv("ANALYZE_ENABLE_ML_KEYWORDS", "0").strip().lower() in {"1", "true", "yes"}
    try:
        if enable_ml_keywords:
            print("[pipeline] loading ML keyword models...", flush=True)
            from models.keyword_ai import extract_keywords as keybert_keywords
            from models.keyword_ranker import rank_keywords
            from models.semantic_keyword import semantic_keywords
        else:
            print("[pipeline] ML keyword models disabled; using fast rule/local analysis", flush=True)
            ml_import_ok = False
    except Exception as exc:
        print(f"[pipeline] ML model import failed: {exc}", flush=True)
        ml_import_ok = False

    hook_seconds = max(5, min(int(hook_duration_seconds or 60), 300))
    with tempfile.NamedTemporaryFile(
        prefix="content_ai_",
        suffix=".wav",
        delete=False,
    ) as audio_file:
        audio_path = audio_file.name
    try:
        print("[pipeline] extracting audio from full video...", flush=True)
        update_current_job(
            stage="extracting_audio",
            progress=24,
            message="Extracting audio from full video",
        )
        audio_ok = extract_audio(video_path, audio_path)

        print("[pipeline] transcribing audio...", flush=True)
        update_current_job(
            stage="transcribing",
            progress=38,
            message="Transcribing full video",
        )
        if audio_ok:
            try:
                stt = transcribe_with_meta(audio_path, model_size=asr_model_size)
            except Exception as exc:
                print(f"[pipeline] STT failed: {exc}", flush=True)
                if asr_model_size is not None:
                    raise RuntimeError(f"Whisper {asr_model_size} could not transcribe this clip") from exc
                stt = {
                    "text": "",
                    "language": None,
                    "language_probability": None,
                    "segment_count": 0,
                    "avg_no_speech_prob": 1.0,
                    "segments": [],
                    "fallback_reason": str(exc),
                }
        else:
            stt = {
                "text": "",
                "language": None,
                "language_probability": None,
                "segment_count": 0,
                "avg_no_speech_prob": 1.0,
                "segments": [],
                "fallback_reason": "audio_extraction_failed",
            }
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass

    update_current_job(
        stage="normalizing_transcript",
        progress=48,
        message="Cleaning and validating transcript",
    )
    transcript = stt.get("text", "")
    if not transcript:
        fallback_source = display_name or os.path.basename(video_path)
        fallback_title = os.path.splitext(os.path.basename(fallback_source))[0].replace("_", " ").replace("-", " ")
        transcript = fallback_title
        stt["transcript_source"] = "fallback_filename"
        stt["fallback_reason"] = stt.get("fallback_reason") or "empty_stt_transcript"
        stt["warning"] = (
            "Speech-to-text failed, so the analysis uses only the uploaded filename. "
            "Classification confidence is intentionally limited."
        )
    else:
        stt["transcript_source"] = "speech_to_text"

    raw_transcript = transcript
    stt_segments = stt.get("segments") or []
    hook_raw_transcript = transcript_for_time_window(stt_segments, hook_seconds)

    cleaned_transcript = clean_text(
        normalize_asr_terms(
            remove_asr_noise(raw_transcript),
            aggressive=False,
        )
    )
    hook_cleaned_transcript = clean_text(
        normalize_asr_terms(
            remove_asr_noise(hook_raw_transcript),
            aggressive=False,
        )
    )
    clean = cleaned_transcript

    update_current_job(stage="classifying", progress=55, message="Extracting keywords and content signals")
    visual_text, captions = visual_context(video_path)
    combined_for_domain = f"{cleaned_transcript} {visual_text}".strip()

    domain = detect_domain(combined_for_domain, visual_text)
    product = extract_main_product(combined_for_domain)
    features = extract_features(combined_for_domain)
    domain = infer_domain_from_features(features, domain)

    tier_rule = feature_to_keywords(features, domain)
    tier_domain = DOMAIN_BASE.get(domain, [])
    tier_text_rule = extract_rule_keywords_from_text(combined_for_domain)

    # Candidate from embeddings (run only when rule-evidence is not enough).
    rule_signal_count = len(tier_rule) + len(tier_text_rule)
    use_ml_enrichment = ((domain == "general") or (rule_signal_count < 4)) and ml_import_ok

    keybert_candidate = []
    semantic_candidate = []

    # Prefer local extractor if ML models are not present to avoid heavy dependencies
    if use_ml_enrichment and clean:
        if keybert_keywords and semantic_keywords:
            try:
                print("[pipeline] extracting keywords with ML models...", flush=True)
                keybert_candidate = keybert_keywords(clean)
                keybert_candidate = filter_ml_keywords(keybert_candidate, domain)
                semantic_candidate = semantic_keywords(clean, keybert_candidate, top_k=15)
                semantic_candidate = filter_ml_keywords(semantic_candidate, domain)
            except Exception as e:
                print(f"[pipeline] ML keyword extraction failed: {e}, falling back to local extractor", flush=True)
                keybert_candidate = _local_extract_keywords(clean, top_k=15, domain=domain)
                keybert_candidate = filter_ml_keywords(keybert_candidate, domain)
                semantic_candidate = []
        else:
            # Use local extractor when heavy ML not available
            keybert_candidate = _local_extract_keywords(clean, top_k=15, domain=domain)
            keybert_candidate = filter_ml_keywords(keybert_candidate, domain)
            semantic_candidate = []

        # Domain relevance check: if ML/local candidate set is mostly irrelevant, fallback to rule-based candidates
        try:
            cand = [k for k in (keybert_candidate or []) if k]
            if semantic_candidate:
                cand.extend([k for k in semantic_candidate if k])
            relevant = 0
            hint_words = set()
            for item in {**SHARED_DOMAIN_HINTS, **SHARED_DOMAIN_BASE}.values():
                for v in item:
                    for tok in re.findall(r"[\u0E00-\u0E7Fa-z0-9]+", (v or "").lower()):
                        if tok:
                            hint_words.add(tok)
            for k in cand:
                toks = set(re.findall(r"[\u0E00-\u0E7Fa-z0-9]+", k.lower()))
                if len(toks & hint_words) >= 1:
                    relevant += 1
            if cand and (relevant / max(1, len(cand))) < 0.5:
                print("[pipeline] ML/local keywords not domain-relevant enough, falling back to rule-based candidates", flush=True)
                keybert_candidate = []
                semantic_candidate = []
                use_ml_enrichment = False
        except Exception:
            # If any error, keep candidates as-is
            pass

    # Candidate from visual captions for videos with low speech.
    visual_candidate = []
    if visual_text:
        visual_candidate = extract_rule_keywords_from_text(visual_text)

    all_candidates = []
    if product:
        all_candidates.append(product)
    all_candidates.extend(tier_rule)
    all_candidates.extend(tier_domain)
    all_candidates.extend(tier_text_rule)
    all_candidates.extend(keybert_candidate)
    all_candidates.extend(semantic_candidate)
    all_candidates.extend(visual_candidate)

    final_keywords = normalize_keywords(all_candidates)
    final_keywords = dedupe_redundant_keywords(final_keywords)

    ranked = []
    if final_keywords and rank_keywords:
        print("[pipeline] ranking keywords...", flush=True)
        ranked = rank_keywords(clean if clean else combined_for_domain, final_keywords)

    if not ranked:
        ranked = []
        for k in final_keywords:
            base = keyword_evidence_score(combined_for_domain, k)
            ranked.append({"keyword": k, "score": max(0.05, base)})

    freq_boost = keyword_frequency_boost(combined_for_domain, final_keywords)

    for item in ranked:
        kw = item["keyword"]

        if product and kw == product:
            item["score"] += 1.8
        elif kw in tier_rule:
            item["score"] += 1.1
        elif kw in tier_text_rule:
            item["score"] += 0.8
        elif kw in tier_domain:
            item["score"] += 0.4

        item["score"] += freq_boost.get(kw, 0.0)
        item["score"] += keyword_evidence_score(combined_for_domain, kw)

        # Penalize too-generic marketing words.
        if kw in {"competitive advantage", "budget value"}:
            item["score"] -= 0.15

    ranked = sorted(ranked, key=lambda x: x["score"], reverse=True)
    ranked = enforce_domain_priority(domain, ranked, final_keywords)
    ranked = sorted(ranked, key=lambda x: x["score"], reverse=True)

    # Split into comparable keywords vs entity/context keywords.
    entity_keywords = []
    context_keywords = []
    comparable_ranked = []

    for item in ranked:
        kw = item["keyword"]
        if is_product_like_keyword(kw):
            if kw not in entity_keywords:
                entity_keywords.append(kw)
            continue

        mapped = to_comparable_keyword(domain, kw)
        if mapped:
            comparable_ranked.append(
                {
                    "keyword": mapped,
                    "score": item["score"],
                    "source_keyword": kw,
                }
            )
        else:
            if kw not in context_keywords:
                context_keywords.append(kw)

    # Merge duplicate mapped comparable keywords and keep max score.
    merged_comp = {}
    for item in comparable_ranked:
        k = item["keyword"]
        if k not in merged_comp or item["score"] > merged_comp[k]["score"]:
            merged_comp[k] = item
    comparable_ranked = sorted(merged_comp.values(), key=lambda x: x["score"], reverse=True)

    comparable_keywords, comparison_dimensions = build_comparison_profile(
        domain=domain,
        features=features,
        ranked_keywords=ranked,
        text=combined_for_domain,
    )
    dimension_status = build_dimension_status(domain, comparison_dimensions)

    # Align top_keywords to comparable keywords for dataset comparison use.
    dim_conf = {d["name"]: float(d["confidence"]) for d in comparison_dimensions}
    top_keywords = []
    for ck in comparable_keywords:
        score = dim_conf.get(ck, keyword_evidence_score(combined_for_domain, ck))
        for item in comparable_ranked:
            if item["keyword"] == ck:
                score = max(score, float(item["score"]))
        top_keywords.append({"keyword": ck, "score": float(score)})

    # Keep stable max size.
    top_keywords = sorted(top_keywords, key=lambda x: x["score"], reverse=True)[:12]
    final_keywords = [item["keyword"] for item in top_keywords]

    # If ASR is weak, surface visual hint in title.
    weak_audio = bool(stt.get("segment_count", 0) == 0) or (stt.get("avg_no_speech_prob") or 0) > 0.65
    summary_input = clean if clean else visual_text
    summary = simple_summarize(summary_input) if summary_input else "No reliable transcript"

    if weak_audio and captions:
        summary = f"Low-speech video; visual cues: {', '.join(captions[:2])}"

    strong_count = sum(1 for d in dimension_status if d["status"] == "present")
    weak_count = sum(1 for d in dimension_status if d["status"] == "weak")
    min_ranked_by_domain = {
        "mouse": 7,
        "keyboard": 6,
        "audio": 5,
        "skincare": 5,
        "smartphone": 6,
        "food_drink": 5,
        "fashion": 5,
    }
    min_ranked = min_ranked_by_domain.get(domain, 6)

    quality_score = 0.0
    if product:
        quality_score += 0.25
    if domain != "general":
        quality_score += 0.2
    if len(features) >= 2:
        quality_score += 0.2
    if len(ranked) >= min_ranked:
        quality_score += 0.15
    if not weak_audio:
        quality_score += 0.2
    if strong_count >= 3:
        quality_score += 0.1
    elif strong_count >= 2 and weak_count >= 1:
        quality_score += 0.05

    if stt.get("transcript_source") == "fallback_filename":
        quality_score = min(quality_score, 0.25)

    return convert_numpy(
        {
            "transcript": raw_transcript,
            "raw_transcript": raw_transcript,
            "cleaned_transcript": cleaned_transcript,
            "transcript_segments": stt_segments if stt.get("transcript_source") == "speech_to_text" else [],
            "analysis": {
                "title": summary,
                "domain": domain,
                "product": product,
                "features": features,
                "top_keywords": top_keywords,
                "all_keywords": final_keywords,
                "entity_keywords": entity_keywords[:5],
                "context_keywords": context_keywords[:10],
                "hook_transcript": hook_cleaned_transcript,
                "hook_raw_transcript": hook_raw_transcript,
                "hook_cleaned_transcript": hook_cleaned_transcript,
                "comparison_dimensions": comparison_dimensions,
                "dimension_status": dimension_status,
                "recommendation_policy": {
                    "gap_delta_threshold": GAP_DELTA_THRESHOLD,
                    "present_threshold": PRESENT_THRESHOLD,
                    "weak_threshold": WEAK_THRESHOLD,
                    "inferred_confidence": INFERRED_CONFIDENCE,
                    "recommend_when_user_status": ["missing", "weak"],
                    "note": "Compare user-vs-viral by dimension confidence. Recommend when viral_conf - user_conf >= gap_delta_threshold.",
                },
                "pipeline_mode": "hybrid_full" if use_ml_enrichment else ("rule_first" if ml_import_ok else "rule_first_offline"),
                "analysis_quality": round(min(1.0, quality_score), 3),
                "stt_meta": {
                    "model_size": stt.get("model_size") or asr_model_size,
                    "device": stt.get("device"),
                    "compute_type": stt.get("compute_type"),
                    "language": stt.get("language"),
                    "language_probability": stt.get("language_probability"),
                    "segment_count": stt.get("segment_count"),
                    "avg_no_speech_prob": stt.get("avg_no_speech_prob"),
                    "weak_audio": weak_audio,
                    "transcript_source": stt.get("transcript_source"),
                    "fallback_reason": stt.get("fallback_reason"),
                    "warning": stt.get("warning"),
                    "hook_seconds_analyzed": hook_seconds,
                    "hook_segment_count": segment_count_for_time_window(
                        stt_segments,
                        hook_seconds,
                    ),
                    "transcript_scope": "full_clip",
                    "transcript_normalization": "explicit_terms_only",
                },
            },
        }
    )
