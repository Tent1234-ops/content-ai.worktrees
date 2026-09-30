import os
from pathlib import Path


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file()


class Settings:
    app_name: str = os.getenv("APP_NAME", "Content AI Backend")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-secret-in-production")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
    admin_invite_code: str = os.getenv("ADMIN_INVITE_CODE", "")
    classification_require_scope_validation: bool = os.getenv(
        "CLASSIFICATION_REQUIRE_SCOPE_VALIDATION", "true"
    ).lower() not in {"false", "0", "no"}
    db_driver: str = os.getenv("DB_DRIVER", "mysql")
    db_host: str = os.getenv("DB_HOST", "127.0.0.1")
    db_port: str = os.getenv("DB_PORT", "3306")
    db_name: str = os.getenv("DB_NAME", "content_ai")
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "1234")
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    youtube_region: str = os.getenv("YOUTUBE_REGION", "TH")
    # Added defaults for Google and TikTok regions and optional TikTok user-agent for scraping
    google_region: str = os.getenv("GOOGLE_REGION", os.getenv("YOUTUBE_REGION", "TH"))
    tiktok_region: str = os.getenv("TIKTOK_REGION", os.getenv("YOUTUBE_REGION", "TH"))
    tiktok_scrape_user_agent: str = os.getenv(
        "TIKTOK_SCRAPE_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    )
    live_trend_refresh_seconds: int = max(30, int(os.getenv("LIVE_TREND_REFRESH_SECONDS", "60")))
    live_trend_limit: int = min(100, max(1, int(os.getenv("LIVE_TREND_LIMIT", "50"))))
    live_trend_provider_timeout_seconds: float = max(
        1.0,
        float(os.getenv("LIVE_TREND_PROVIDER_TIMEOUT_SECONDS", "8")),
    )
    live_trend_snapshot_retention_runs: int = max(
        2,
        int(os.getenv("LIVE_TREND_SNAPSHOT_RETENTION_RUNS", "120")),
    )
    live_trend_momentum_window_seconds: int = max(
        120,
        int(os.getenv("LIVE_TREND_MOMENTUM_WINDOW_SECONDS", "300")),
    )
    youtube_category_trend_refresh_seconds: int = max(
        60,
        int(os.getenv("YOUTUBE_CATEGORY_TREND_REFRESH_SECONDS", "60")),
    )
    youtube_category_trend_limit: int = min(
        50,
        max(1, int(os.getenv("YOUTUBE_CATEGORY_TREND_LIMIT", "50"))),
    )
    youtube_category_cache_seconds: int = max(
        3600,
        int(os.getenv("YOUTUBE_CATEGORY_CACHE_SECONDS", "86400")),
    )
    youtube_category_snapshot_timeout_seconds: float = max(
        15.0,
        float(os.getenv("YOUTUBE_CATEGORY_SNAPSHOT_TIMEOUT_SECONDS", "60")),
    )
    youtube_trend_category_ids: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv(
            "YOUTUBE_TREND_CATEGORY_IDS",
            "1,2,10,15,17,20,22,23,24,25,26,28",
        ).split(",")
        if item.strip()
    )[:12]


settings = Settings()
