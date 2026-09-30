"""Read-only source audit and frozen, human-labeled topic evaluation bundles."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.orm import Session, selectinload

from app.core.datetime_utils import utc_isoformat
from app.core.config import settings
from app.database.models import (
    TrendHistoryAttempt, TrendHistoryBucket, TrendSnapshotRun,
)
from app.services.trend_history import GAP_SECONDS, _samples_for_run
from app.services.youtube_cc_dataset import YouTubeCCDatasetError, extract_youtube_video_id

CONTRACT = "trend-topics-title-only-v1"
SPLITS = ("development", "test")
LABEL_COLUMNS = (
    "sample_id", "video_id", "title", "status", "topics", "evidence", "annotator", "notes",
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def title_fingerprint(title: str) -> str:
    return _hash(" ".join(unicodedata.normalize("NFKC", title).casefold().split()))


def _time(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("Missing observation time")
    if value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _video_id(url) -> str | None:
    try:
        return extract_youtube_video_id(url)
    except (ValueError, YouTubeCCDatasetError):
        return None


def _scope_key(platform, scope, run_id):
    return platform, scope, int(run_id)


def inspect_topic_sources(
    db: Session, *, region: str = "TH", days: int = 90, now: datetime | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    """No backfill, API calls, annotations, or database mutations occur here."""
    if not 1 <= days <= 90 or not re.fullmatch(r"[A-Z]{2}", region):
        raise ValueError("Use 1-90 days and an uppercase two-letter region")
    end = _time(now or datetime.utcnow())
    start = end - timedelta(days=days)
    issues = Counter()
    snapshots = {}
    identities = defaultdict(set)
    raw_quality = defaultdict(Counter)
    raw_scope_samples = Counter()
    archive_scope_samples = defaultdict(set)
    scope_statuses = {}
    raw_attempts = {}
    runs = db.query(TrendSnapshotRun).options(selectinload(TrendSnapshotRun.items)).filter(
        TrendSnapshotRun.region == region, TrendSnapshotRun.completed_at >= start,
        TrendSnapshotRun.completed_at <= end,
    ).order_by(TrendSnapshotRun.run_id).all()
    for run in runs:
        try:
            providers = json.loads(run.provider_status or "{}")
            for platform, provider in providers.items():
                if platform not in {"youtube", "google"}:
                    continue
                scopes = {"global": provider} if run.snapshot_kind == "global" else {
                    f"category:{category}": value for category, value in provider.get("categories", {}).items()}
                if not scopes and run.snapshot_kind == "youtube_categories" and platform == "youtube":
                    scopes = {f"category:{category}": provider for category in settings.youtube_trend_category_ids}
                for scope, result in scopes.items():
                    mode = result.get("mode", provider.get("mode"))
                    status = ("excluded_mock" if mode == "mock" else "observed"
                              if mode == "live" and result.get("status") in {"ok", "empty"}
                              and run.status in {"completed", "partial"} else "failed")
                    key = _scope_key(platform, scope, run.run_id)
                    scope_statuses[key] = status
                    raw_attempts[key] = SimpleNamespace(platform=platform, ranking_scope=scope,
                        run_id=run.run_id, observed_at=run.completed_at, status=status)
        except (ValueError, TypeError, AttributeError):
            issues["unreadable_raw_attempt_status"] += 1
        try:
            samples = _samples_for_run(run)
        except (ValueError, TypeError, AttributeError):
            issues["invalid_raw_provider_metadata"] += 1
            samples = []
        live_scopes = {(platform, scope) for platform, scope, _ in samples}
        for item in run.items:
            if (item.platform, item.ranking_scope) not in live_scopes:
                issues["excluded_non_live_or_failed_raw_rows"] += 1
                continue
            quality = raw_quality[(item.platform, item.ranking_scope)]
            quality["rows"] += 1
            for name in ("title", "category", "video_url", "channel_title", "description", "published_at"):
                quality[name] += bool(str(getattr(item, name) or "").strip())
            quality["rank"] += type(item.provider_rank) is int and 1 <= item.provider_rank <= 50
            quality["duration_seconds"] += (item.duration_seconds or 0) > 0
            for name in ("views", "likes", "comments"):
                quality[name] += getattr(item, f"{name}_available") is True
            video_id = _video_id(item.video_url) if item.platform == "youtube" else None
            quality["video_id"] += video_id is not None
            if video_id:
                identities[item.trend_key].add(video_id)
        for platform, scope, sample in samples:
            key = _scope_key(platform, scope, run.run_id)
            scope_statuses[key] = "observed"
            raw_scope_samples[(platform, scope)] += 1
            snapshots[key] = dict(sample, platform=platform, ranking_scope=scope,
                                  source="raw", region=region)

    archived_attempts = db.query(TrendHistoryAttempt).filter(
        TrendHistoryAttempt.region == region, TrendHistoryAttempt.observed_at >= start,
        TrendHistoryAttempt.observed_at <= end,
    ).order_by(TrendHistoryAttempt.observed_at).all()
    for attempt in archived_attempts:
        key = _scope_key(attempt.platform, attempt.ranking_scope, attempt.run_id)
        raw_attempts[key] = attempt
        scope_statuses[key] = attempt.status
    attempts = list(raw_attempts.values())

    buckets = db.query(TrendHistoryBucket).filter(
        TrendHistoryBucket.region == region,
        TrendHistoryBucket.bucket_at >= start.replace(minute=0, second=0, microsecond=0),
        TrendHistoryBucket.bucket_at <= end,
    ).order_by(TrendHistoryBucket.bucket_at).all()
    for bucket in buckets:
        for payload in (bucket.first_sample, bucket.last_sample):
            try:
                sample = json.loads(payload)
                at = _time(sample["observed_at"])
                if not start <= at <= end:
                    continue
                key = _scope_key(bucket.platform, bucket.ranking_scope, sample["run_id"])
                if not isinstance(sample["items"], list):
                    raise ValueError("Invalid items")
                if scope_statuses.get(key) in {"failed", "excluded_mock"}:
                    issues["excluded_failed_or_mock_archive_samples"] += 1
                    continue
                # Enrichment is limited to metadata from this exact source observation.
                raw_items = {item["key"]: item for item in snapshots.get(key, {}).get("items", [])}
                items = []
                for item in sample["items"]:
                    if not isinstance(item, dict):
                        raise ValueError("Invalid archived row")
                    item = dict(item)
                    raw = raw_items.get(item.get("key"), {})
                    if raw.get("title") == item.get("title"):
                        for field in ("video_url", "channel_title"):
                            if not item.get(field):
                                item[field] = raw.get(field)
                    items.append(item)
                    video_id = _video_id(item.get("video_url")) if bucket.platform == "youtube" else None
                    if video_id and item.get("key"):
                        identities[item["key"]].add(video_id)
                snapshots[key] = dict(sample, items=items, platform=bucket.platform,
                                      ranking_scope=bucket.ranking_scope, source="archive", region=region)
                archive_scope_samples[(bucket.platform, bucket.ranking_scope)].add(key)
            except (ValueError, KeyError, TypeError, AttributeError):
                issues["invalid_archive_samples"] += 1

    observations = []
    by_video = {}
    by_scope = defaultdict(list)
    for key, sample in sorted(snapshots.items()):
        if scope_statuses.get(key) in {"failed", "excluded_mock"}:
            continue
        platform, scope, run_id = key
        at = _time(sample["observed_at"])
        entries, seen_ids, seen_keys, seen_ranks = [], set(), set(), set()
        for source in sample["items"]:
            title = source.get("title")
            rank = source.get("rank")
            trend_key = source.get("key")
            identity_source = "source_url"
            video_id = _video_id(source.get("video_url")) if platform == "youtube" else None
            if not video_id and platform == "youtube":
                choices = identities.get(trend_key, set())
                if len(choices) == 1:
                    video_id = next(iter(choices))
                    identity_source = "unambiguous_retained_url_lookup"
                else:
                    identity_source = "unresolved"
                    issues["ambiguous_video_identity" if choices else "unresolved_video_identity"] += 1
            valid_title = isinstance(title, str) and bool(title.strip())
            valid_rank = type(rank) is int and 1 <= rank <= 50
            duplicate = bool((video_id and video_id in seen_ids) or (trend_key and trend_key in seen_keys))
            if video_id:
                seen_ids.add(video_id)
            if trend_key:
                seen_keys.add(trend_key)
            if valid_rank and rank in seen_ranks:
                issues["duplicate_rank_in_scope"] += 1
            if valid_rank:
                seen_ranks.add(rank)
            entry = dict(source, video_id=video_id, identity_source=identity_source,
                         title_valid=valid_title, rank_valid=valid_rank, duplicate=duplicate)
            entries.append(entry)
            if platform != "youtube" or not valid_title or not valid_rank or not video_id or duplicate:
                continue
            occurrence = {"run_id": run_id, "observed_at": utc_isoformat(at),
                          "ranking_scope": scope, "rank": rank, "source": sample["source"],
                          "trend_key": trend_key, "identity_source": identity_source}
            candidate = by_video.setdefault(video_id, {
                "video_id": video_id, "first_seen_at": utc_isoformat(at),
                "last_seen_at": utc_isoformat(at), "scopes": set(), "title_variants": set(),
                "observations": 0, "latest_at": datetime.min,
            })
            candidate["scopes"].add(scope)
            candidate["title_variants"].add(title_fingerprint(title))
            candidate["observations"] += 1
            candidate["first_seen_at"] = min(candidate["first_seen_at"], utc_isoformat(at), key=_time)
            candidate["last_seen_at"] = max(candidate["last_seen_at"], utc_isoformat(at), key=_time)
            if at > candidate["latest_at"]:
                candidate.update(title=title, category=str(source.get("category") or "Unknown"),
                                 channel_title=source.get("channel_title") or None,
                                 provenance=occurrence, latest_at=at)
        observation = dict(sample, items=entries, observed_at=utc_isoformat(at))
        observations.append(observation)
        by_scope[(platform, scope)].append(observation)

    scope_reports = []
    all_scopes = set(by_scope) | {(a.platform, a.ranking_scope) for a in attempts}
    for platform, scope in sorted(all_scopes):
        samples = sorted(by_scope[(platform, scope)], key=lambda x: _time(x["observed_at"]))
        scope_attempts = [a for a in attempts if a.platform == platform and a.ranking_scope == scope]
        rows = [item for sample in samples for item in sample["items"]]
        points = [_time(sample["observed_at"]) for sample in samples]
        observed_hours = {at.replace(minute=0, second=0, microsecond=0) for at in points}
        failed_hours = {a.observed_at.replace(minute=0, second=0, microsecond=0)
                        for a in scope_attempts if a.status == "failed"}
        intervals, hour = [], start.replace(minute=0, second=0, microsecond=0)
        while hour <= end:
            status = ("partial" if hour in observed_hours and hour in failed_hours else
                      "observed" if hour in observed_hours else
                      "failed" if hour in failed_hours else "no_observation")
            if intervals and intervals[-1]["status"] == status:
                intervals[-1]["through_hour"] = utc_isoformat(hour)
                intervals[-1]["hours"] += 1
            else:
                intervals.append({"from_hour": utc_isoformat(hour), "through_hour": utc_isoformat(hour),
                                  "hours": 1, "status": status})
            hour += timedelta(hours=1)
        scope_reports.append({
            "platform": platform, "ranking_scope": scope,
            "raw_samples": raw_scope_samples[(platform, scope)],
            "archived_samples": len(archive_scope_samples[(platform, scope)]),
            "available_samples": len(samples), "observed_hours": len(observed_hours),
            "first_at": samples[0]["observed_at"] if samples else None,
            "last_at": samples[-1]["observed_at"] if samples else None,
            "gap_count_over_90_minutes": sum((b-a).total_seconds() > GAP_SECONDS for a, b in zip(points, points[1:])),
            "failed_attempts": sum(a.status == "failed" for a in scope_attempts),
            "hours": intervals,
            "row_quality": {"total": len(rows), "with_title": sum(i["title_valid"] for i in rows),
                            "with_category": sum(bool(i.get("category")) for i in rows),
                            "valid_rank": sum(i["rank_valid"] for i in rows),
                            "verified_video_id": sum(bool(i["video_id"]) for i in rows),
                            "duplicate_rows": sum(i["duplicate"] for i in rows)},
            "raw_metadata_present": dict(raw_quality[(platform, scope)]),
            "sample_sizes": dict(sorted(Counter(len(s["items"]) for s in samples).items())),
        })
    candidates = []
    for candidate in by_video.values():
        candidate.pop("latest_at")
        candidate["scopes"] = sorted(candidate["scopes"])
        candidate["title_variants"] = sorted(candidate["title_variants"])
        candidate["video_url"] = f"https://www.youtube.com/watch?v={candidate['video_id']}"
        candidate["title_sha256"] = _hash(candidate["title"])
        candidate["title_fingerprint"] = title_fingerprint(candidate["title"])
        candidates.append(candidate)
    report = {
        "contract": CONTRACT, "region": region, "requested_from": utc_isoformat(start),
        "requested_to": utc_isoformat(end), "generated_at": utc_isoformat(end),
        "input_fields": ["title"], "supplementary_only": ["description", "hashtags", "channel", "statistics"],
        "sampling": "retained_raw_plus_first_last_hourly_archive_deduplicated_by_run_and_scope",
        "raw_runs": len(runs), "archive_buckets": len(buckets), "scopes": scope_reports,
        "candidate_videos": len(candidates), "candidate_categories": dict(Counter(c["category"] for c in candidates)),
        "unresolved_unique_trend_keys": len({item.get("key") for sample in observations
            if sample["platform"] == "youtube" for item in sample["items"] if not item["video_id"]}),
        "issues": dict(issues), "ground_truth_status": "not_annotated",
        "limitations": [
            "No observation is not zero and does not prove an API failure.",
            "Hours outside the collection window are not expected to be complete.",
            "Archived samples preserve first and last observations, not all intrahour changes.",
            "Legacy archive has no description, statistics, channel ID, or guaranteed source URL.",
            "Unresolved video identities are excluded from the evaluation pool, not guessed.",
            "Channel titles are not stable channel IDs; this is not a channel-held-out evaluation.",
            "Balanced category sampling is for evaluation coverage, not platform popularity.",
        ],
    }
    return report, sorted(candidates, key=lambda c: c["video_id"]), observations


def choose_evaluation_samples(candidates: list[dict], *, size: int = 200, test_size: int = 100,
                              seed: int = 20260925) -> tuple[dict[str, list[dict]], dict]:
    if not 2 <= size <= 1000 or not 0 < test_size < size:
        raise ValueError("Size must be 2-1000; test size must be between 1 and size-1")
    pools = defaultdict(list)
    for row in candidates:
        pools[row["category"]].append(row)
    counts, channels, title_hashes, video_ids = Counter(), Counter(), set(), set()
    selected = []
    for rows in pools.values():
        rows.sort(key=lambda row: _hash(f"{seed}|{row['video_id']}"))
    while pools and len(selected) < size:
        category = min(pools, key=lambda value: (counts[value], value))
        pools[category].sort(key=lambda row: (
            channels[row.get("channel_title") or "unknown"], _hash(f"{seed}|{row['video_id']}")))
        row = pools[category].pop(0)
        if not pools[category]:
            del pools[category]
        variants = set(row["title_variants"])
        if row["video_id"] in video_ids or variants & title_hashes:
            continue
        video_ids.add(row["video_id"])
        title_hashes.update(variants)
        selected.append(row)
        counts[category] += 1
        channels[row.get("channel_title") or "unknown"] += 1
    # Short pools stay short. Never repeat rows to reach the requested size.
    target_test = min(test_size, max(0, len(selected) - 1))
    if len(selected) < size:
        target_test = math.floor(len(selected) * test_size / size)
    allocations = {category: count * target_test // max(1, len(selected)) for category, count in counts.items()}
    remaining = target_test - sum(allocations.values())
    for category in sorted(counts, key=lambda c: (-(counts[c] * target_test % max(1, len(selected))), c))[:remaining]:
        allocations[category] += 1
    result = {split: [] for split in SPLITS}
    used = Counter()
    for row in sorted(selected, key=lambda row: (row["category"], _hash(f"split|{seed}|{row['video_id']}"))):
        category = row["category"]
        split = "test" if used[category] < allocations[category] else "development"
        used[category] += 1
        result[split].append(dict(row, sample_id=f"yt-{row['video_id']}", split=split,
                                  contract=CONTRACT, platform="youtube"))
    return result, {"requested": size, "selected": len(selected), "shortfall": size - len(selected),
                    "seed": seed, "strategy": "category_balanced_channel_title_diversity_seeded",
                    "counts": {split: dict(Counter(row["category"] for row in rows)) for split, rows in result.items()}}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def spreadsheet_text(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def write_preparation_bundle(path: Path, report: dict, candidates: list[dict], observations: list[dict],
                             *, size=200, test_size=100, seed=20260925) -> dict:
    splits, selection = choose_evaluation_samples(candidates, size=size, test_size=test_size, seed=seed)
    path.mkdir(parents=True, exist_ok=False)
    report = dict(report, selection=selection)
    (path / "audit.json").write_text(_json(report), encoding="utf-8", newline="\n")
    # Full title evidence is research material, not input for the development pipeline.
    with (path / "observations.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for observation in observations:
            handle.write(json.dumps(observation, ensure_ascii=False) + "\n")
    (path / "audit.md").write_text(render_audit(report), encoding="utf-8", newline="\n")
    manifest = {"contract": CONTRACT, "created_at": report["generated_at"], "input_fields": ["title"],
                "region": report["region"], "selection": selection, "files": {},
                "annotation_status": "pending_human_review", "holdout": "test must not be used for tuning"}
    for split, rows in splits.items():
        folder = path / split
        folder.mkdir()
        samples = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
        (folder / "samples.jsonl").write_text(samples, encoding="utf-8", newline="\n")
        manifest["files"][f"{split}/samples.jsonl"] = _hash(samples)
        with (folder / "labels.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LABEL_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({"sample_id": row["sample_id"], "video_id": row["video_id"],
                                 "title": spreadsheet_text(row["title"]), "status": "pending",
                                 "topics": "[]", "evidence": "[]", "annotator": "", "notes": ""})
    manifest["files"]["audit.json"] = _hash(_json(report))
    manifest["files"]["observations.jsonl"] = hashlib.sha256((path / "observations.jsonl").read_bytes()).hexdigest()
    heldout = _json({"contract": CONTRACT, "video_ids": sorted(row["video_id"] for row in splits["test"])})
    (path / "heldout_video_ids.json").write_text(heldout, encoding="utf-8", newline="\n")
    manifest["files"]["heldout_video_ids.json"] = _hash(heldout)
    (path / "manifest.json").write_text(_json(manifest), encoding="utf-8", newline="\n")
    (path / "ANNOTATION_GUIDE.md").write_text(ANNOTATION_GUIDE, encoding="utf-8", newline="\n")
    return manifest


def render_audit(report: dict) -> str:
    lines = ["# Trend Topic Data Readiness", "", f"Contract: `{CONTRACT}` (title only).",
             f"Region: {report['region']}. Window: {report['requested_from']} to {report['requested_to']} (UTC).",
             "", "No API calls, generated topics, or ground-truth labels were used.", "",
             "## Available Observations", "",
             "| Platform / scope | Raw | Archived | Unique samples | Hours | First UTC | Latest UTC | Failed attempts |",
             "|---|---:|---:|---:|---:|---|---|---:|"]
    for s in report["scopes"]:
        lines.append(f"| {s['platform']} / {s['ranking_scope']} | {s['raw_samples']} | {s['archived_samples']} | "
                     f"{s['available_samples']} | {s['observed_hours']} | {s['first_at']} | {s['last_at']} | {s['failed_attempts']} |")
    lines += ["", "## Title, Identity And Rank Completeness", "",
              "| Platform / scope | Rows | Title | Category | Valid rank | Verified video ID | Duplicate rows |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for s in report["scopes"]:
        q = s["row_quality"]
        lines.append(f"| {s['platform']} / {s['ranking_scope']} | {q['total']} | {q['with_title']} | {q['with_category']} | "
                     f"{q['valid_rank']} | {q['verified_video_id'] if s['platform'] == 'youtube' else 'N/A'} | {q['duplicate_rows']} |")
    lines += ["", "## Raw Metadata Completeness", "",
              "Counts below refer only to retained live raw rows. Missing is not zero.", "",
              "| Platform / scope | Rows | URL | Channel title | Description | Published | Duration | Views | Likes | Comments |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in report["scopes"]:
        q = s["raw_metadata_present"]
        fields = ("rows", "video_url", "channel_title", "description", "published_at", "duration_seconds", "views", "likes", "comments")
        lines.append(f"| {s['platform']} / {s['ranking_scope']} | " + " | ".join(str(q.get(f, 0)) for f in fields) + " |")
    lines += ["", "## Evaluation Set", "", f"Verified unique candidate videos: {report['candidate_videos']}.",
              "All topic labels are pending HUMAN annotation. No accuracy can be reported yet."]
    for split, categories in report["selection"]["counts"].items():
        lines.append(f"- {split}: {sum(categories.values())} videos; categories: {json.dumps(categories, ensure_ascii=False)}")
    lines += [f"- Shortfall: {report['selection']['shortfall']}.", "", "## Limitations", ""]
    lines += [f"- {note}" for note in report["limitations"]]
    lines += ["", "Hourly observed/partial/failed/no_observation intervals and source issues are in audit.json.",
              "Do not feed observations.jsonl or test/ into discovery, alias tuning, or development.", ""]
    return "\n".join(lines)


def validate_preparation_bundle(path: Path) -> dict:
    try:
        return _validate_bundle(path)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, csv.Error) as exc:
        return {"valid": False, "ready_for_evaluation": False, "status": "invalid",
                "counts": {}, "errors": [f"Cannot read bundle: {exc}"]}


def _validate_bundle(path: Path) -> dict:
    errors, counts, seen_ids, seen_titles = [], {}, set(), set()
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("contract") != CONTRACT or manifest.get("input_fields") != ["title"]:
        errors.append("Unsupported or changed title-only contract")
    expected = {"audit.json", "observations.jsonl", "heldout_video_ids.json",
                *(f"{split}/samples.jsonl" for split in SPLITS)}
    if set(manifest.get("files", {})) != expected:
        errors.append("Missing or unexpected immutable files in manifest")
    for name in sorted(expected):
        file = path / name
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != manifest.get("files", {}).get(name):
            errors.append(f"Immutable source changed or missing: {name}")
    for split in SPLITS:
        samples = [json.loads(line) for line in (path / split / "samples.jsonl").read_text(encoding="utf-8").splitlines() if line]
        expected_rows = {row["sample_id"]: row for row in samples}
        if len(expected_rows) != len(samples):
            errors.append(f"Duplicate sample IDs in {split}")
        if Counter(row["category"] for row in samples) != Counter(manifest["selection"]["counts"][split]):
            errors.append(f"Sample allocation differs from manifest in {split}")
        if split == "test":
            heldout = json.loads((path / "heldout_video_ids.json").read_text(encoding="utf-8"))
            if heldout.get("video_ids") != sorted(row["video_id"] for row in samples):
                errors.append("Held-out denylist differs from frozen test split")
        with (path / split / "labels.csv").open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(LABEL_COLUMNS):
                errors.append(f"Unexpected annotation columns in {split}")
            labels = list(reader)
        actual_ids = [row.get("sample_id") for row in labels]
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_rows):
            errors.append(f"Annotation rows missing, duplicated, or added in {split}")
        status_counts = Counter()
        for sample in samples:
            video_id = sample["video_id"]
            variants = set(sample["title_variants"])
            if video_id in seen_ids or variants & seen_titles:
                errors.append(f"Duplicate video or title across samples: {video_id}")
            seen_ids.add(video_id)
            seen_titles.update(variants)
            if (sample["split"] != split or sample["contract"] != CONTRACT or
                    _video_id(sample["video_url"]) != video_id or _hash(sample["title"]) != sample["title_sha256"]):
                errors.append(f"Invalid sample provenance: {video_id}")
        for row in labels:
            sample = expected_rows.get(row.get("sample_id"))
            if not sample:
                continue
            prefix = f"{split}/{row['sample_id']}"
            if row.get("video_id") != sample["video_id"] or row.get("title") != spreadsheet_text(sample["title"]):
                errors.append(f"{prefix}: immutable title or video ID edited")
            status = row.get("status", "")
            status_counts[status] += 1
            try:
                topics, evidence = json.loads(row["topics"]), json.loads(row["evidence"])
                if not isinstance(topics, list) or not isinstance(evidence, list):
                    raise ValueError()
                if any(not isinstance(x, str) or not x.strip() for x in topics + evidence):
                    raise ValueError()
                if len(set(topics)) != len(topics) or len(topics) != len(evidence):
                    raise ValueError()
                if any(text not in sample["title"] for text in evidence):
                    raise ValueError()
                if status == "labeled" and not topics:
                    raise ValueError()
                if status != "labeled" and (topics or evidence):
                    raise ValueError()
            except (ValueError, TypeError, KeyError):
                errors.append(f"{prefix}: invalid topics/evidence; quote exact title spans")
            if status not in {"pending", "labeled", "no_topic", "ambiguous"}:
                errors.append(f"{prefix}: invalid annotation status")
            if status != "pending" and not row.get("annotator", "").strip():
                errors.append(f"{prefix}: human annotator required")
            if status == "ambiguous" and not row.get("notes", "").strip():
                errors.append(f"{prefix}: ambiguity note required")
        counts[split] = dict(status_counts)
    complete = not errors and all(counts[s] and not counts[s].get("pending", 0) for s in SPLITS)
    return {"valid": not errors, "ready_for_evaluation": complete,
            "status": "invalid" if errors else "ready" if complete else "awaiting_human_annotation",
            "counts": counts, "errors": errors}


ANNOTATION_GUIDE = """# Human Annotation Guide

