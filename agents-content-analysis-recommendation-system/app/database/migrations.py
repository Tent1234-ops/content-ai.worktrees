from __future__ import annotations

from typing import Dict

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import Engine


def migrate_reference_statistics_schema(engine: Engine) -> None:
    """Widen counters without rewriting observations or transcript data."""
    if engine.dialect.name != "mysql":
        return
    with engine.begin() as connection:
        columns = {column["name"]: column for column in inspect(connection).get_columns("dataset_contents")}
        for name in ("views", "likes", "comments"):
            if "BIGINT" not in str(columns[name]["type"]).upper():
                connection.execute(text(f"ALTER TABLE dataset_contents MODIFY COLUMN {name} BIGINT NOT NULL DEFAULT 0"))

from app.services.dataset_contract import (
    HOLDOUT_SPLIT_STRATEGY,
    SPLIT_STRATEGY,
    SUPPORTED_YOUTUBE_DATASET_SOURCES,
    channel_dataset_split,
)
from app.services.view_metrics import (
    GOOGLE_INTEREST_V1,
    PROVIDER_NATIVE_V1,
    TIKTOK_PUBLIC_VIEW_V1,
    UNKNOWN_VIEW_METRIC,
    YOUTUBE_PLAY_START_VIEW_V2,
    YOUTUBE_QUALIFIED_VIEW_V1,
    YOUTUBE_VIEW_METRIC_CHANGE_AT,
)


PHASE13_DATASET_COLUMNS = {
    "dataset_source": "VARCHAR(100) NOT NULL DEFAULT 'legacy'",
    "dataset_version": "VARCHAR(100) NOT NULL DEFAULT 'legacy-v1'",
    "source_record_id": "VARCHAR(255) NULL",
    "source_creator": "VARCHAR(255) NULL",
    "taxonomy_version": "VARCHAR(50) NOT NULL DEFAULT 'legacy-v1'",
    "taxonomy_leaf_key": "VARCHAR(100) NULL",
    "category_level_1": "VARCHAR(150) NULL",
    "category_level_2": "VARCHAR(150) NULL",
    "category_level_3": "VARCHAR(150) NULL",
    "language": "VARCHAR(20) NOT NULL DEFAULT 'und'",
    "verification_status": "VARCHAR(30) NOT NULL DEFAULT 'unverified'",
    "label_source": "VARCHAR(100) NOT NULL DEFAULT 'unverified'",
    "license_name": "VARCHAR(100) NOT NULL DEFAULT 'unknown'",
    "license_url": "VARCHAR(1024) NULL",
    "data_split": "VARCHAR(20) NOT NULL DEFAULT 'unassigned'",
    "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
}

PHASE13_ANALYSIS_COLUMNS = {
    "classification_model_id": "INT NULL",
    "taxonomy_version": "VARCHAR(50) NULL",
    "taxonomy_leaf_key": "VARCHAR(100) NULL",
    "category_level_1": "VARCHAR(150) NULL",
    "category_level_2": "VARCHAR(150) NULL",
    "category_level_3": "VARCHAR(150) NULL",
    "classification_confidence": "FLOAT NULL",
    "classification_is_unknown": "BOOLEAN NOT NULL DEFAULT FALSE",
}

PHASE13_MODEL_METRIC_COLUMNS = {
    "taxonomy_leaf_key": "VARCHAR(100) NOT NULL DEFAULT '__overall__'",
}

PHASE19_USER_CONTENT_COLUMNS = {
    "raw_transcript": "LONGTEXT NULL",
    "cleaned_transcript": "LONGTEXT NULL",
}

