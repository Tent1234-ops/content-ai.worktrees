# Dashboard API Payload Specification

This document describes the dashboard endpoints and the expected response payloads for frontend integration.

## GET /dashboard/overview

Description:
- Returns dashboard metrics, category/cluster distributions, top trend items, priority topic signals, emerging topics, and live trend snapshots.
- Use on the main dashboard screen.

Headers:
- `Authorization: Bearer <access_token>`

Query parameters:
- `region`: string, 2 characters (e.g. `TH`)
- `trend_mode`: `auto` | `mock` | `live`
- `trend_limit`: integer, 1-10

Example request:

    GET /dashboard/overview?region=TH&trend_mode=live&trend_limit=5 HTTP/1.1
    Host: localhost:8000
    Authorization: Bearer <access_token>

Example response structure:

    {
      "db_status": "ok",
      "db_error": null,
      "user_role": "user",
      "metrics": {
        "total_users": 10,
        "active_users": 8,
        "total_user_contents": 23,
        "total_analysis_results": 23,
        "total_clusters": 4,
        "total_cluster_runs": 2,
        "total_cluster_memberships": 18,
        "total_dataset_contents": 120,
        "total_system_logs": 50,
        "my_contents": 8,
        "my_analysis_results": 8
      },
      "category_distribution": [{ "category": "Technology", "count": 12 }],
      "cluster_distribution": [{ "cluster_name": "Review", "count": 9 }],
      "top_trends": [{
        "dataset_id": 1,
        "title": "Sample Trend Video",
        "category": "Technology",
        "source_platform": "youtube",
        "video_url": "https://...",
        "views": 123456,
        "likes": 7890,
        "comments": 234,
        "trend_score": 45678.0,
        "published_at": "2026-07-26T14:00:00"
      }],
      "top_categories": [{ "category": "Technology", "count": 12 }],
      "top_keywords": [{ "keyword": "smartphone", "count": 125 }],
      "source_distribution": [{ "source_platform": "youtube", "count": 18 }],
      "platform_summaries": [{
        "source": "youtube",
        "dataset_count": 42,
        "profile_count": 5,
        "domains": ["audio", "smartphone"]
      }],
      "platform_comparison": [{
        "domain": "audio",
        "youtube_sample_size": 20,
        "google_sample_size": 12,
        "youtube_duration": "60-90 sec",
        "google_duration": "55-85 sec"
      }],
      "priority_topics": [{ "keyword": "content", "score": 12.34 }],
      "emerging_topics": [{ "keyword": "unbox", "score": 9.87 }],
      "priority_items": [{
        "title": "Affordable smartphone camera battle under budget",
        "category": "Technology",
        "source_platform": "youtube",
        "video_url": "https://...",
        "trend_score": 418275.0,
        "priority_score": 419005.0,
        "novelty_score": 6.0,
        "views": 618000,
        "likes": 50100,
        "comments": 3025,
        "published_at": "2026-04-27T12:30:00"
      }],
      "youtube_trends": {
        "mode": "live",
        "region": "TH",
        "total": 5,
        "items": [
          {
            "title": "Example YouTube Trend",
            "channel_title": "Example Channel",
            "category": "Technology",
            "published_at": "2026-07-26T12:00:00",
            "video_url": "https://...",
            "thumbnail_url": "https://...",
            "views": 12345,
            "likes": 1234,
            "comments": 123,
            "trend_score": 4567.0,
            "duration_seconds": 420,
            "source": "youtube"
          }
        ]
      },
      "google_trends": {
        "mode": "live",
        "region": "TH",
        "total": 5,
        "items": [
          {
            "title": "Google Trend Topic",
            "query": "example query",
            "category": "Technology",
            "published_at": "2026-07-26T12:00:00",
            "video_url": "https://...",
            "thumbnail_url": "https://...",
            "views": 6789,
            "likes": 234,
            "comments": 45,
            "trend_score": 2123.0,
            "duration_seconds": 360,
            "source": "google_trends",
            "traffic_text": "Rising"
          }
        ]
      },
      "tiktok_trends": {
        "mode": "live",
        "region": "TH",
        "total": 5,
        "items": [
          {
            "title": "ตัวอย่าง TikTok Trend",
            "creator": "TrendCreatorTH",
            "category": "Entertainment",
            "published_at": "2026-07-26T12:00:00",
            "video_url": "https://www.tiktok.com/@trendcreatorth/video/1234567890",
            "thumbnail_url": "https://...",
            "views": 1250000,
            "likes": 98000,
            "comments": 5400,
            "trend_score": 153400.0,
            "duration_seconds": 30,
            "source": "tiktok_live"
          }
        ]
      }
    }

Frontend guidance:
- Use `priority_items` for a ranked high-priority content feed.
- Use `priority_topics` for recommend keyword signals.
- Use `emerging_topics` for newly rising keyword panels.
- Display `youtube_trends.items` and `google_trends.items` as live trend snapshots.
- Use `top_trends` for deep comparison cards or examples of successful content.

---

## GET /dashboard/emerging-topics

Description:
- Returns priority-ranked trend items and emerging topic keywords.
- Use on a dedicated emerging topics panel.

Headers:
- `Authorization: Bearer <access_token>`

Query parameters:
- `region`: string, 2 characters
- `trend_mode`: `auto` | `mock` | `live`
- `trend_limit`: integer, 1-10

Example request:

    GET /dashboard/emerging-topics?region=TH&trend_mode=live&trend_limit=5 HTTP/1.1
    Host: localhost:8000
    Authorization: Bearer <access_token>

Example response structure:

    {
      "priority_items": [
        {
          "title": "Affordable smartphone camera battle under budget",
          "category": "Technology",
          "source_platform": "youtube",
          "video_url": "https://...",
          "trend_score": 418275.0,
          "priority_score": 419005.0,
          "novelty_score": 6.0,
          "views": 618000,
          "likes": 50100,
          "comments": 3025,
          "published_at": "2026-04-27T12:30:00"
        }
      ],
      "emerging_topics": [
        { "keyword": "content", "score": 9.87 }
      ],
      "youtube_trends": {
        "mode": "live",
        "region": "TH",
        "total": 5,
        "items": []
      },
      "google_trends": {
        "mode": "live",
        "region": "TH",
        "total": 5,
        "items": []
      },
      "tiktok_trends": {
        "mode": "live",
        "region": "TH",
        "total": 5,
        "items": []
      }
    }

Frontend guidance:
- Use `priority_items` for a top-priority content list.
- Use `emerging_topics` for keyword discovery.
- Show `youtube_trends.items` and `google_trends.items` as supporting live snapshots.