This is a title-only, multi-label topic evaluation set, NOT model predictions.
All rows intentionally start pending. No model accuracy is available yet.

1. Annotate development/labels.csv first. Keep test/ sealed until rules are fixed.
2. Read ONLY the supplied title. URLs are provenance, not permission to use the
   video, description, thumbnail, category or your outside knowledge as evidence.
3. Change status to labeled, no_topic, or ambiguous. Never force a topic.
4. topics is a JSON array of topic names; evidence is a JSON array of exact
   excerpts from the title in the same order. Example title: Review Galaxy S26.
   topics: ["Galaxy S26"], evidence: ["Galaxy S26"]. One title may have many topics.
5. Generic words such as review/video/today are not topic names. Distinguish an
   object/product/game/person/event from a broad YouTube category.
6. no_topic and ambiguous require empty arrays []; ambiguous also needs notes.
   Every completed row requires the human annotator name. Do not ask AI to invent
   ground truth. Topic extraction confidence is not an annotation.
7. Do not edit title, video_id, sample_id, samples.jsonl, manifest or split. The
   source hashes detect accidental edits, not malicious tampering. CSV is UTF-8
   with BOM; spreadsheet-formula-like titles have a protective apostrophe.
8. Agree on naming/aliases using development only. Freeze the rules and model
   version before opening test. Ideally have another person annotate/review test.
9. Validate with: python scripts/prepare_trend_topics.py validate --bundle PATH
   Add --require-complete for the final gate. Pending labels do not count as gold.
10. Keep test sample IDs out of discovery and alias development. observations.jsonl
    contains the full audit corpus, including test evidence: it is NOT a training
    file. Future discovery must exclude held-out IDs. This is video-held-out and
    duplicate-title-held-out, NOT channel-held-out or a future-time benchmark.

The balanced sample is for testing topic extraction, NOT measuring topic popularity.
Do not sum snapshots or category rankings as new videos. An unobserved interval
is not zero. Supplementary fields must never silently become title-only features.
"""