YOUTUBE_CC_DATASET_COLUMNS = {
    "duration_seconds": "INT NULL",
    "collection_run_id": "INT NULL",
    "source_youtube_id": "VARCHAR(32) NULL",
    "source_channel_id": "VARCHAR(64) NULL",
    "source_category": "VARCHAR(100) NULL",
    "source_subcategory": "VARCHAR(100) NULL",
    "collection_query": "VARCHAR(255) NULL",
    "source_release_url": "VARCHAR(1024) NULL",
    "source_archive_sha256": "VARCHAR(64) NULL",
    "source_annotation_path": "VARCHAR(1024) NULL",
    "source_annotation_sha256": "VARCHAR(64) NULL",
    "import_batch_id": "VARCHAR(64) NULL",
    "split_strategy": "VARCHAR(100) NULL",
    "creator_group_key": "VARCHAR(64) NULL",
    "transcript_sha256": "VARCHAR(64) NULL",
    "transcript_segment_count": "INT NOT NULL DEFAULT 0",
    "transcript_start_seconds": "FLOAT NULL",
    "transcript_end_seconds": "FLOAT NULL",
    "transcript_window_seconds": "INT NULL",
    "transcript_source": "VARCHAR(50) NULL",
    "transcript_acquisition_method": (
        "VARCHAR(64) NOT NULL DEFAULT 'youtube_transcript_api'"
    ),
    "transcript_scope": "VARCHAR(32) NOT NULL DEFAULT 'first_window'",
    "transcript_timestamps_available": "BOOLEAN NOT NULL DEFAULT TRUE",
    "caption_type": "VARCHAR(50) NULL",
    "transcript_quality": "VARCHAR(30) NULL",
    "reviewed_by": "VARCHAR(255) NULL",
    "reviewed_at": "DATETIME NULL",
    "review_notes": "TEXT NULL",
    "statistics_captured_at": "DATETIME NULL",
    "license_verified_at": "DATETIME NULL",
    "raw_metadata_json": "TEXT NULL",
    "collection_strategy": "VARCHAR(50) NULL",
    "average_views_per_day": "FLOAT NOT NULL DEFAULT 0",
    "engagement_rate": "FLOAT NOT NULL DEFAULT 0",
    "is_training_eligible": "BOOLEAN NOT NULL DEFAULT FALSE",
    "is_keyword_recommendation_eligible": "BOOLEAN NOT NULL DEFAULT FALSE",
    "is_duration_recommendation_eligible": "BOOLEAN NOT NULL DEFAULT FALSE",
}

YOUTUBE_CC_COLLECTION_RUN_COLUMNS = {
    "review_artifact_path": "VARCHAR(1024) NULL",
    "review_artifact_sha256": "VARCHAR(64) NULL",
    "duplicates_skipped": "INT NOT NULL DEFAULT 0",
    "resume_count": "INT NOT NULL DEFAULT 0",
    "last_resumed_at": "DATETIME NULL",
}

VIEW_METRIC_COLUMNS = {
    "dataset_contents": {
        "view_metric_version": (
            f"VARCHAR(64) NOT NULL DEFAULT '{UNKNOWN_VIEW_METRIC}'"
        ),
    },
    "trend_snapshot_items": {
        "view_metric_version": (
            f"VARCHAR(64) NOT NULL DEFAULT '{UNKNOWN_VIEW_METRIC}'"
        ),
    },
}

TREND_SCOPE_RUN_COLUMNS = {
    "snapshot_kind": "VARCHAR(32) NOT NULL DEFAULT 'global'",
}

TREND_SCOPE_ITEM_COLUMNS = {
    "ranking_scope": "VARCHAR(64) NOT NULL DEFAULT 'global'",
    "category_id": "VARCHAR(32) NULL",
    "provider_rank": "INT NOT NULL DEFAULT 0",
}

TREND_DETAIL_ITEM_COLUMNS = {
    "channel_title": "VARCHAR(255) NULL",
    "thumbnail_url": "VARCHAR(1024) NULL",
    "description": "TEXT NULL",
    "duration_seconds": "INT NULL",
    "views_available": "BOOLEAN NULL",
    "likes_available": "BOOLEAN NULL",
    "comments_available": "BOOLEAN NULL",
    "search_volume": "INT NULL",
}


def _available_archive_name(connection, base_name: str) -> str:
    tables = set(inspect(connection).get_table_names())
    if base_name not in tables:
        return base_name
    suffix = 2
    while f"{base_name}_{suffix}" in tables:
        suffix += 1
    return f"{base_name}_{suffix}"


def archive_phase10_notification_tables(engine: Engine) -> Dict[str, str]:
    """Archive incompatible Phase 10 tables before SQLAlchemy creates Phase 11 tables."""
    archived: Dict[str, str] = {}
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        if "notifications" in tables:
            columns = {column["name"] for column in inspector.get_columns("notifications")}
            is_phase11 = {"watch_session_id", "trend_key", "platform", "detected_at"}.issubset(columns)
            if not is_phase11:
                archive_name = _available_archive_name(connection, "notifications_legacy_phase10")
                if connection.dialect.name == "mysql":
                    connection.execute(text(f"RENAME TABLE notifications TO {archive_name}"))
                else:
                    connection.execute(text(f"ALTER TABLE notifications RENAME TO {archive_name}"))
                archived["notifications"] = archive_name

        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "user_trend_snapshots" in tables:
            archive_name = _available_archive_name(connection, "user_trend_snapshots_legacy_phase10")
            if connection.dialect.name == "mysql":
                connection.execute(text(f"RENAME TABLE user_trend_snapshots TO {archive_name}"))
            else:
                connection.execute(text(f"ALTER TABLE user_trend_snapshots RENAME TO {archive_name}"))
            archived["user_trend_snapshots"] = archive_name

    return archived


