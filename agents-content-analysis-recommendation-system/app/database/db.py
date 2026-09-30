import importlib.util
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def _resolve_mysql_driver() -> str | None:
    if importlib.util.find_spec("pymysql"):
        return "pymysql"
    return None


MYSQL_DRIVER = _resolve_mysql_driver()


def _mysql_server_url() -> str:
    return f"mysql+{MYSQL_DRIVER}://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}"


def _mysql_database_url() -> str:
    return f"{_mysql_server_url()}/{settings.db_name}"


def _build_database_url() -> str:
    explicit_url = os.environ.get("DATABASE_URL")
    if explicit_url:
        return explicit_url

    if settings.db_driver.lower() == "mysql" and MYSQL_DRIVER:
        return _mysql_database_url()

    return "sqlite:///./app.db"


def _ensure_mysql_database() -> None:
    bootstrap_engine = create_engine(_mysql_server_url(), pool_pre_ping=True)
    with bootstrap_engine.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        connection.commit()
    bootstrap_engine.dispose()


def _ensure_mysql_schema_compat() -> None:
    bootstrap_engine = create_engine(_mysql_database_url(), pool_pre_ping=True)
    with bootstrap_engine.connect() as connection:
        # Add duration_seconds if missing (older schema compatibility)
        column_exists = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema_name
                  AND TABLE_NAME = 'dataset_contents'
                  AND COLUMN_NAME = 'duration_seconds'
                """
            ),
            {"schema_name": settings.db_name},
        ).scalar()
        if not column_exists:
            connection.execute(text("ALTER TABLE dataset_contents ADD COLUMN duration_seconds INT NULL"))
            connection.commit()

        # Increase video_url length for dataset_contents and user_contents to support long trend links
        for table_name in ["dataset_contents", "user_contents"]:
            row = connection.execute(
                text(
                    """
                    SELECT CHARACTER_MAXIMUM_LENGTH
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = :schema_name
                      AND TABLE_NAME = :table_name
                      AND COLUMN_NAME = 'video_url'
                    """
                ),
                {"schema_name": settings.db_name, "table_name": table_name},
            ).scalar()
            if row is not None and row < 1024:
                connection.execute(
                    text(f"ALTER TABLE {table_name} MODIFY COLUMN video_url VARCHAR(1024) NULL")
                )
                connection.commit()

        # Add updated_at column to system_configs if missing
        config_updated_exists = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema_name
                  AND TABLE_NAME = 'system_configs'
                  AND COLUMN_NAME = 'updated_at'
                """
            ),
            {"schema_name": settings.db_name},
        ).scalar()
        if not config_updated_exists:
            connection.execute(
                text("ALTER TABLE system_configs ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
            )
            connection.commit()

        # Add new admin config fields to system_configs if missing
        for table_name, column_name, sql_type in [
            ("content_keywords", "score", "FLOAT NOT NULL DEFAULT 0"),
            ("analysis_results", "cluster_id", "INT NULL"),
            ("analysis_results", "dataset_id", "INT NULL"),
            ("system_configs", "tiktok_region", "VARCHAR(2) NOT NULL DEFAULT 'TH'"),
            ("system_configs", "enable_tiktok_trending", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("system_configs", "asr_model_default", "VARCHAR(20) NOT NULL DEFAULT 'small'"),
            ("system_configs", "enable_model_toggle", "BOOLEAN NOT NULL DEFAULT TRUE"),
            ("system_configs", "job_backend", "VARCHAR(20) NOT NULL DEFAULT 'inprocess'"),
            ("system_configs", "redis_url", "VARCHAR(255) NULL"),
        ]:
            column_exists = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = :schema_name
                      AND TABLE_NAME = :table_name
                      AND COLUMN_NAME = :column_name
                    """
                ),
                {"schema_name": settings.db_name, "table_name": table_name, "column_name": column_name},
            ).scalar()
            if not column_exists:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}"))
                connection.commit()

        # Fix legacy followed_topics schema if old fields still exist from earlier versions.
        for table_name, column_name, sql_type in [
            ("followed_topics", "topic", "VARCHAR(255) NULL"),
            ("followed_topics", "source_platform", "VARCHAR(50) NULL"),
        ]:
            column_exists = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = :schema_name
                      AND TABLE_NAME = :table_name
                      AND COLUMN_NAME = :column_name
                    """
                ),
                {"schema_name": settings.db_name, "table_name": table_name, "column_name": column_name},
            ).scalar()
            if column_exists:
                connection.execute(text(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {sql_type}"))
                connection.commit()
    bootstrap_engine.dispose()


def _ensure_sqlite_schema_compat() -> None:
    sqlite_engine = create_engine(_build_database_url(), pool_pre_ping=True)
    with sqlite_engine.connect() as connection:
        def table_has_column(table_name: str, column_name: str) -> bool:
            rows = connection.execute(text(f"PRAGMA table_info('{table_name}')")).fetchall()
            return any(row[1] == column_name for row in rows)

        if table_has_column("users", "user_id"):
            if not table_has_column("users", "password_hash"):
                connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL"))
                connection.commit()
            if not table_has_column("users", "role"):
                connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"))
                connection.commit()
            if not table_has_column("users", "is_active"):
                connection.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
                connection.commit()
            if not table_has_column("users", "updated_at"):
                connection.execute(text("ALTER TABLE users ADD COLUMN updated_at DATETIME NULL"))
                connection.commit()

        if table_has_column("dataset_contents", "dataset_id"):
            if not table_has_column("dataset_contents", "duration_seconds"):
                connection.execute(text("ALTER TABLE dataset_contents ADD COLUMN duration_seconds INTEGER NULL"))
                connection.commit()

        if table_has_column("content_keywords", "content_id"):
            if not table_has_column("content_keywords", "score"):
                connection.execute(text("ALTER TABLE content_keywords ADD COLUMN score FLOAT NOT NULL DEFAULT 0"))
                connection.commit()

        if table_has_column("analysis_results", "result_id"):
            if not table_has_column("analysis_results", "cluster_id"):
                connection.execute(text("ALTER TABLE analysis_results ADD COLUMN cluster_id INTEGER NULL"))
                connection.commit()
            if not table_has_column("analysis_results", "dataset_id"):
                connection.execute(text("ALTER TABLE analysis_results ADD COLUMN dataset_id INTEGER NULL"))
                connection.commit()

        if table_has_column("system_configs", "config_id"):
            if not table_has_column("system_configs", "updated_at"):
                connection.execute(text("ALTER TABLE system_configs ADD COLUMN updated_at DATETIME NULL"))
                connection.commit()
            if not table_has_column("system_configs", "tiktok_region"):
                connection.execute(text("ALTER TABLE system_configs ADD COLUMN tiktok_region TEXT NOT NULL DEFAULT 'TH'"))
                connection.commit()
            if not table_has_column("system_configs", "enable_tiktok_trending"):
                connection.execute(text("ALTER TABLE system_configs ADD COLUMN enable_tiktok_trending INTEGER NOT NULL DEFAULT 1"))
                connection.commit()
            if not table_has_column("system_configs", "asr_model_default"):
                connection.execute(text("ALTER TABLE system_configs ADD COLUMN asr_model_default TEXT NOT NULL DEFAULT 'small'"))
                connection.commit()
            if not table_has_column("system_configs", "enable_model_toggle"):
                connection.execute(text("ALTER TABLE system_configs ADD COLUMN enable_model_toggle INTEGER NOT NULL DEFAULT 1"))
                connection.commit()
            if not table_has_column("system_configs", "job_backend"):
                connection.execute(text("ALTER TABLE system_configs ADD COLUMN job_backend TEXT NOT NULL DEFAULT 'inprocess'"))
                connection.commit()
            if not table_has_column("system_configs", "redis_url"):
                connection.execute(text("ALTER TABLE system_configs ADD COLUMN redis_url TEXT NULL"))
                connection.commit()
    sqlite_engine.dispose()


DATABASE_URL = _build_database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")
USING_MYSQL = settings.db_driver.lower() == "mysql" and MYSQL_DRIVER is not None
DB_BOOTSTRAP_ERROR = None
SKIP_DB_BOOTSTRAP = os.getenv("CONTENT_AI_SKIP_DB_BOOTSTRAP", "0") == "1"

if USING_MYSQL and not SKIP_DB_BOOTSTRAP:
    try:
        _ensure_mysql_database()
        _ensure_mysql_schema_compat()
    except Exception as exc:
        DB_BOOTSTRAP_ERROR = f"{exc.__class__.__name__}: {exc}"
elif IS_SQLITE and not SKIP_DB_BOOTSTRAP:
    try:
        _ensure_sqlite_schema_compat()
    except Exception as exc:
        DB_BOOTSTRAP_ERROR = f"{exc.__class__.__name__}: {exc}"

engine_kwargs = {"pool_pre_ping": True}
if IS_SQLITE:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
