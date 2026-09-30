"""Conservative, timestamped ideas from live metadata, never transcript evidence."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.datetime_utils import utc_isoformat
from app.database.models import TrendSnapshotItem, TrendSnapshotRun
from app.services.live_trend_snapshots import _provider_status_for_run

METHOD_VERSION = "current-metadata-ideas-v1"
SNAPSHOT_MAX_AGE_HOURS = 24
VIDEO_MAX_AGE_DAYS = 7
QUERY_MAX_AGE_HOURS = 48
SUPPORTED = {"phone", "camera", "laptop"}

# Families identify products; the model number itself is not a fixed dictionary.
PRODUCTS = {
    "phone": [
        ("iphone", r"\biphone\s*\d{1,2}(?:\s*(?:pro\s*max|pro|max|plus|mini|air|e))?\b"),
        ("galaxy", r"\b(?:samsung\s+)?galaxy\s*(?:[sam]\s*\d{1,3}(?:\s*(?:ultra|plus|fe))?|z\s*(?:fold|flip)\s*\d{1,2})\b"),
        ("pixel", r"\b(?:google\s+)?pixel\s*\d{1,2}(?:\s*(?:pro\s*xl|pro|xl|a))?\b"),
        ("redmi", r"\b(?:xiaomi\s+)?redmi\s*(?:note\s*)?\d{1,3}(?:\s*(?:pro\+?|plus))?\b"),
        ("xiaomi", r"\bxiaomi\s*\d{1,3}(?:\s*(?:ultra|pro|t))?\b"),
        ("infinix", r"\binfinix\s*(?:gt|note|hot|zero)\s*\d{1,3}(?:\s*pro)?\b"),
        ("oppo", r"\boppo\s*(?:reno|find\s*x|[ak])\s*\d{1,3}(?:\s*(?:pro|ultra))?\b"),
        ("vivo", r"\bvivo\s*[vxy]\s*\d{1,3}(?:\s*(?:pro|ultra))?\b"),
        ("realme", r"\brealme\s*(?:gt\s*)?\d{1,3}(?:\s*(?:pro|plus))?\b"),
        ("poco", r"\bpoco\s*[fxm]\s*\d{1,2}(?:\s*pro)?\b"),
    ],
    "laptop": [
        ("macbook", r"\bmacbook\s*(?:air|pro)(?:\s*(?:m\d{1,2}|\d{2})){0,2}\b"),
        ("thinkpad", r"\bthinkpad\s*[a-z]\d{1,3}(?:\s*(?:carbon|yoga))?\b"),
        ("vivobook", r"\bvivobook\s*(?:[a-z]\s*)?\d{1,3}(?:\s*(?:pro|flip))?\b"),
        ("zenbook", r"\bzenbook\s*(?:[a-z]\s*)?\d{1,3}(?:\s*(?:pro|duo|flip))?\b"),
        ("rog", r"\brog\s*(?:strix|zephyrus|flow)\s*[a-z]\d{1,2}\b"),
        ("legion", r"\b(?:lenovo\s*)?legion\s*(?:pro\s*)?\d{1,2}(?:i)?\b"),
        ("aspire", r"\b(?:acer\s*)?aspire\s*(?:lite\s*)?\d{1,2}\b"),
    ],
    "camera": [
        ("sony_alpha", r"\bsony\s*(?:alpha\s*)?a\s*\d{1,4}(?:\s*(?:iv|iii|ii|r|s|v)){0,2}\b"),
        ("canon_eos", r"\bcanon\s*(?:eos\s*)?r\s*\d{1,3}(?:\s*mark\s*(?:ii|iii|iv))?\b"),
        ("nikon_z", r"\bnikon\s*z\s*\d{1,2}(?:\s*(?:ii|iii))?\b"),
        ("fujifilm", r"\bfujifilm\s*x[-\s]?[ths]\s*\d{1,2}\b"),
        ("gopro", r"\bgopro\s*(?:hero\s*)?\d{1,2}(?:\s*black)?\b"),
        ("osmo", r"\b(?:dji\s*)?osmo\s*(?:pocket|action)\s*\d{1,2}\b"),
    ],
}
CATEGORY_MARKERS = {
    "phone": ("มือถือ", "สมาร์ทโฟน", "สมาร์ตโฟน", "smartphone"),
    "laptop": ("โน้ตบุ๊ก", "โน๊ตบุ๊ค", "โน้ตบุ๊ค", "laptop", "notebook", "macbook"),
    "camera": ("กล้องมิเรอร์เลส", "กล้องดิจิทัล", "mirrorless", "dslr", "เลนส์กล้อง"),
}
ASPECTS = {
    "battery": ("แบตเตอรี่", ("แบตเตอรี่", "แบต", "ความอึด", "battery")),
    "camera": ("การถ่ายภาพ", ("กล้อง", "ถ่ายภาพ", "เซนเซอร์", "camera", "sensor", "autofocus")),
    "performance": ("ประสิทธิภาพ", ("ชิป", "ซีพียู", "ประมวลผล", "snapdragon", "dimensity", "cpu", "processor")),
    "display": ("หน้าจอ", ("หน้าจอ", "จอภาพ", "จอ", "amoled", "oled", "display", "screen")),
    "cooling": ("การระบายความร้อน", ("ระบายความร้อน", "ความร้อน", "cooling", "thermal")),
    "gaming": ("การเล่นเกม", ("เล่นเกม", "เกมมิ่ง", "gaming", "frame rate", "เฟรมเรต")),
    "video": ("การถ่ายวิดีโอ", ("ถ่ายวิดีโอ", "กันสั่น", "stabilization", "4k", "8k")),
    "portability": ("การพกพา", ("พกพา", "น้ำหนัก", "บางเบา", "portable", "weight")),
}
ALLOWED_ASPECTS = {
    "phone": set(ASPECTS),
    "laptop": {"battery", "performance", "display", "cooling", "gaming", "portability"},
    "camera": {"battery", "camera", "video", "portability", "display"},
}


def _time(value):
    try:
        value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(value, datetime):
            return None
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    except ValueError:
        return None


def _find(text, term):
    pattern = re.escape(term)
    if term.isascii():
        pattern = r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])"
    if term == "จอ":
        boundaries = _thai_token_spans(text)
        return next((match for match in re.finditer(pattern, text) if match.span() in boundaries), None)
    return re.search(pattern, text, re.I)


@lru_cache(maxsize=128)
def _thai_token_spans(text):
    from pythainlp.tokenize import word_tokenize
    spans, offset = set(), 0
    for token in word_tokenize(text, engine="newmm", keep_whitespace=True):
        spans.add((offset, offset + len(token)))
        offset += len(token)
    return spans


def _span(match):
    return {"start": match.start(), "end": match.end(), "text": match.group()}


def _products(text, domain):
    return [{"family": family, "name": m.group(), "key": re.sub(r"[\s-]+", "",
             re.sub(r"^(?:samsung|google|xiaomi|lenovo|acer|dji)\s+", "", m.group().casefold())),
             "span": _span(m)} for family, pattern in PRODUCTS[domain]
            for m in re.finditer(r"(?<![A-Za-z0-9])" + pattern[2:-2] + r"(?![A-Za-z0-9])", text, re.I)]


def _aspects(text, domain):
    result = {}
    for key in sorted(ALLOWED_ASPECTS[domain]):
        for term in ASPECTS[key][1]:
            match = _find(text, term)
            if match:
                result[key] = _span(match)
                break
    return result


def _product_context(text, span):
    # Keep evidence in the same sentence/paragraph as this product. A later
    # paragraph about a different device is not evidence about this one.
    breaks = list(re.finditer(r"[.!?\r\n\u3002]", text))
    start = max((m.end() for m in breaks if m.end() <= span["start"]), default=0)
    end = min((m.start() for m in breaks if m.start() >= span["end"]), default=len(text))
    return start, text[start:end]


def _latest_sources(db, now, region):
    cutoff = now - timedelta(hours=SNAPSHOT_MAX_AGE_HOURS)
    runs = db.query(TrendSnapshotRun).filter(TrendSnapshotRun.region == region,
        TrendSnapshotRun.completed_at >= cutoff, TrendSnapshotRun.completed_at <= now,
        TrendSnapshotRun.status.in_(["completed", "partial", "failed"])).order_by(
            TrendSnapshotRun.completed_at.desc(), TrendSnapshotRun.run_id.desc()).limit(200).all()
    selected, seen = {}, set()
    for run in runs:
        for platform, provider in _provider_status_for_run(run).items():
            if platform not in {"youtube", "google"}:
                continue
            scopes = {"global": provider} if run.snapshot_kind == "global" else {
                f"category:{key}": value for key, value in provider.get("categories", {}).items()}
            if not scopes and run.snapshot_kind == "youtube_categories" and platform == "youtube":
                scopes = {f"category:{key}": provider for key in settings.youtube_trend_category_ids}
            for scope, result in scopes.items():
                key = platform, scope
                if key in seen:
                    continue
                seen.add(key)
                if (run.status in {"completed", "partial"} and result.get("status") == "ok"
                        and result.get("mode", provider.get("mode")) == "live"):
                    selected[run.run_id, platform, scope] = run.completed_at
    if not selected:
        return []
    rows = db.query(TrendSnapshotItem).filter(TrendSnapshotItem.run_id.in_({k[0] for k in selected}),
        TrendSnapshotItem.provider_rank.between(1, 50)).order_by(TrendSnapshotItem.item_id).all()
    result = []
    for row in rows:
        observed = selected.get((row.run_id, row.platform, row.ranking_scope))
        published = _time(row.published_at)
        max_age = timedelta(days=VIDEO_MAX_AGE_DAYS) if row.platform == "youtube" else timedelta(hours=QUERY_MAX_AGE_HOURS)
        if observed is None or published is None or not now - max_age <= published <= now:
            continue
        result.append((row, observed, published, min(observed + timedelta(hours=SNAPSHOT_MAX_AGE_HOURS), published + max_age)))
    return result


def build_current_trend_ideas(db, *, transcript: str, domain: str, now=None, region=None) -> dict:
    now = _time(now or datetime.utcnow())
    output = {"status": "no_related", "generated_at": utc_isoformat(now), "method_version": METHOD_VERSION,
        "region": region or settings.youtube_region, "items": [],
        "policy": {"snapshot_max_age_hours": SNAPSHOT_MAX_AGE_HOURS,
            "youtube_publication_max_age_days": VIDEO_MAX_AGE_DAYS, "google_query_max_age_hours": QUERY_MAX_AGE_HOURS},
        "source_type": "live_metadata_not_transcript"}
    if domain not in SUPPORTED:
        return dict(output, status="unsupported_category")
    if len(transcript.strip()) < 20:
        return dict(output, status="insufficient_user_evidence")
    user_products = _products(transcript, domain)
    user_aspects = _aspects(transcript, domain)
    if not user_products and not user_aspects:
        return dict(output, status="insufficient_user_evidence")
    try:
        # Provider failure must not break the reference-based recommendation.
        with db.begin_nested():
            sources = _latest_sources(db, now, output["region"])
    except SQLAlchemyError:
        return dict(output, status="unavailable")
    if not sources:
        return dict(output, status="no_recent_sources")
    user_keys = {p["key"] for p in user_products}
    user_families = {p["family"] for p in user_products}
    groups = {}
    # Newest source first. Multiple ranking scopes for one video are not extra support.
    sources.sort(key=lambda row: (-row[1].timestamp(), row[0].provider_rank, row[0].item_id))
    for row, observed, published, expires in sources:
        title = row.title or ""
        if re.search(r"เคส|ฟิล์มกันรอย|เมาส์|ที่ชาร์จ|\b(?:case|screen protector|mouse|dpi|polling rate|charger)\b", title, re.I):
            continue
        title_products = _products(title, domain)
        # A phone camera review cannot turn into a standalone Camera recommendation.
        other_products = [p for leaf in SUPPORTED - {domain} for p in _products(title, leaf)]
        if other_products and not title_products:
            continue
        title_relevant = bool(title_products or any(_find(title, word) for word in CATEGORY_MARKERS[domain]))
        if not title_relevant:
            continue
        fields = [("query" if row.platform == "google" else "title", title)]
        if row.platform == "youtube" and row.description:
            # Only the opening text, before outbound links/promotional footers.
            description = row.description[:600]
            description = re.split(r"https?://|ติดตามได้|ติดตามช่อง|affiliate|subscribe", description, maxsplit=1, flags=re.I)[0]
            fields.append(("description", description))
        for field, text in fields:
            for product in _products(text, domain):
                if product["key"] in user_keys:
                    continue
                offset, context = _product_context(text, product["span"])
                source_aspects = {key: dict(span, start=span["start"] + offset,
                    end=span["end"] + offset, field=field)
                    for key, span in _aspects(context, domain).items()}
                shared = sorted(set(user_aspects) & set(source_aspects))
                same_family = product["family"] in user_families
                if not shared and not same_family:
                    continue
                from app.services.trend_topic_preparation import _video_id
                video_id = _video_id(row.video_url) if row.platform == "youtube" else None
                if row.platform == "youtube" and not video_id:
                    continue
                if row.platform == "google":
                    # Use the recorded provider URL only; never fetch searches on demand.
                    from urllib.parse import urlparse
                    parsed = urlparse(row.video_url or "")
                    if parsed.scheme != "https" or parsed.hostname not in {"trends.google.com", "www.google.com", "google.com"}:
                        continue
                key = product["key"]
                reason = "shared_aspects" if shared else "same_product_family"
                labels = [ASPECTS[k][0] for k in shared]
                idea = groups.setdefault(key, {"idea_id": hashlib.sha256(key.encode()).hexdigest()[:20],
                    "topic": product["name"], "suggestion": (
                        f"ลองเปรียบเทียบ {product['name']} ในประเด็น{', '.join(labels[:2])}กับสิ่งที่คุณทดสอบในคลิป"
                        if labels else f"ลองเปรียบเทียบ {product['name']} กับรุ่นตระกูลเดียวกันที่คุณพูดถึง"),
                    "relationship": reason, "related_aspects": labels,
                    "user_evidence": [dict(user_aspects[k], field="transcript") for k in shared]
                        if shared else [dict(p["span"], field="transcript") for p in user_products if p["family"] == product["family"]],
                    "sources": [], "expires_at": utc_isoformat(expires), "_expires": expires, "_seen": set()})
                identity = (row.platform, video_id or row.trend_key)
                if identity in idea["_seen"]:
                    continue
                idea["_seen"].add(identity)
                idea["sources"].append({"platform": row.platform, "snapshot_run_id": row.run_id,
                    "snapshot_item_id": row.item_id, "video_id": video_id, "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else row.video_url,
                    "channel_title": row.channel_title or "", "thumbnail_url": row.thumbnail_url or "",
                    "observed_at": utc_isoformat(observed), "published_at": utc_isoformat(published),
                    "expires_at": utc_isoformat(expires), "ranking_scope": row.ranking_scope,
                    "provider_rank": row.provider_rank, "evidence_field": field,
                    "evidence_text": text, "metadata_fields": dict(fields), "topic_span": product["span"],
                    "context_text": context,
                    "related_evidence": [source_aspects[k] for k in shared],
                    "is_transcript_evidence": False})
                idea["_expires"] = min(idea["_expires"], expires)
    ranked = sorted(groups.values(), key=lambda idea: (-len(idea["related_aspects"]), -len(idea["sources"]), idea["topic"]))
    for idea in ranked[:4]:
        idea["support_count"] = len(idea.pop("_seen"))
        idea["expires_at"] = utc_isoformat(idea.pop("_expires"))
        output["items"].append(idea)
    if output["items"]:
        output["status"] = "ready"
    return output