def migrate_phase13_taxonomy_schema(engine: Engine) -> Dict[str, object]:
    """Add Phase 13 columns to existing databases without rewriting legacy rows."""
    added_columns: list[str] = []
    added_indexes: list[str] = []
    added_constraints: list[str] = []
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        for table_name, definitions in (
            ("dataset_contents", PHASE13_DATASET_COLUMNS),
            ("analysis_results", PHASE13_ANALYSIS_COLUMNS),
            ("model_evaluation_metrics", PHASE13_MODEL_METRIC_COLUMNS),
        ):
            if table_name not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, sql_type in definitions.items():
                if column_name in existing:
                    continue
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}")
                )
                added_columns.append(f"{table_name}.{column_name}")

        inspector = inspect(connection)

        def ensure_index(
            table_name: str,
            index_name: str,
            columns: tuple[str, ...],
            *,
            unique: bool = False,
        ) -> None:
            if table_name not in tables:
                return
            index_names = {
                str(index.get("name")) for index in inspector.get_indexes(table_name)
            }
            constraint_names = {
                str(item.get("name"))
                for item in inspector.get_unique_constraints(table_name)
            }
            if index_name in index_names or index_name in constraint_names:
                return
            unique_sql = "UNIQUE " if unique else ""
            connection.execute(
                text(
                    f"CREATE {unique_sql}INDEX {index_name} ON {table_name} "
                    f"({', '.join(columns)})"
                )
            )
            added_indexes.append(index_name)

        ensure_index(
            "dataset_contents",
            "uq_dataset_source_version_record",
            ("dataset_source", "dataset_version", "source_record_id"),
            unique=True,
        )
        ensure_index(
            "dataset_contents",
            "ix_dataset_taxonomy_leaf",
            ("taxonomy_version", "taxonomy_leaf_key"),
        )
        ensure_index(
            "dataset_contents",
            "ix_dataset_contents_taxonomy_leaf_key",
            ("taxonomy_leaf_key",),
        )
        ensure_index(
            "analysis_results",
            "ix_analysis_results_classification_model_id",
            ("classification_model_id",),
        )

        if connection.dialect.name == "mysql" and "model_evaluation_metrics" in tables:
            metric_unique = next(
                (
                    item
                    for item in inspector.get_unique_constraints("model_evaluation_metrics")
                    if item.get("name") == "uq_model_evaluation_metric"
                ),
                None,
            )
            expected_metric_columns = [
                "model_id",
                "dataset_split",
                "language",
                "taxonomy_level",
                "taxonomy_leaf_key",
                "metric_name",
            ]
            if metric_unique and metric_unique.get("column_names") != expected_metric_columns:
                connection.execute(
                    text(
                        "ALTER TABLE model_evaluation_metrics "
                        "DROP INDEX uq_model_evaluation_metric"
                    )
                )
                connection.execute(
                    text(
                        "ALTER TABLE model_evaluation_metrics "
                        "ADD CONSTRAINT uq_model_evaluation_metric UNIQUE "
                        "(model_id, dataset_split, language, taxonomy_level, "
                        "taxonomy_leaf_key, metric_name)"
                    )
                )
                added_constraints.append("uq_model_evaluation_metric:replaced")

        if (
            connection.dialect.name == "mysql"
            and "analysis_results" in tables
            and "classification_models" in tables
        ):
            foreign_keys = inspector.get_foreign_keys("analysis_results")
            has_model_foreign_key = any(
                item.get("constrained_columns") == ["classification_model_id"]
                for item in foreign_keys
            )
            if not has_model_foreign_key:
                constraint_name = "fk_analysis_results_classification_model"
                connection.execute(
                    text(
                        "ALTER TABLE analysis_results "
                        f"ADD CONSTRAINT {constraint_name} "
                        "FOREIGN KEY (classification_model_id) "
                        "REFERENCES classification_models(model_id) ON DELETE SET NULL"
                    )
                )
                added_constraints.append(constraint_name)

    return {
        "added_columns": added_columns,
        "added_indexes": added_indexes,
        "added_constraints": added_constraints,
    }


