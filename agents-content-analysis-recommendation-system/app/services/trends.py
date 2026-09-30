import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import json5

from app.core.config import settings
from app.schemas.trends import GoogleTrendItem, TikTokTrendItem, YouTubeCategoryItem, YouTubeTrendItem
from app.services.simple_cache import get as cache_get, set as cache_set


def _compute_trend_score(views: int, likes: int, comments: int) -> float:
    return round((views * 0.5) + (likes * 2.0) + (comments * 3.0), 2)


def _compute_google_trend_score(traffic: int) -> float:
    return round(float(traffic), 2)


def _parse_iso8601_duration(duration_text: str | None) -> int | None:
    if not duration_text:
        return None
    pattern = re.compile(
        r"^P(?:"
        r"(?:(?P<days>\d+)D)?"
        r"(?:T"
        r"(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?"
        r"(?:(?P<seconds>\d+)S)?"
        r")?"
        r")$"
    )
    match = pattern.match(duration_text)
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return (days * 86400) + (hours * 3600) + (minutes * 60) + seconds


def _normalize_json_like_text(raw_text: str) -> str:
    normalized = raw_text.replace("undefined", "null")
    normalized = normalized.replace("\n", " ")
    return normalized


def _extract_js_object(text: str, marker: str) -> str:
    start = text.find(marker)
    if start == -1:
        raise ValueError(f"Marker not found: {marker}")
    start = text.find("{", start)
    if start == -1:
        raise ValueError("JSON object start not found")
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("Could not extract JSON object from text")


def _get_video_renderer_items(data: object) -> List[Dict[str, object]]:
    if isinstance(data, dict):
        if "videoRenderer" in data and isinstance(data["videoRenderer"], dict):
            return [data["videoRenderer"]]
        items = []
        for value in data.values():
            items.extend(_get_video_renderer_items(value))
        return items
    if isinstance(data, list):
        items = []
        for value in data:
            items.extend(_get_video_renderer_items(value))
        return items
    return []


def _parse_view_count(text: str | None) -> int:
    if not text:
        return 0
    number_text = re.sub(r"[^0-9]", "", text)
    try:
        return int(number_text)
    except ValueError:
        return 0


def _parse_duration_string(duration_text: str | None) -> int | None:
    if not duration_text:
        return None
    parts = duration_text.split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return None
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def _mock_youtube_categories(_region: str) -> List[YouTubeCategoryItem]:
    return [
        YouTubeCategoryItem(category_id="10", title="Music", assignable=True),
        YouTubeCategoryItem(category_id="17", title="Sports", assignable=True),
        YouTubeCategoryItem(category_id="20", title="Gaming", assignable=True),
        YouTubeCategoryItem(category_id="22", title="People & Blogs", assignable=True),
        YouTubeCategoryItem(category_id="24", title="Entertainment", assignable=True),
        YouTubeCategoryItem(category_id="28", title="Science & Technology", assignable=True),
    ]


def _mock_youtube_trending(region: str, limit: int, video_category_id: Optional[str] = None) -> List[YouTubeTrendItem]:
    seed_items = [
        {
            "title": "Top 5 gaming audio gadgets creators are talking about",
            "channel_title": "Trend Lab TH",
            "category": "28",
            "published_at": datetime(2026, 4, 27, 9, 0, 0),
            "video_url": "https://www.youtube.com/watch?v=mock001",
            "thumbnail_url": "https://img.youtube.com/vi/mock001/hqdefault.jpg",
            "views": 452000,
            "likes": 38400,
            "comments": 2150,
            "duration_seconds": 72,
        },
        {
            "title": "Affordable smartphone camera battle under budget",
            "channel_title": "Creator Insight",
            "category": "28",
            "published_at": datetime(2026, 4, 27, 12, 30, 0),
            "video_url": "https://www.youtube.com/watch?v=mock002",
            "thumbnail_url": "https://img.youtube.com/vi/mock002/hqdefault.jpg",
            "views": 618000,
            "likes": 50100,
            "comments": 3025,
            "duration_seconds": 95,
        },
        {
            "title": "Cafe review ideas that went viral this week",
            "channel_title": "Social Pulse",
            "category": "22",
            "published_at": datetime(2026, 4, 26, 18, 0, 0),
            "video_url": "https://www.youtube.com/watch?v=mock003",
            "thumbnail_url": "https://img.youtube.com/vi/mock003/hqdefault.jpg",
            "views": 390000,
            "likes": 29750,
            "comments": 1822,
            "duration_seconds": 48,
        },
    ]
    if video_category_id:
        seed_items = [item for item in seed_items if item["category"] == video_category_id]
    items: List[YouTubeTrendItem] = []
    for raw in seed_items[:limit]:
        items.append(
            YouTubeTrendItem(
                **raw,
                trend_score=_compute_trend_score(raw["views"], raw["likes"], raw["comments"]),
                source=f"youtube_mock_{region.lower()}",
            )
        )
    return items


