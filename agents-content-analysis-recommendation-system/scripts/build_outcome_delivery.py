"""Build a checksummed, secret-free Outcome Prediction delivery package."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.request import urlopen

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.database import models  # noqa: E402,F401
from app.database.db import Base, SessionLocal, engine  # noqa: E402
from app.database.models import (  # noqa: E402
    AnalysisResult,
    ClassificationModel,
    ClipRevisionComparison,
    ClipRevisionPlan,
    DatasetContent,
    OutcomeModel,
    ReferenceVideoStatistic,
    UserContent,
)
from app.services.analysis_settings import get_analysis_settings  # noqa: E402
from app.services.classification_readiness import classification_model_snapshot  # noqa: E402
from app.services.outcome_prediction_readiness import reject_database_writes  # noqa: E402
from app.services.outcome_training import CALIBRATION_VERSION  # noqa: E402


SCHEMA_VERSION = "outcome-prediction-delivery-v1"
PACKAGE_FILES = (
    "docs/presentation/outcome-prediction/README.md",
    "docs/presentation/outcome-prediction/algorithm-explained.md",
    "docs/presentation/outcome-prediction/evaluation-and-limitations.md",
    "docs/presentation/outcome-prediction/demo-and-questions.md",
    "docs/presentation/outcome-prediction/operations-runbook.md",
    "docs/implementation/outcome-prediction-protocol-v1.json",
    "docs/implementation/outcome-feature-schema-v1.json",
)
SOURCE_ROOTS = (
    "app",
    "scripts",
    "tests",
    "frontend_flutter/lib",
    "frontend_flutter/test",
    "docs/prompts/outcome-prediction",
    "docs/implementation",
    "docs/presentation/outcome-prediction",
)
SOURCE_SUFFIXES = {".py", ".ps1", ".cjs", ".dart", ".md", ".json", ".yaml", ".yml"}
ROOT_FILES = ("README.md", "requirements.txt", ".env.example", "frontend_flutter/pubspec.yaml", "frontend_flutter/pubspec.lock")
PACKAGE_NAMES = (
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "numpy",
    "scipy",
    "scikit-learn",
    "pythainlp",
    "sentence-transformers",
    "faster-whisper",
    "keybert",
    "joblib",
)
FORBIDDEN_PACKAGE_SUFFIXES = {".mp4", ".mov", ".avi", ".jsonl", ".sqlite", ".sqlite3", ".db"}


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json(path: Path | str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def relative_path(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return "outside_workspace"


def source_records() -> list[dict[str, Any]]:
    files: set[Path] = set()
    for root_name in SOURCE_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in SOURCE_SUFFIXES
                and "__pycache__" not in path.parts
            ):
                files.add(path)
    for name in ROOT_FILES:
        path = ROOT / name
        if path.is_file():
            files.add(path)
    rows = []
    for path in sorted(files):
        name = path.relative_to(ROOT).as_posix()
        if name == ".env" or name.startswith("artifacts/") or name.startswith("videos/"):
            raise RuntimeError(f"Forbidden source path entered manifest: {name}")
        rows.append({"path": name, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


def source_tree_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {}
    for root_name in SOURCE_ROOTS:
        prefix = root_name.rstrip("/") + "/"
        selected = [item for item in records if item["path"].startswith(prefix)]
        groups[root_name] = {
            "file_count": len(selected),
            "sha256": canonical_sha256(selected),
        }
    root_selected = [item for item in records if item["path"] in ROOT_FILES]
    groups["root_contracts"] = {
        "file_count": len(root_selected),
        "sha256": canonical_sha256(root_selected),
    }
    return groups


def schema_contract() -> dict[str, Any]:
    tables = []
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        tables.append({
            "name": table.name,
            "columns": [
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": bool(column.nullable),
                    "primary_key": bool(column.primary_key),
                    "foreign_keys": sorted(str(key.target_fullname) for key in column.foreign_keys),
                }
                for column in table.columns
            ],
            "indexes": sorted(index.name or "" for index in table.indexes),
        })
    return {
        "schema_version": "content-ai-schema-contract-v1",
        "migration_strategy": "idempotent SQLAlchemy migrations; no Alembic revision table",
        "migrations_file": "app/database/migrations.py",
        "migrations_sha256": sha256_file(ROOT / "app/database/migrations.py"),
        "table_count": len(tables),
        "tables": tables,
        "schema_sha256": canonical_sha256(tables),
    }


def git_identity() -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            capture_output=True, timeout=10, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--short"], cwd=ROOT, text=True,
            capture_output=True, timeout=10, check=True,
        ).stdout.splitlines()
        return {"available": True, "commit": commit, "dirty": bool(status)}
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "reason": "broken_or_unavailable_worktree_metadata",
            "detail": str(exc).splitlines()[0][:240],
        }


def package_versions() -> dict[str, str | None]:
    versions = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def env_key_names() -> list[str]:
    result = []
    for raw in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            result.append(line.split("=", 1)[0].strip())
    return sorted(set(result))


def _parse_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def database_snapshot() -> dict[str, Any]:
    with reject_database_writes(engine):
        with SessionLocal() as db:
            classifier = db.query(ClassificationModel).filter_by(is_active=True).one_or_none()
            classifier_snapshot = classification_model_snapshot(classifier)
            outcome_rows = db.query(OutcomeModel).order_by(OutcomeModel.model_id).all()
            active_outcome = [row for row in outcome_rows if row.is_active]
            if len(active_outcome) > 1:
                raise RuntimeError("Multiple active Outcome models")

            historical = []
            rows = db.query(AnalysisResult, UserContent).join(
                UserContent, AnalysisResult.content_id == UserContent.content_id
            ).order_by(AnalysisResult.created_at.desc()).limit(100).all()
            wanted = {"recommendation": False, "unknown": False}
            for analysis, content in rows:
                payload = _parse_payload(analysis.summary)
                recommendation = payload.get("recommendation") or {}
                advice = recommendation.get("actionable_recommendations") or {}
                kind = None
                if not wanted["recommendation"] and advice.get("status") == "ready":
                    kind = "recommendation"
                elif not wanted["unknown"] and analysis.classification_is_unknown:
                    kind = "unknown"
                if kind:
                    wanted[kind] = True
                    historical.append({
                        "kind": kind,
                        "evidence_type": "historical_saved_result",
                        "content_id": content.content_id,
                        "analysis_id": analysis.result_id,
                        "created_at": analysis.created_at,
                        "category": analysis.taxonomy_leaf_key,
                        "recommendation_status": advice.get("status"),
                        "outcome_status": (payload.get("outcome_assessment") or {}).get("status")
                        or "legacy_not_assessed",
                    })
                if all(wanted.values()):
                    break

            result = {
                "database": {
                    "dialect": engine.url.get_backend_name(),
                    "database_name": engine.url.database,
                    "url_recorded": False,
                    "dataset_rows": db.query(DatasetContent).count(),
                    "latest_reference_observation": db.query(
                        func.max(ReferenceVideoStatistic.observed_at)
                    ).scalar(),
                },
                "classification": {
                    "model_id": classifier_snapshot.get("model_id"),
                    "model_key": classifier_snapshot.get("model_key"),
                    "model_version": classifier_snapshot.get("model_version"),
                    "status": classifier_snapshot.get("status"),
                    "artifact_sha256": classifier_snapshot.get("artifact_sha256"),
                    "taxonomy_version": classifier_snapshot.get("taxonomy_version"),
                    "unknown_threshold": classifier_snapshot.get("unknown_threshold"),
                    "readiness": {
                        "status": (classifier_snapshot.get("readiness") or {}).get("status"),
                        "reason_codes": (classifier_snapshot.get("readiness") or {}).get("reason_codes") or [],
                        "can_accept_predictions": (
                            classifier_snapshot.get("readiness") or {}
                        ).get("can_accept_predictions") is True,
                    },
                },
                "outcome": {
                    "registered_models": len(outcome_rows),
                    "active_model_id": active_outcome[0].model_id if active_outcome else None,
                    "qualified_active": bool(
                        active_outcome
                        and active_outcome[0].status == "qualified"
                        and active_outcome[0].independent_test_passed
                        and active_outcome[0].production_eligible
                    ),
                },
                "analysis_settings": get_analysis_settings(db, admin=True),
                "demo_examples": historical,
                "revision": {
                    "saved_plan_count": db.query(ClipRevisionPlan).count(),
                    "comparison_count": db.query(ClipRevisionComparison).count(),
                },
            }
            db.rollback()
            return result


def runtime_health(backend_url: str, web_url: str) -> dict[str, Any]:
    output: dict[str, Any] = {
        "backend_url": backend_url.rstrip("/"),
        "web_url": web_url.rstrip("/"),
        "backend_http_status": None,
        "web_http_status": None,
        "health": None,
    }
    try:
        with urlopen(backend_url.rstrip("/") + "/health", timeout=10) as response:
            output["backend_http_status"] = response.status
            health = json.loads(response.read().decode("utf-8"))
            output["health"] = {
                "status": health.get("status"),
                "database_status": (health.get("database") or {}).get("status"),
                "asr_ready": ((health.get("ai_models") or {}).get("faster_whisper") or {}).get("ready"),
                "trend_providers": {
                    name: {
                        "status": item.get("status"),
                        "mode": item.get("mode"),
                        "last_checked_at": item.get("last_checked_at"),
                    }
                    for name, item in ((health.get("live_trends") or {}).get("providers") or {}).items()
                },
            }
    except Exception as exc:
        output["backend_error"] = f"{exc.__class__.__name__}: {exc}"[:300]
    try:
        with urlopen(web_url.rstrip("/"), timeout=10) as response:
            output["web_http_status"] = response.status
    except Exception as exc:
        output["web_error"] = f"{exc.__class__.__name__}: {exc}"[:300]
    return output


def verify_phase6_bundle(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    integrity = load_json(path / "integrity.json")
    mismatches = []
    for name, expected in (integrity.get("files") or {}).items():
        target = path / name
        if not target.is_file() or sha256_file(target) != expected:
            mismatches.append(name)
    if mismatches:
        raise RuntimeError(f"Phase 6 integrity mismatch: {mismatches}")
    release = load_json(path / "release-decision.json")
    return integrity, release


def verify_private_backup(path: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    expected = (path / "manifest.sha256").read_text(encoding="ascii").split()[0]
    actual = sha256_file(manifest_path)
    if expected != actual:
        raise RuntimeError("Private backup manifest checksum mismatch")
    manifest = load_json(manifest_path)
    return {
        "path": relative_path(path),
        "manifest_sha256": actual,
        "schema_version": manifest.get("schema_version"),
        "privacy": manifest.get("privacy"),
        "shareable": False,
        "table_count": len(manifest.get("database_tables") or []),
        "row_total": manifest.get("database_row_total"),
        "private_env_included": (manifest.get("environment") or {}).get("private_env_included"),
        "outcome_contract": manifest.get("outcome_contract"),
        "outcome_registry": manifest.get("outcome_registry"),
    }


def verify_restore_report(path: Path, backup: dict[str, Any]) -> dict[str, Any]:
    report = load_json(path)
    if report.get("passed") is not True:
        raise RuntimeError("Restore report did not pass")
    if report.get("backup_manifest_sha256") != backup["manifest_sha256"]:
        raise RuntimeError("Restore report does not belong to the selected backup")
    return {
        "path": relative_path(path),
        "passed": True,
        "target": "separate_sqlite_database",
        "source_database_was_not_modified": report.get("source_database_was_not_modified") is True,
        "table_count": len(report.get("tables") or []),
        "row_total": report.get("row_total"),
        "backup_manifest_sha256": report.get("backup_manifest_sha256"),
    }


def copy_shareable_package(output: Path, manifest_files: list[Path]) -> dict[str, Any]:
    package = output / "shareable-package"
    package.mkdir()
    copied = []
    for source in [*(ROOT / item for item in PACKAGE_FILES), *manifest_files]:
        if not source.is_file():
            raise FileNotFoundError(f"Required shareable file is missing: {source}")
        if source.name == ".env" or source.suffix.lower() in FORBIDDEN_PACKAGE_SUFFIXES:
            raise RuntimeError(f"Forbidden file in shareable package: {source.name}")
        if output in source.resolve().parents:
            relative = Path("release") / source.name
        elif ROOT in source.resolve().parents:
            relative = source.resolve().relative_to(ROOT)
        else:
            relative = Path("release") / source.name
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append({
            "path": target.relative_to(package).as_posix(),
            "size": target.stat().st_size,
            "sha256": sha256_file(target),
        })
    package_manifest = {
        "schema_version": "outcome-shareable-package-v1",
        "privacy": "allowlisted documentation and metadata only",
        "contains_database_rows": False,
        "contains_user_videos": False,
        "contains_transcripts": False,
        "contains_credentials": False,
        "files": copied,
    }
    package_manifest["package_sha256"] = canonical_sha256(copied)
    path = package / "manifest.json"
    path.write_text(json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (package / "manifest.sha256").write_text(
        f"{sha256_file(path)}  manifest.json\n", encoding="ascii"
    )
    return package_manifest


def create_release(
    *,
    output: Path,
    phase6_bundle: Path,
    private_backup: Path,
    restore_report_path: Path,
    browser_evidence_path: Path,
    flutter_version_path: Path,
    backend_url: str,
    web_url: str,
) -> dict[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    records = source_records()
    schema = schema_contract()
    phase6_integrity, phase6_release = verify_phase6_bundle(phase6_bundle)
    backup = verify_private_backup(private_backup)
    restore = verify_restore_report(restore_report_path, backup)
    browser = load_json(browser_evidence_path)
    if browser.get("passed") is not True:
        raise RuntimeError("Browser evidence did not pass")
    protocol = load_json(ROOT / "docs/implementation/outcome-prediction-protocol-v1.json")
    feature = load_json(ROOT / "docs/implementation/outcome-feature-schema-v1.json")
    rights = load_json(ROOT / "docs/implementation/outcome-prediction-data-use-v1.json")
    readiness = load_json(
        ROOT / "artifacts/outcome-prediction/phase-6/20261009T115547Z-readiness/readiness.json"
    )
    flutter_version = load_json(flutter_version_path)
    db = database_snapshot()

    source_manifest = {
        "schema_version": "outcome-source-hashes-v1",
        "git": git_identity(),
        "file_count": len(records),
        "tree_sha256": canonical_sha256(records),
        "groups": source_tree_summary(records),
        "files": records,
    }
    source_path = output / "source-hashes.json"
    source_path.write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    schema_path = output / "schema-contract.json"
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    acceptance = {item["area"]: item["status"] for item in phase6_release.get("matrix") or []}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "release_name": "content-ai-outcome-prediction-phase7-20261009",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "delivery_status": "ready_for_rehearsal_with_unaccepted_limitations",
        "final_submission_status": "not_ready_as_qualified_outcome_prediction",
        "source": {
            "git": source_manifest["git"],
            "file_hash_manifest": relative_path(source_path),
            "file_hash_manifest_sha256": sha256_file(source_path),
            "tree_sha256": source_manifest["tree_sha256"],
        },
        "runtime": {
            "platform": platform.platform(),
            "python": sys.version,
            "backend_app_version": settings.app_version,
            "python_packages": package_versions(),
            "flutter": flutter_version,
            "requirements_sha256": sha256_file(ROOT / "requirements.txt"),
            "pubspec_lock_sha256": sha256_file(ROOT / "frontend_flutter/pubspec.lock"),
            "web_index_sha256": sha256_file(ROOT / "frontend_flutter/build/web/index.html"),
            "web_main_sha256": sha256_file(ROOT / "frontend_flutter/build/web/main.dart.js"),
        },
        "database_schema": {
            "dialect": db["database"]["dialect"],
            "database_name": db["database"]["database_name"],
            "database_url_recorded": False,
            "schema_contract": relative_path(schema_path),
            "schema_sha256": schema["schema_sha256"],
            "migration_strategy": schema["migration_strategy"],
        },
        "backup": backup,
        "restore_verification": restore,
        "models": {
            "classification": db["classification"],
            "outcome": db["outcome"],
        },
        "outcome_contract": {
            "target_version": (protocol.get("target") or {}).get("version"),
            "protocol_version": protocol.get("protocol_version"),
            "protocol_sha256": protocol.get("protocol_sha256"),
            "feature_version": feature.get("feature_policy_version"),
            "feature_schema_sha256": feature.get("feature_schema_sha256"),
            "calibration_version": CALIBRATION_VERSION,
            "frozen_real_dataset_manifest_sha256": None,
            "frozen_outcome_split_sha256": None,
            "observation_cutoff": readiness.get("cutoff"),
            "readiness_audit_sha256": readiness.get("audit_sha256"),
        },
        "data": {
            "active_target_rows": (readiness.get("dataset") or {}).get("active_target_rows"),
            "structurally_ready_rows": (readiness.get("dataset") or {}).get(
                "structurally_ready_without_rights_or_outcome_split"
            ),
            "training_allowed_rows": (readiness.get("dataset") or {}).get("training_allowed_rows"),
            "data_use_status": rights.get("status"),
            "real_training_allowed": (rights.get("decision") or {}).get("real_training_allowed") is True,
            "real_serving_allowed": (rights.get("decision") or {}).get("real_serving_allowed") is True,
            "retention": rights.get("retention"),
            "withdrawal_handling": (rights.get("retention") or {}).get("withdrawal"),
        },
        "qualification": {
            "qualified_scopes": [],
            "withheld_scopes": ["phone", "camera", "laptop", "unsupported_or_unknown"],
            "prediction_qualified": False,
            "activation_authorized": False,
            "phase6_decision": phase6_release.get("decision"),
            "phase6_bundle_sha256": phase6_integrity.get("bundle_sha256"),
            "acceptance": acceptance,
        },
        "runtime_health": runtime_health(backend_url, web_url),
        "urls": {
            "api": backend_url.rstrip("/"),
            "api_docs": backend_url.rstrip("/") + "/docs",
            "web": web_url.rstrip("/") + "/#/dashboard",
        },
        "environment": {
            "required_key_names": env_key_names(),
            "secret_values_included": False,
        },
        "demo": {
            "historical_saved_results": db["demo_examples"],
            "revision": db["revision"],
            "browser_evidence": {
                "path": relative_path(browser_evidence_path),
                "passed": True,
                "screenshots": len(browser.get("screenshots") or []),
                "fixture_route_hits": browser.get("fixtureRouteHits"),
                "fixture_is_model_evidence": False,
            },
        },
        "known_limitations": [
            "Classification model 43 is presentation_only, expired and blocked for accepted live predictions.",
            "No real Outcome model is registered or active.",
            "Data-use permission and retention basis remain unverified.",
            "No frozen real Outcome manifest or fresh independent Outcome Test exists.",
            "Human utility study has zero real reviewers and remains not evaluated.",
            "No claim is made that following a recommendation causes views to increase.",
            "The current health payload is degraded when a legacy TikTok provider attempt is in error; the delivery UI supports YouTube and Google only.",
            "Final 18 October rehearsal and 19 October release-day checks cannot be claimed on 9 October.",
        ],
        "privacy": {
            "shareable_package_contains_private_backup": False,
            "shareable_package_contains_database_rows": False,
            "shareable_package_contains_transcripts": False,
            "shareable_package_contains_user_videos": False,
            "shareable_package_contains_credentials": False,
        },
        "phase8_started": False,
    }
    manifest_path = output / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    (output / "release-manifest.sha256").write_text(
        f"{sha256_file(manifest_path)}  release-manifest.json\n", encoding="ascii"
    )
    package = copy_shareable_package(output, [manifest_path, source_path, schema_path])
    integrity_files = [source_path, schema_path, manifest_path, output / "release-manifest.sha256"]
    integrity = {
        "schema_version": "outcome-delivery-integrity-v1",
        "files": {path.name: sha256_file(path) for path in integrity_files},
        "shareable_package_sha256": package["package_sha256"],
    }
    integrity["bundle_sha256"] = canonical_sha256(integrity)
    (output / "integrity.json").write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"manifest": manifest, "integrity": integrity, "package": package}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--phase6-bundle", type=Path, required=True)
    parser.add_argument("--private-backup", type=Path, required=True)
    parser.add_argument("--restore-report", type=Path, required=True)
    parser.add_argument("--browser-evidence", type=Path, required=True)
    parser.add_argument("--flutter-version-json", type=Path, required=True)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--web-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    result = create_release(
        output=args.output_dir,
        phase6_bundle=args.phase6_bundle.resolve(),
        private_backup=args.private_backup.resolve(),
        restore_report_path=args.restore_report.resolve(),
        browser_evidence_path=args.browser_evidence.resolve(),
        flutter_version_path=args.flutter_version_json.resolve(),
        backend_url=args.backend_url,
        web_url=args.web_url,
    )
    print(json.dumps({
        "status": "complete",
        "output": str(args.output_dir.resolve()),
        "delivery_status": result["manifest"]["delivery_status"],
        "final_submission_status": result["manifest"]["final_submission_status"],
        "source_tree_sha256": result["manifest"]["source"]["tree_sha256"],
        "bundle_sha256": result["integrity"]["bundle_sha256"],
        "shareable_package_sha256": result["package"]["package_sha256"],
        "phase8_started": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