def migrate_phase19_transcript_schema(engine: Engine) -> Dict[str, object]:
    """Add auditable raw and cleaned transcripts to saved user analyses."""
    added_columns: list[str] = []
    backfilled_rows = 0
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "user_contents" not in set(inspector.get_table_names()):
            return {
                "added_columns": added_columns,
                "backfilled_rows": backfilled_rows,
            }

        existing = {
            column["name"] for column in inspector.get_columns("user_contents")
        }
        for column_name, mysql_type in PHASE19_USER_CONTENT_COLUMNS.items():
            if column_name in existing:
                continue
            column_type = mysql_type if connection.dialect.name == "mysql" else "TEXT NULL"
            connection.execute(
                text(
                    "ALTER TABLE user_contents "
                    f"ADD COLUMN {column_name} {column_type}"
                )
            )
            added_columns.append(f"user_contents.{column_name}")

        result = connection.execute(
            text(
                "UPDATE user_contents SET "
                "raw_transcript = CASE "
                "WHEN raw_transcript IS NULL OR TRIM(raw_transcript) = '' "
                "THEN transcript ELSE raw_transcript END, "
                "cleaned_transcript = CASE "
                "WHEN cleaned_transcript IS NULL OR TRIM(cleaned_transcript) = '' "
                "THEN transcript ELSE cleaned_transcript END "
                "WHERE transcript IS NOT NULL AND TRIM(transcript) <> '' "
                "AND (raw_transcript IS NULL OR TRIM(raw_transcript) = '' "
                "OR cleaned_transcript IS NULL OR TRIM(cleaned_transcript) = '')"
            )
        )
        backfilled_rows = max(int(result.rowcount or 0), 0)

    return {
        "added_columns": added_columns,
        "backfilled_rows": backfilled_rows,
    }


def migrate_scope_completion_schema(engine: Engine) -> Dict[str, object]:
    definitions = {
        "dataset_contents": {"deleted_at": "DATETIME NULL", "deletion_state_json": "TEXT NULL"},
        "system_configs": {
            "trend_refresh_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
            "trend_refresh_seconds": "INT NULL",
            "youtube_category_refresh_seconds": "INT NULL",
            "trend_notification_mode": "VARCHAR(20) NOT NULL DEFAULT 'all'",
        },
        "followed_topics": {"platform": "VARCHAR(20) NOT NULL DEFAULT 'all'"},
        # This is a cursor, not evidence. A missing retained run is re-baselined.
        "user_trend_watch_sessions": {"last_seen_category_run_id": "INT NULL"},
    }
    added = []
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        for table, columns in definitions.items():
            if table not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name in existing:
                    continue
                if connection.dialect.name == "postgresql":
                    definition = definition.replace("DATETIME", "TIMESTAMP")
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
                added.append(f"{table}.{name}")
    return {"added_columns": added}


def migrate_trend_scheduler_schema(engine: Engine) -> Dict[str, object]:
    definitions = {
        "trend_schedule_mode": "VARCHAR(20) NOT NULL DEFAULT 'interval'",
        "trend_window_start_hour": "INT NOT NULL DEFAULT 14",
        "trend_window_end_hour": "INT NOT NULL DEFAULT 23",
        "trend_worker_seen_at": "DATETIME NULL",
        "trend_worker_status": "VARCHAR(40) NULL",
    }
    added = []
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "system_configs" not in inspector.get_table_names():
            return {"added_columns": []}
        existing = {c["name"] for c in inspector.get_columns("system_configs")}
        for name, definition in definitions.items():
            if name not in existing:
                if connection.dialect.name == "postgresql":
                    definition = definition.replace("DATETIME", "TIMESTAMP")
                connection.execute(text(f"ALTER TABLE system_configs ADD COLUMN {name} {definition}"))
                added.append(name)
    return {"added_columns": added}


def migrate_analysis_settings_schema(engine: Engine) -> Dict[str, object]:
    with engine.begin() as connection:
        if "system_configs" not in inspect(connection).get_table_names():
            return {"added_columns": []}
        columns = {column["name"] for column in inspect(connection).get_columns("system_configs")}
        added = []
        if "upload_max_duration_seconds" not in columns:
            connection.execute(text(
                "ALTER TABLE system_configs ADD COLUMN upload_max_duration_seconds INT NOT NULL DEFAULT 300"
            ))
            added.append("upload_max_duration_seconds")
        return {"added_columns": added}