def _mock_google_trending(region: str, limit: int) -> List[GoogleTrendItem]:
    seed_items = [
        {
            "title": "เลือกตั้งท้องถิ่น",
            "query": "เลือกตั้งท้องถิ่น",
            "category": "News",
            "published_at": datetime(2026, 5, 4, 8, 0, 0),
            "video_url": "https://trends.google.com/trends/explore?q=%E0%B9%80%E0%B8%A5%E0%B8%B7%E0%B8%AD%E0%B8%81%E0%B8%95%E0%B8%B1%E0%B9%89%E0%B8%87%E0%B8%97%E0%B9%89%E0%B8%AD%E0%B8%87%E0%B8%96%E0%B8%B4%E0%B9%88%E0%B8%99&geo=TH",
            "thumbnail_url": None,
            "traffic_text": "200K+",
            "trend_score": 200000.0,
            "duration_seconds": None,
        },
        {
            "title": "ผลบอลพรีเมียร์ลีก",
            "query": "ผลบอลพรีเมียร์ลีก",
            "category": "Sports",
            "published_at": datetime(2026, 5, 4, 9, 0, 0),
            "video_url": "https://trends.google.com/trends/explore?q=%E0%B8%9C%E0%B8%A5%E0%B8%9A%E0%B8%AD%E0%B8%A5%E0%B8%9E%E0%B8%A3%E0%B8%B5%E0%B9%80%E0%B8%A1%E0%B8%B5%E0%B8%A2%E0%B8%A3%E0%B9%8C%E0%B8%A5%E0%B8%B5%E0%B8%81&geo=TH",
            "thumbnail_url": None,
            "traffic_text": "100K+",
            "trend_score": 100000.0,
            "duration_seconds": None,
        },
        {
            "title": "iPhone รุ่นใหม่",
            "query": "iPhone รุ่นใหม่",
            "category": "Technology",
            "published_at": datetime(2026, 5, 4, 10, 0, 0),
            "video_url": "https://trends.google.com/trends/explore?q=iPhone&geo=TH",
            "thumbnail_url": None,
            "traffic_text": "50K+",
            "trend_score": 50000.0,
            "duration_seconds": None,
        },
    ]
    return [
        GoogleTrendItem(
            **item,
            search_volume=_parse_google_traffic(item.get("traffic_text")),
            source=f"google_trends_mock_{region.lower()}",
        )
        for item in seed_items[:limit]
    ]


def _mock_tiktok_trending(region: str, limit: int) -> List[TikTokTrendItem]:
    seed_items = [
        {
            "title": "Challenge สเต็ปเต้นสุดฮิต",
            "creator": "DanceBeatTH",
            "category": "Entertainment",
            "published_at": datetime(2026, 5, 5, 12, 0, 0),
            "video_url": "https://www.tiktok.com/@dancebeatth/video/mock001",
            "thumbnail_url": "https://example.com/tiktok_mock001.jpg",
            "views": 1250000,
            "likes": 98000,
            "comments": 5400,
            "duration_seconds": 31,
        },
        {
            "title": "รีวิวแก็ดเจ็ตมือถือสุดล้ำ",
            "creator": "TechTalks",
            "category": "Technology",
            "published_at": datetime(2026, 5, 5, 13, 30, 0),
            "video_url": "https://www.tiktok.com/@techtalks/video/mock002",
            "thumbnail_url": "https://example.com/tiktok_mock002.jpg",
            "views": 842000,
            "likes": 75600,
            "comments": 3100,
            "duration_seconds": 45,
        },
        {
            "title": "สูตรทำอาหารจานด่วนใน 1 นาที",
            "creator": "ChefQuick",
            "category": "Food",
            "published_at": datetime(2026, 5, 5, 9, 0, 0),
            "video_url": "https://www.tiktok.com/@chefquick/video/mock003",
            "thumbnail_url": "https://example.com/tiktok_mock003.jpg",
            "views": 554000,
            "likes": 62000,
            "comments": 2520,
            "duration_seconds": 60,
        },
    ]
    return [
        TikTokTrendItem(**item, source=f"tiktok_mock_{region.lower()}")
        for item in seed_items[:limit]
    ]


def _parse_tiktok_trending_items(page_text: str, limit: int) -> List[TikTokTrendItem]:
    items: List[TikTokTrendItem] = []
    try:
        raw_json = _extract_js_object(page_text, 'window["SIGI_STATE"]')
        payload = json5.loads(_normalize_json_like_text(raw_json))
        item_module = payload.get("ItemModule", {}) if isinstance(payload, dict) else {}
        if not isinstance(item_module, dict):
            return []

        for item_id, item_data in item_module.items():
            if not isinstance(item_data, dict):
                continue
            title = item_data.get("desc") or item_data.get("title") or ""
            creator = item_data.get("author") or (item_data.get("authorMeta") or {}).get("name") or ""
            video_url = f"https://www.tiktok.com/@{item_data.get('author', '').strip('/')}/video/{item_id}" if item_id else ""
            thumbnail_url = item_data.get("videoCover") or item_data.get("cover") or ""
            stats = item_data.get("stats") or {}
            views = int(stats.get("playCount", 0) or 0)
            likes = int(stats.get("diggCount", 0) or 0)
            comments = int(stats.get("commentCount", 0) or 0)
            published_at = None
            if item_data.get("createTime"):
                try:
                    published_at = datetime.utcfromtimestamp(int(item_data.get("createTime")))
                except Exception:
                    published_at = None
            items.append(
                TikTokTrendItem(
                    title=title,
                    creator=creator,
                    category=item_data.get("challenges", [{}])[0].get("title") if item_data.get("challenges") else None,
                    published_at=published_at,
                    video_url=video_url,
                    thumbnail_url=thumbnail_url,
                    views=views,
                    likes=likes,
                    comments=comments,
                    trend_score=_compute_trend_score(views, likes, comments),
                    duration_seconds=item_data.get("video", {}).get("durationSeconds") if isinstance(item_data.get("video"), dict) else None,
                    source="tiktok_live",
                )
            )
            if len(items) >= limit:
                break
    except Exception:
        pass
    return items


def _live_tiktok_trending(region: str, limit: int) -> List[TikTokTrendItem]:
    url = "https://www.tiktok.com/discover?lang=en"
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urlopen(request, timeout=settings.live_trend_provider_timeout_seconds) as response:
        page_text = response.read().decode("utf-8", errors="replace")

    items = _parse_tiktok_trending_items(page_text, limit)
    return items


def get_tiktok_trending(region: str, limit: int, mode: str) -> tuple[str, List[TikTokTrendItem]]:
    if mode == "mock":
        return "mock", _mock_tiktok_trending(region, limit)

    if mode == "live":
        return "live", _live_tiktok_trending(region, limit)

    try:
        items = _live_tiktok_trending(region, limit)
        if items:
            return "live", items
    except (ValueError, URLError, TimeoutError):
        pass
    return "mock", _mock_tiktok_trending(region, limit)


def _parse_google_traffic(traffic_text: str | None) -> int:
    if not traffic_text:
        return 0
    normalized = traffic_text.strip().upper().replace(",", "").replace("+", "")
    multiplier = 1
    if normalized.endswith("K"):
        multiplier = 1000
        normalized = normalized[:-1]
    elif normalized.endswith("M"):
        multiplier = 1000000
        normalized = normalized[:-1]
    try:
        return int(float(normalized) * multiplier)
    except ValueError:
        return 0


_GOOGLE_TRENDS_REGION_MAP = {
    "US": "united_states",
    "TH": "thailand",
    "GB": "united_kingdom",
    "IN": "india",
    "CA": "canada",
    "AU": "australia",
    "SG": "singapore",
    "ID": "indonesia",
    "MX": "mexico",
    "BR": "brazil",
    "JP": "japan",
    "DE": "germany",
    "FR": "france",
    "ZA": "south_africa",
}


def _normalize_google_region(region: str) -> str:
    return _GOOGLE_TRENDS_REGION_MAP.get(region.upper(), region.lower())