def migrate_training_requestor_schema(engine: Engine) -> Dict[str, object]:
    """Keep historical training runs when their requesting account is deleted."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "model_training_runs" not in inspector.get_table_names():
            return {"changed": False}
        column = next(c for c in inspector.get_columns("model_training_runs") if c["name"] == "requested_by")
        if column["nullable"]:
            return {"changed": False}
        dialect = connection.dialect.name
        if dialect in {"mysql", "mariadb"}:
            connection.execute(text("ALTER TABLE model_training_runs MODIFY COLUMN requested_by INT NULL"))
        elif dialect == "postgresql":
            connection.execute(text("ALTER TABLE model_training_runs ALTER COLUMN requested_by DROP NOT NULL"))
        else:
            # Fresh SQLite test databases use the nullable model definition.
            return {"changed": False, "requires_manual_migration": True}
        return {"changed": True}


def migrate_analysis_payload_schema(engine: Engine) -> Dict[str, object]:
    """Allow saved analysis JSON to exceed MySQL TEXT's 64 KiB limit."""
    widened_columns: list[str] = []
    with engine.begin() as connection:
        if connection.dialect.name != "mysql":
            return {"widened_columns": widened_columns}
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        # These names are fixed schema identifiers, never user input.
        for table_name, column_name in (
            ("analysis_results", "summary"),
            ("recommendations", "recommended_keywords"),
        ):
            if table_name not in tables:
                continue
            payload_column = next(
                (
                    column
                    for column in inspector.get_columns(table_name)
                    if column["name"] == column_name
                ),
                None,
            )
            if payload_column is None or str(payload_column["type"]).upper().startswith("LONGTEXT"):
                continue
            connection.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"MODIFY COLUMN {column_name} LONGTEXT NULL"
                )
            )
            widened_columns.append(f"{table_name}.{column_name}")

    return {"widened_columns": widened_columns}


def migrate_youtube_cc_dataset_schema(engine: Engine) -> Dict[str, object]:
    """Add YouTube provenance fields and disable non-production evidence."""
    added_columns: list[str] = []
    added_indexes: list[str] = []
    added_constraints: list[str] = []
    widened_columns: list[str] = []
    legacy_rows_deactivated = 0

    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        if connection.dialect.name == "mysql":
            for table_name in ("user_contents", "dataset_contents"):
                if table_name not in tables:
                    continue
                transcript_column = next(
                    (
                        column
                        for column in inspector.get_columns(table_name)
                        if column["name"] == "transcript"
                    ),
                    None,
                )
                if transcript_column is None:
                    continue
                if str(transcript_column["type"]).upper() == "LONGTEXT":
                    continue
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        "MODIFY COLUMN transcript LONGTEXT NULL"
                    )
                )
                widened_columns.append(f"{table_name}.transcript")

        if "dataset_collection_runs" in tables:
            run_columns = {
                column["name"]
                for column in inspector.get_columns("dataset_collection_runs")
            }
            for column_name, sql_type in YOUTUBE_CC_COLLECTION_RUN_COLUMNS.items():
                if column_name in run_columns:
                    continue
                connection.execute(
                    text(
                        "ALTER TABLE dataset_collection_runs "
                        f"ADD COLUMN {column_name} {sql_type}"
                    )
                )
                added_columns.append(f"dataset_collection_runs.{column_name}")

        if "dataset_contents" not in tables:
            return {
                "added_columns": added_columns,
                "added_indexes": added_indexes,
                "added_constraints": added_constraints,
                "widened_columns": widened_columns,
                "legacy_rows_deactivated": legacy_rows_deactivated,
            }

        existing_columns = {
            column["name"] for column in inspector.get_columns("dataset_contents")
        }
        for column_name, sql_type in YOUTUBE_CC_DATASET_COLUMNS.items():
            if column_name in existing_columns:
                continue
            connection.execute(
                text(f"ALTER TABLE dataset_contents ADD COLUMN {column_name} {sql_type}")
            )
            added_columns.append(f"dataset_contents.{column_name}")

        inspector = inspect(connection)
        available_columns = {
            column["name"] for column in inspector.get_columns("dataset_contents")
        }
        index_names = {
            str(item.get("name")) for item in inspector.get_indexes("dataset_contents")
        }
        unique_names = {
            str(item.get("name"))
            for item in inspector.get_unique_constraints("dataset_contents")
        }

        def ensure_index(name: str, columns: tuple[str, ...], *, unique: bool = False) -> None:
            if not set(columns).issubset(available_columns):
                return
            if name in index_names or name in unique_names:
                return
            unique_sql = "UNIQUE " if unique else ""
            connection.execute(
                text(
                    f"CREATE {unique_sql}INDEX {name} ON dataset_contents "
                    f"({', '.join(columns)})"
                )
            )
            added_indexes.append(name)

        ensure_index("uq_dataset_source_youtube_id", ("source_youtube_id",), unique=True)
        ensure_index("uq_dataset_transcript_sha256", ("transcript_sha256",), unique=True)
        ensure_index("ix_dataset_contents_creator_group_key", ("creator_group_key",))
        ensure_index("ix_dataset_contents_source_channel_id", ("source_channel_id",))
        ensure_index("ix_dataset_contents_collection_run_id", ("collection_run_id",))
        ensure_index(
            "ix_dataset_training_eligibility",
            ("is_training_eligible", "data_split", "taxonomy_leaf_key"),
        )

        result = connection.execute(
            text(
                "UPDATE dataset_contents SET is_active = FALSE, "
                "is_training_eligible = FALSE "
                "WHERE (source_platform LIKE '%_seed' "
                "OR source_platform = 'seed' "
                "OR dataset_source IN ('demo_seed', 'mmsum')"
                ") AND (is_active = TRUE OR is_training_eligible = TRUE)"
            )
        )
        legacy_rows_deactivated = max(int(result.rowcount or 0), 0)

        connection.execute(
            text(
                "UPDATE dataset_contents SET "
                "is_keyword_recommendation_eligible = CASE "
                "WHEN dataset_source IN ('youtube_cc', 'youtube_public_research') "
                "AND is_training_eligible = TRUE "
                "AND is_active = TRUE THEN TRUE ELSE FALSE END"
            )
        )
        connection.execute(
            text(
                "UPDATE dataset_contents SET "
                "transcript_acquisition_method = "
                "COALESCE(transcript_acquisition_method, 'youtube_transcript_api'), "
                "transcript_scope = COALESCE(transcript_scope, 'first_window') "
                "WHERE dataset_source IN ('youtube_cc', 'youtube_public_research')"
            )
        )
        connection.execute(
            text(
                "UPDATE dataset_contents SET "
                "is_duration_recommendation_eligible = CASE "
                "WHEN dataset_source IN ('youtube_cc', 'youtube_public_research') "
                "AND is_training_eligible = TRUE "
                "AND is_active = TRUE "
                "AND duration_seconds > 0 "
                "AND duration_seconds <= 300 THEN TRUE ELSE FALSE END"
            )
        )

        if connection.dialect.name == "mysql" and "dataset_collection_runs" in tables:
            inspector = inspect(connection)
            foreign_keys = inspector.get_foreign_keys("dataset_contents")
            has_collection_run_fk = any(
                item.get("constrained_columns") == ["collection_run_id"]
                for item in foreign_keys
            )
            if not has_collection_run_fk:
                constraint_name = "fk_dataset_contents_collection_run"
                connection.execute(
                    text(
                        "ALTER TABLE dataset_contents "
                        f"ADD CONSTRAINT {constraint_name} "
                        "FOREIGN KEY (collection_run_id) "
                        "REFERENCES dataset_collection_runs(collection_run_id) "
                        "ON DELETE SET NULL"
                    )
                )
                added_constraints.append(constraint_name)

        if "classification_models" in tables:
            connection.execute(
                text(
                    "UPDATE classification_models SET is_active = FALSE, status = 'legacy' "
                    "WHERE training_dataset_source IN ('demo_seed', 'mmsum')"
                )
            )

    return {
        "added_columns": added_columns,
        "added_indexes": added_indexes,
        "added_constraints": added_constraints,
        "widened_columns": widened_columns,
        "legacy_rows_deactivated": legacy_rows_deactivated,
    }