def _live_youtube_categories(region: str) -> List[YouTubeCategoryItem]:
    if not settings.youtube_api_key:
        raise ValueError("Missing YOUTUBE_API_KEY")

    region = region.upper()
    cache_key = f"youtube_video_categories:{region}"
    cached = cache_get(cache_key)
    if isinstance(cached, list) and cached:
        return cached

    params = {
        "part": "snippet",
        "regionCode": region,
        "key": settings.youtube_api_key,
    }
    url = f"https://www.googleapis.com/youtube/v3/videoCategories?{urlencode(params)}"
    with urlopen(url, timeout=settings.live_trend_provider_timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    items: List[YouTubeCategoryItem] = []
    for item in payload.get("items", []):
        snippet = item.get("snippet", {})
        items.append(
            YouTubeCategoryItem(
                category_id=str(item.get("id", "")),
                title=snippet.get("title", ""),
                assignable=bool(snippet.get("assignable", True)),
            )
        )
    if items:
        cache_set(
            cache_key,
            items,
            ttl_seconds=settings.youtube_category_cache_seconds,
        )
    return items


def _live_youtube_trending(
    region: str,
    limit: int,
    video_category_id: Optional[str] = None,
    *,
    allow_web_fallback: bool = True,
) -> List[YouTubeTrendItem]:
    if not settings.youtube_api_key:
        if not allow_web_fallback or video_category_id:
            raise ValueError("Missing YOUTUBE_API_KEY for category-scoped trends")
        return _live_youtube_trending_web_fallback(region, limit, video_category_id)

    try:
        categories = _live_youtube_categories(region)
        category_map: Dict[str, str] = {item.category_id: item.title for item in categories}
        params = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "regionCode": region,
            "maxResults": min(limit, 50),
            "key": settings.youtube_api_key,
        }
        if video_category_id:
            params["videoCategoryId"] = video_category_id
        url = f"https://www.googleapis.com/youtube/v3/videos?{urlencode(params)}"
        with urlopen(url, timeout=settings.live_trend_provider_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        items: List[YouTubeTrendItem] = []
        for item in payload.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            duration_seconds = _parse_iso8601_duration((item.get("contentDetails") or {}).get("duration"))
            thumbnails = snippet.get("thumbnails") or {}
            thumbnail_url = next(
                (
                    details.get("url")
                    for size in ("maxres", "standard", "high", "medium", "default")
                    if isinstance((details := thumbnails.get(size)), dict)
                    and details.get("url")
                ),
                None,
            )
            items.append(
                YouTubeTrendItem(
                    title=snippet.get("title", ""),
                    channel_title=snippet.get("channelTitle", ""),
                    description=snippet.get("description") or None,
                    category=category_map.get(str(snippet.get("categoryId", "")), str(snippet.get("categoryId", ""))),
                    published_at=datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
                    if snippet.get("publishedAt")
                    else None,
                    video_url=f"https://www.youtube.com/watch?v={item.get('id', '')}",
                    thumbnail_url=thumbnail_url,
                    views=views,
                    likes=likes,
                    comments=comments,
                    views_available="viewCount" in stats,
                    likes_available="likeCount" in stats,
                    comments_available="commentCount" in stats,
                    trend_score=_compute_trend_score(views, likes, comments),
                    duration_seconds=duration_seconds,
                    source="youtube_live",
                )
            )
        return items
    except (ValueError, URLError, TimeoutError, json.JSONDecodeError):
        if not allow_web_fallback or video_category_id:
            raise
        return _live_youtube_trending_web_fallback(region, limit, video_category_id)


def _live_youtube_trending_web_fallback(
    region: str, limit: int, video_category_id: Optional[str] = None
) -> List[YouTubeTrendItem]:
    url = f"https://www.youtube.com/feed/trending?gl={region.upper()}"
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    })
    with urlopen(request, timeout=settings.live_trend_provider_timeout_seconds) as response:
        page_text = response.read().decode("utf-8", errors="replace")

    marker = "ytInitialData"
    raw_json = _extract_js_object(page_text, marker)
    payload = json.loads(_normalize_json_like_text(raw_json))
    renderers = _get_video_renderer_items(payload)
    items: List[YouTubeTrendItem] = []
    for item in renderers[:limit]:
        title = ""
        try:
            title = item["title"]["runs"][0]["text"]
        except (KeyError, TypeError, IndexError):
            title = item.get("title", {}).get("simpleText", "")

        channel_title = ""
        try:
            channel_title = item["ownerText"]["runs"][0]["text"]
        except (KeyError, TypeError, IndexError):
            channel_title = item.get("shortBylineText", {}).get("runs", [{}])[0].get("text", "")

        video_id = item.get("videoId", "")
        video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        thumbnail_url = ""
        try:
            thumbnails = item["thumbnail"]["thumbnails"]
            thumbnail_url = thumbnails[-1].get("url", "") if thumbnails else ""
        except (KeyError, TypeError, IndexError):
            thumbnail_url = ""

        views_text = item.get("viewCountText", {}).get("simpleText") or item.get("viewCountText", {}).get("runs", [{}])[0].get("text")
        views = _parse_view_count(views_text)

        duration_text = item.get("lengthText", {}).get("simpleText")
        duration_seconds = _parse_duration_string(duration_text)

        items.append(
            YouTubeTrendItem(
                title=title,
                channel_title=channel_title,
                category=None,
                published_at=None,
                video_url=video_url,
                thumbnail_url=thumbnail_url,
                views=views,
                likes=0,
                comments=0,
                views_available=bool(views_text),
                likes_available=False,
                comments_available=False,
                trend_score=_compute_trend_score(views, 0, 0),
                duration_seconds=duration_seconds,
                source="youtube_live",
            )
        )
    return items