def migrate_view_metric_schema(engine: Engine) -> Dict[str, object]:
    """Version public view counts and backfill existing metric snapshots."""
    added_columns: list[str] = []
    added_indexes: list[str] = []
    backfilled_rows: dict[str, int] = {}
    cutoff = YOUTUBE_VIEW_METRIC_CHANGE_AT.replace(tzinfo=None).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        for table_name, definitions in VIEW_METRIC_COLUMNS.items():
            if table_name not in tables:
                continue
            existing = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, sql_type in definitions.items():
                if column_name in existing:
                    continue
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {sql_type}"
                    )
                )
                added_columns.append(f"{table_name}.{column_name}")

        inspector = inspect(connection)

        def ensure_index(
            table_name: str,
            index_name: str,
            columns: tuple[str, ...],
        ) -> None:
            if table_name not in tables:
                return
            names = {
                str(item.get("name"))
                for item in inspector.get_indexes(table_name)
            }
            if index_name in names:
                return
            connection.execute(
                text(
                    f"CREATE INDEX {index_name} ON {table_name} "
                    f"({', '.join(columns)})"
                )
            )
            added_indexes.append(index_name)

        ensure_index(
            "dataset_contents",
            "ix_dataset_view_metric_leaf",
            ("view_metric_version", "taxonomy_leaf_key"),
        )
        ensure_index(
            "trend_snapshot_items",
            "ix_trend_snapshot_platform_metric",
            ("platform", "view_metric_version"),
        )

        if "dataset_contents" in tables:
            result = connection.execute(
                text(
                    "UPDATE dataset_contents SET view_metric_version = CASE "
                    "WHEN LOWER(COALESCE(source_platform, '')) LIKE 'youtube%' "
                    "AND COALESCE(statistics_captured_at, created_at) < :cutoff "
                    "THEN :youtube_v1 "
                    "WHEN LOWER(COALESCE(source_platform, '')) LIKE 'youtube%' "
                    "THEN :youtube_v2 "
                    "WHEN LOWER(COALESCE(source_platform, '')) LIKE 'google%' "
                    "THEN :google_v1 "
                    "WHEN LOWER(COALESCE(source_platform, '')) LIKE 'tiktok%' "
                    "THEN :tiktok_v1 ELSE :provider_v1 END "
                    "WHERE view_metric_version IS NULL "
                    "OR view_metric_version = '' "
                    "OR view_metric_version = :unknown"
                ),
                {
                    "cutoff": cutoff,
                    "youtube_v1": YOUTUBE_QUALIFIED_VIEW_V1,
                    "youtube_v2": YOUTUBE_PLAY_START_VIEW_V2,
                    "google_v1": GOOGLE_INTEREST_V1,
                    "tiktok_v1": TIKTOK_PUBLIC_VIEW_V1,
                    "provider_v1": PROVIDER_NATIVE_V1,
                    "unknown": UNKNOWN_VIEW_METRIC,
                },
            )
            backfilled_rows["dataset_contents"] = max(
                int(result.rowcount or 0),
                0,
            )

        if "trend_snapshot_items" in tables:
            result = connection.execute(
                text(
                    "UPDATE trend_snapshot_items SET view_metric_version = CASE "
                    "WHEN LOWER(COALESCE(platform, '')) LIKE 'youtube%' "
                    "AND created_at < :cutoff THEN :youtube_v1 "
                    "WHEN LOWER(COALESCE(platform, '')) LIKE 'youtube%' "
                    "THEN :youtube_v2 "
                    "WHEN LOWER(COALESCE(platform, '')) LIKE 'google%' "
                    "THEN :google_v1 "
                    "WHEN LOWER(COALESCE(platform, '')) LIKE 'tiktok%' "
                    "THEN :tiktok_v1 ELSE :provider_v1 END "
                    "WHERE view_metric_version IS NULL "
                    "OR view_metric_version = '' "
                    "OR view_metric_version = :unknown"
                ),
                {
                    "cutoff": cutoff,
                    "youtube_v1": YOUTUBE_QUALIFIED_VIEW_V1,
                    "youtube_v2": YOUTUBE_PLAY_START_VIEW_V2,
                    "google_v1": GOOGLE_INTEREST_V1,
                    "tiktok_v1": TIKTOK_PUBLIC_VIEW_V1,
                    "provider_v1": PROVIDER_NATIVE_V1,
                    "unknown": UNKNOWN_VIEW_METRIC,
                },
            )
            backfilled_rows["trend_snapshot_items"] = max(
                int(result.rowcount or 0),
                0,
            )

    return {
        "cutoff_utc": YOUTUBE_VIEW_METRIC_CHANGE_AT.isoformat(),
        "added_columns": added_columns,
        "added_indexes": added_indexes,
        "backfilled_rows": backfilled_rows,
    }


def migrate_trend_scope_schema(engine: Engine) -> Dict[str, object]:
    """Separate global charts from category-scoped YouTube snapshots."""
    added_columns: list[str] = []
    added_indexes: list[str] = []
    constraint_action = "unchanged"
    search_volume_backfilled_rows = 0

    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        table_columns = {
            "trend_snapshot_runs": TREND_SCOPE_RUN_COLUMNS,
            "trend_snapshot_items": {
                **TREND_SCOPE_ITEM_COLUMNS,
                **TREND_DETAIL_ITEM_COLUMNS,
            },
        }
        for table_name, definitions in table_columns.items():
            if table_name not in tables:
                continue
            existing = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, sql_type in definitions.items():
                if column_name in existing:
                    continue
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {sql_type}"
                    )
                )
                added_columns.append(f"{table_name}.{column_name}")

        if "trend_snapshot_runs" in tables:
            connection.execute(
                text(
                    "UPDATE trend_snapshot_runs SET snapshot_kind = 'global' "
                    "WHERE snapshot_kind IS NULL OR snapshot_kind = ''"
                )
            )
        if "trend_snapshot_items" in tables:
            connection.execute(
                text(
                    "UPDATE trend_snapshot_items SET ranking_scope = 'global' "
                    "WHERE ranking_scope IS NULL OR ranking_scope = ''"
                )
            )
            # Legacy Google snapshots stored provider traffic in trend_score.
            # Missing-traffic rows used only a rank fallback from 1 to 100, so
            # values above 100 are safe to recover as approximate volume.
            cast_type = (
                "SIGNED"
                if connection.dialect.name in {"mysql", "mariadb"}
                else "INTEGER"
            )
            result = connection.execute(
                text(
                    "UPDATE trend_snapshot_items "
                    f"SET search_volume = CAST(trend_score AS {cast_type}) "
                    "WHERE platform = 'google' "
                    "AND search_volume IS NULL "
                    "AND trend_score > 100"
                )
            )
            search_volume_backfilled_rows = max(int(result.rowcount or 0), 0)

        inspector = inspect(connection)

        def ensure_index(
            table_name: str,
            index_name: str,
            columns: tuple[str, ...],
        ) -> None:
            if table_name not in tables:
                return
            names = {
                str(item.get("name"))
                for item in inspector.get_indexes(table_name)
            }
            if index_name in names:
                return
            connection.execute(
                text(
                    f"CREATE INDEX {index_name} ON {table_name} "
                    f"({', '.join(columns)})"
                )
            )
            added_indexes.append(index_name)

        ensure_index(
            "trend_snapshot_runs",
            "ix_trend_snapshot_run_kind_region",
            ("snapshot_kind", "region", "status"),
        )
        ensure_index(
            "trend_snapshot_items",
            "ix_trend_snapshot_scope_category",
            ("ranking_scope", "category_id", "provider_rank"),
        )

        if "trend_snapshot_items" in tables:
            unique_names = {
                str(item.get("name"))
                for item in inspector.get_unique_constraints(
                    "trend_snapshot_items"
                )
            }
            dialect = connection.dialect.name
            old_name = "uq_trend_snapshot_item_run_platform_key"
            new_name = "uq_trend_snapshot_item_run_scope_key"
            if old_name in unique_names and new_name not in unique_names:
                if dialect in {"mysql", "mariadb"}:
                    connection.execute(
                        text(
                            "ALTER TABLE trend_snapshot_items "
                            f"DROP INDEX {old_name}"
                        )
                    )
                elif dialect == "postgresql":
                    connection.execute(
                        text(
                            "ALTER TABLE trend_snapshot_items "
                            f"DROP CONSTRAINT {old_name}"
                        )
                    )
                else:
                    old_name = ""
            if new_name not in unique_names and dialect != "sqlite":
                connection.execute(
                    text(
                        "ALTER TABLE trend_snapshot_items "
                        f"ADD CONSTRAINT {new_name} UNIQUE "
                        "(run_id, platform, ranking_scope, trend_key)"
                    )
                )
                constraint_action = "replaced" if old_name else "added"

    return {
        "added_columns": added_columns,
        "added_indexes": added_indexes,
        "unique_constraint": constraint_action,
        "search_volume_backfilled_rows": search_volume_backfilled_rows,
    }