def _live_google_trending(region: str, limit: int) -> List[GoogleTrendItem]:
    try:
        url = f"https://trends.google.com/trends/trendingsearches/daily?geo={region.upper()}"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=settings.live_trend_provider_timeout_seconds) as response:
            page_text = response.read().decode("utf-8", errors="replace")

        blocks = re.findall(r"AF_initDataCallback\((\{.*?\})\);", page_text, flags=re.S)
        for raw_block in blocks:
            try:
                block = json5.loads(raw_block)
            except Exception:
                continue
            if block.get("key") != "ds:0":
                continue
            data = block.get("data")
            if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
                continue
            items: List[GoogleTrendItem] = []
            for index, entry in enumerate(data[1][:limit]):
                if not isinstance(entry, list) or not entry:
                    continue
                title = str(entry[0]) if entry[0] is not None else ""
                traffic = None
                if len(entry) > 6 and isinstance(entry[6], int):
                    traffic = entry[6]

                items.append(
                    GoogleTrendItem(
                        title=title,
                        query=title,
                        category="Search Trends",
                        published_at=datetime.utcnow(),
                        video_url=f"https://trends.google.com/trends/explore?q={quote_plus(title)}&geo={region.upper()}",
                        thumbnail_url=None,
                        views=0,
                        likes=0,
                        comments=0,
                        trend_score=float(traffic if traffic is not None else max(limit - index, 1)),
                        search_volume=traffic,
                        source="google_trends_live",
                        traffic_text=str(traffic) if traffic is not None else None,
                    )
                )
            if items:
                return items
    except Exception as exc:
        raise ValueError(f"Google Trends live fetch failed: {exc}") from exc
    raise ValueError("Google Trends live fetch returned no parseable items")


def get_youtube_categories(region: str, mode: str) -> tuple[str, List[YouTubeCategoryItem]]:
    if mode == "mock":
        return "mock", _mock_youtube_categories(region)

    if mode == "live":
        return "live", _live_youtube_categories(region)

    try:
        return "live", _live_youtube_categories(region)
    except (ValueError, URLError, TimeoutError):
        return "mock", _mock_youtube_categories(region)


def get_youtube_trending(
    region: str,
    limit: int,
    mode: str,
    video_category_id: Optional[str] = None,
    *,
    allow_web_fallback: bool = True,
) -> tuple[str, List[YouTubeTrendItem]]:
    if mode == "mock":
        return "mock", _mock_youtube_trending(region, limit, video_category_id)

    if mode == "live":
        return "live", _live_youtube_trending(
            region,
            limit,
            video_category_id,
            allow_web_fallback=allow_web_fallback,
        )

    try:
        items = _live_youtube_trending(
            region,
            limit,
            video_category_id,
            allow_web_fallback=allow_web_fallback,
        )
        if items:
            return "live", items
    except (ValueError, URLError, TimeoutError):
        pass

    return "mock", _mock_youtube_trending(region, limit, video_category_id)


def get_google_trending(region: str, limit: int, mode: str) -> tuple[str, List[GoogleTrendItem]]:
    if mode == "mock":
        return "mock", _mock_google_trending(region, limit)

    if mode == "live":
        return "live", _live_google_trending(region, limit)

    try:
        items = _live_google_trending(region, limit)
        if items:
            return "live", items
    except (ValueError, URLError, TimeoutError, ET.ParseError):
        pass

    return "mock", _mock_google_trending(region, limit)