def migrate_classification_split_strategy(engine: Engine) -> Dict[str, object]:
    """Reassign reviewed YouTube rows to the current channel-grouped split."""
    updated_rows = 0
    skipped_rows = 0
    with engine.begin() as connection:
        from app.services.dataset_split_plan import load_split_registry
        overrides = load_split_registry(connection)["overrides"]
        inspector = inspect(connection)
        if "dataset_contents" not in set(inspector.get_table_names()):
            return {
                "split_strategy": SPLIT_STRATEGY,
                "updated_rows": 0,
                "skipped_rows": 0,
            }

        rows = connection.execute(
            text(
                "SELECT dataset_id, source_channel_id, data_split, split_strategy, "
                "creator_group_key FROM dataset_contents "
                "WHERE dataset_source IN :dataset_sources "
                "AND source_channel_id IS NOT NULL "
                "AND TRIM(source_channel_id) <> ''"
            ).bindparams(bindparam("dataset_sources", expanding=True)),
            {"dataset_sources": tuple(SUPPORTED_YOUTUBE_DATASET_SOURCES)},
        ).mappings()
        for row in rows:
            try:
                split, creator_group_key = channel_dataset_split(
                    str(row["source_channel_id"]), overrides=overrides
                )
            except ValueError:
                skipped_rows += 1
                continue
            strategy = HOLDOUT_SPLIT_STRATEGY if row["source_channel_id"] in overrides else SPLIT_STRATEGY
            if (
                str(row["data_split"] or "") == split
                and str(row["split_strategy"] or "") == strategy
                and str(row["creator_group_key"] or "") == creator_group_key
            ):
                continue
            connection.execute(
                text(
                    "UPDATE dataset_contents SET data_split = :data_split, "
                    "split_strategy = :split_strategy, creator_group_key = :group_key "
                    "WHERE dataset_id = :dataset_id"
                ),
                {
                    "data_split": split,
                    "split_strategy": strategy,
                    "group_key": creator_group_key,
                    "dataset_id": int(row["dataset_id"]),
                },
            )
            updated_rows += 1

    return {
        "split_strategy": SPLIT_STRATEGY,
        "updated_rows": updated_rows,
        "skipped_rows": skipped_rows,
    }
