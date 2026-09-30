"""Read-only Phase 7 runner. No training, activation, Dataset import or provider fetch."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASR_LOCAL_FILES_ONLY", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from app.services.analysis_evaluation import (
    LABELS, REVIEW_FIELDS, allocate_variant_orders, audit_recommendation,
    audit_study_manifest, build_presentation_variants, classification_metrics, digest,
    freeze_utility_protocol, human_review_summary, overlap_audit,
    pilot_classification_metrics, scoring_exclusions, structural_summary,
    utility_metrics, validate_utility_responses, verify_utility_protocol,
)
from app.services.recommendation_utility_study import (
    audit_actionable_evidence, build_blind_packets, evidence_correctness_summary, render_review_html,
    stable_context_lock, study_readiness, thai_report,
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def file_hash(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def new_output(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def seal_artifacts(directory):
    """Detect accidental mutations; this is an integrity manifest, not a signature."""
    directory = Path(directory)
    files = {path.relative_to(directory).as_posix(): file_hash(path)
             for path in sorted(directory.rglob("*")) if path.is_file()
             and path.name != "artifact-integrity.json" and "responses" not in path.relative_to(directory).parts}
    write(directory / "artifact-integrity.json", {"files": files, "sha256": digest(files)})


def verify_artifacts(directory):
    directory = Path(directory).resolve()
    seal = read(directory / "artifact-integrity.json")
    if seal.get("sha256") != digest(seal.get("files")) or not seal.get("files"):
        raise ValueError("Artifact integrity manifest is invalid")
    for name, expected in seal["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Frozen artifact changed: {name}")


def inventory(args):
    out = new_output(args.out)
    unique = {}
    for path in sorted(Path(args.videos).resolve().rglob("*")):
        if path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
            continue
        sha = file_hash(path)
        unique.setdefault(sha, []).append(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path))
    cases = []
    for number, (sha, paths) in enumerate(unique.items(), 1):
        path = min(paths, key=len)
        cases.append({"case_id": f"existing-{number:02}", "video_path": path,
                      "media_sha256": sha, "duplicates": paths, "role": "regression",
                      "source_kind": "unverified", "expected_label": None,
                      "label_reviewed_by": "", "source_youtube_id": "", "source_channel_id": "",
                      "independence_confirmed_by": "", "provenance_note": "Previously available local clip; not a new blind test."})
    for case in cases:
        case.update({"creator_group_key": "", "registered_at": "", "consent_status": "unconfirmed"})
        case["scenario_kind"] = ""
    write(out / "cases.json", {"schema_version": "recommendation-utility-manifest-v1", "cases": cases})
    write(out / "inventory.json", {"file_count": sum(map(len, unique.values())),
                                  "unique_media_count": len(cases), "missing": [
                                      "new_phone", "new_camera", "new_laptop", "self_recorded",
                                      "independently_labeled_out_of_scope"]})
    print(f"Inventory: {len(cases)} unique media files; labels and independent new clips still required.", flush=True)


def database_context(db, *, as_of=None):
    from app.database.models import ReferenceVideoStatistic, SystemConfig
    from app.services.analysis_settings import capture_analysis_settings
    from app.services.classification import get_active_classification_model
    from app.services.classification_training import load_classification_artifact
    from app.services.dataset_eligibility import reference_transcript_rows
    from app.core.datetime_utils import utc_isoformat
    cutoff = as_of or datetime.now(timezone.utc).replace(tzinfo=None)
    if cutoff.tzinfo is not None:
        cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
    config = db.query(SystemConfig).filter(SystemConfig.user_id.is_(None)).first()
    if config is None:
        raise ValueError("Configure analysis settings first; evaluation never creates production config")
    model = get_active_classification_model(db)
    if model is None:
        raise ValueError("No active model; evaluation will not activate or train one")
    artifact = load_classification_artifact(model.artifact_path)
    manifest_path = Path(artifact["dataset_manifest_path"])
    if artifact.get("dataset_manifest_sha256") and file_hash(manifest_path) != artifact["dataset_manifest_sha256"]:
        raise ValueError("Model dataset manifest hash mismatch")
    manifest = read(manifest_path)
    splits = {}
    for name, spec in manifest["artifacts"]["splits"].items():
        path = Path(spec["path"])
        if file_hash(path) != spec["sha256"]:
            raise ValueError(f"Frozen {name} split hash mismatch")
        splits[name] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    reference_rows = []
    for row in sorted(reference_transcript_rows(db, now=cutoff), key=lambda r: r.dataset_id):
        data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        data = {key: utc_isoformat(value) if isinstance(value, datetime) else value for key, value in data.items()}
        reference_rows.append(data)
    pool = [{**r, "evaluation_pool": name} for name in ("train", "validation") for r in splits.get(name, [])]
    pool.extend({**r, "evaluation_pool": "reference"} for r in reference_rows)
    packages = {}
    for name in ("scikit-learn", "pythainlp", "faster-whisper", "ctranslate2"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "not_installed"
    from app.services.actionable_recommendations import (
        METHOD_VERSION as ACTION_METHOD_VERSION, template_catalog,
    )
    from app.services.recommendation_evidence import (
        METHOD_VERSION as EVIDENCE_METHOD_VERSION, SCHEMA_VERSION as EVIDENCE_SCHEMA_VERSION,
    )
    from app.services.topic_comparisons import (
        METHOD_VERSION as COMPARISON_METHOD_VERSION,
        SCHEMA_VERSION as COMPARISON_SCHEMA_VERSION,
        comparison_policy,
    )
    from app.services.taxonomy import ready_leaf_keys
    policy = comparison_policy()
    history_hours = policy["latest_observation_hours"] + policy["growth_max_hours"]
    observations = db.query(ReferenceVideoStatistic).filter(
        ReferenceVideoStatistic.dataset_id.in_([row["dataset_id"] for row in reference_rows]),
        ReferenceVideoStatistic.observed_at >= cutoff - timedelta(hours=history_hours),
        ReferenceVideoStatistic.observed_at <= cutoff,
    ).order_by(ReferenceVideoStatistic.observation_id).all()
    frozen_statistics = [{column.name: getattr(row, column.name) for column in row.__table__.columns}
                         for row in observations]
    templates = template_catalog()
    context = {"at": datetime.now(timezone.utc).isoformat(), "settings": capture_analysis_settings(db),
               "python_version": sys.version, "packages": packages,
               "asr_language": os.getenv("ASR_LANGUAGE", "auto"),
               "artifact_path": model.artifact_path, "artifact_sha256": file_hash(model.artifact_path),
               "dataset_manifest_sha256": file_hash(manifest_path),
               "reference_sha256": digest(reference_rows), "reference_count": len(reference_rows),
               "statistics_cutoff": utc_isoformat(cutoff),
               "statistics_sha256": digest(frozen_statistics),
               "recommendation_parameters": {"max_keywords_display": config.max_keywords,
                                               "ready_categories": sorted(ready_leaf_keys(db))},
               "method_versions": {"actionable_recommendations": ACTION_METHOD_VERSION,
                                   "actionable_template_version": templates.get("version"),
                                   "actionable_template_sha256": digest(templates),
                                   "recommendation_evidence": EVIDENCE_METHOD_VERSION,
                                   "recommendation_evidence_schema": EVIDENCE_SCHEMA_VERSION,
                                   "topic_comparisons": COMPARISON_METHOD_VERSION,
                                   "topic_comparison_schema": COMPARISON_SCHEMA_VERSION,
                                   "topic_comparison_policy": comparison_policy()},
               "code_sha256": {str(path.relative_to(ROOT)): file_hash(path) for path in [
                   ROOT / "app/services/recommendation.py", ROOT / "app/routes/analyze.py",
                   ROOT / "app/services/nlp.py", ROOT / "app/services/pipeline/core.py",
                   ROOT / "app/services/pipeline/domain_rules.py", ROOT / "models/speech_to_text.py",
                   ROOT / "app/services/analysis_evaluation.py",
                   ROOT / "app/services/recommendation_utility_study.py",
                   ROOT / "app/services/utility_review.html",
                   ROOT / "app/services/actionable_recommendations.py",
                   ROOT / "app/services/recommendation_evidence.py",
                   ROOT / "app/services/dataset_eligibility.py",
                   ROOT / "app/services/taxonomy.py",
                   ROOT / "app/services/topic_comparisons.py",
                   ROOT / "app/services/classification_acceptance.py",
                   ROOT / "app/services/analysis_settings.py",
                   ROOT / "scripts/evaluate_analysis.py"]}}
    return context, splits, reference_rows, pool


def prior_evaluation_records(pool, *, exclude_paths=()):
    records = [{**row, "registry_source": f"{row.get('evaluation_pool', 'dataset')}:{row.get('dataset_id', '')}"}
               for row in pool]
    excluded = {Path(path).resolve() for path in exclude_paths}
    for path in (ROOT / "artifacts" / "evaluation").glob("**/cases.json"):
        if path.resolve() in excluded:
            continue
        try:
            value = read(path)
        except (OSError, json.JSONDecodeError):
            continue
        rows = value.get("cases", []) if isinstance(value, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            spec = row.get("spec", row) if isinstance(row, dict) else {}
            result = row.get("result") or {}
            records.append({**spec, "transcript": result.get("cleaned_transcript") or result.get("transcript") or spec.get("transcript"),
                            "registry_source": str(path.relative_to(ROOT))})
    return records


def protocol_markdown(protocol, audit, readiness):
    lines = ["# Phase 7 Recommendation Utility Protocol", "",
             f"- Study: `{protocol['study_id']}`",
             f"- Protocol version: `{protocol['schema_version']}`",
             f"- SHA-256: `{protocol['protocol_sha256']}`",
             f"- Created before prediction: `{protocol['created_at']}`",
             f"- Random seed: `{protocol['seed']}`",
             f"- Registered heldout cases: `{audit['eligible_case_count']}`",
             f"- Planned real reviewers: `{len(protocol['reviewer_ids'])}`",
             f"- Readiness: `{readiness['state']}`", "",
             "## การเปรียบเทียบ", "",
             "- A: ชื่อหัวข้อเท่านั้น",
             "- B: หัวข้อเดียวกันพร้อมวิธีทำ",
             "- C: เนื้อหา B เดิมพร้อมหลักฐานและข้อจำกัด", "",
             "## เกณฑ์สำคัญ", "",
             "- ประเมิน Classification, Evidence correctness และ Utility แยกกัน",
             "- คะแนนที่ขาดไม่แทนด้วยศูนย์; งานล้มเหลวไม่ถือเป็น Unknown rejection",
             "- ต้องมีคลิปครบอย่างน้อยหมวดละ 3 และผู้ประเมินจริง 3 คน",
             "- ไม่อ้างว่าคำแนะนำทำให้ Engagement เพิ่มขึ้น", ""]
    return "\n".join(lines)


def prepare_study(args):
    from app.database.db import SessionLocal
    manifest = read(args.manifest)
    reviewers = [item.strip() for item in args.reviewers.split(",") if item.strip()]
    db = SessionLocal()
    try:
        context, splits, references, pool = database_context(db)
        prior_pool = [*pool, *({**row, "evaluation_pool": "historical_test"}
                               for row in splits.get("test", []))]
        for case in manifest.get("cases", []):
            path = (ROOT / case.get("video_path", "")).resolve()
            if not path.is_file():
                raise ValueError(f"Video does not exist: {case.get('case_id')}")
            if file_hash(path) != case.get("media_sha256"):
                raise ValueError(f"Media hash mismatch before registration: {case.get('case_id')}")
        audit = audit_study_manifest(
            manifest,
            prior_records=prior_evaluation_records(prior_pool, exclude_paths=[args.manifest]),
        )
        if any("invalid_or_duplicate_case_id" in row["exclusions"] for row in audit["cases"]):
            raise ValueError("Each registered case must have a unique safe ID")
        protocol = freeze_utility_protocol(
            study_id=args.study_id, manifest_sha256=audit["manifest_sha256"],
            context_lock=stable_context_lock(context), reviewer_ids=reviewers, seed=args.seed,
        )
        readiness = study_readiness(manifest_audit=audit, reviewer_ids=reviewers)
        eligible_ids = [row["case_id"] for row in audit["cases"] if row["fresh_heldout_eligible"]]
        allocations = allocate_variant_orders(
            study_id=protocol["study_id"], protocol_sha256=protocol["protocol_sha256"],
            case_ids=eligible_ids, reviewer_ids=reviewers, seed=protocol["seed"],
        )
        out = new_output(args.out)
        write(out / "manifest.json", manifest)
        write(out / "manifest-audit.json", audit)
        write(out / "context.json", context)
        write(out / "reference-rows.json", references)
        write(out / "protocol.json", protocol)
        write(out / "allocation-plan.private.json", allocations)
        write(out / "readiness.json", readiness)
        (out / "protocol.md").write_text(protocol_markdown(protocol, audit, readiness), encoding="utf-8")
        seal_artifacts(out)
        print(json.dumps({"prepared": str(out), "readiness": readiness}, ensure_ascii=False, indent=2))
    finally:
        db.rollback()
        db.close()


def run_study(args):
    from app.database.db import SessionLocal
    from app.routes.analyze import _build_recommendation
    from app.services.ai_pipeline import analyze_video
    from app.services.media_validation import validate_user_upload_duration
    prepared = Path(args.prepared).resolve()
    verify_artifacts(prepared)
    manifest = read(prepared / "manifest.json")
    audit = read(prepared / "manifest-audit.json")
    protocol = read(prepared / "protocol.json")
    readiness = read(prepared / "readiness.json")
    allocations = read(prepared / "allocation-plan.private.json")
    if not verify_utility_protocol(protocol) or protocol["manifest_sha256"] != digest(manifest):
        raise ValueError("Frozen protocol or manifest hash is invalid")
    if readiness["state"] != "ready_for_prediction":
        raise ValueError("Study is not ready: fresh heldout clips and three real reviewers are required")
    if [row["spec"] for row in audit["cases"]] != manifest["cases"]:
        raise ValueError("Manifest audit does not match registered cases")
    # Reserve the directory before any expensive work and persist each completed case.
    out = new_output(args.out)
    write(out / "run-status.json", {"status": "running"})
    cutoff = datetime.fromisoformat(protocol["context_lock"]["statistics_cutoff"].replace("Z", "+00:00"))
    db = SessionLocal()
    try:
        context, splits, references, pool = database_context(db, as_of=cutoff)
        overlap_pool = prior_evaluation_records([*pool, *({**row, "evaluation_pool": "historical_test"}
                                 for row in splits.get("test", []))])
        if digest(stable_context_lock(context)) != digest(protocol["context_lock"]):
            raise ValueError("Frozen evaluation context changed; create a new protocol version")
        case_outputs = {}
        for audited in audit["cases"]:
            spec = audited["spec"]
            case_id = spec["case_id"]
            video = (ROOT / spec["video_path"]).resolve()
            entry = {"case_id": case_id, "spec": spec, "role": spec["role"],
                     "expected_label": spec["expected_label"], "video_uri": video.as_uri(),
                     "manifest_eligible": audited["fresh_heldout_eligible"],
                     "analysis_status": "failed", "exclusions": ["analysis_not_completed"]}
            if not audited["fresh_heldout_eligible"] and spec.get("role") != "regression":
                entry.update(analysis_status="excluded", exclusions=audited["exclusions"], variants={})
                case_outputs[case_id] = entry
                continue
            error_stage = "media_integrity"
            try:
                if file_hash(video) != spec["media_sha256"]:
                    raise ValueError("Media changed after protocol freeze")
                error_stage = "media_duration"
                duration = validate_user_upload_duration(
                    video, max_duration_seconds=context["settings"]["upload_max_duration_seconds"])
                error_stage = "speech_to_text"
                result = analyze_video(str(video), display_name="evaluation.mp4",
                                       hook_duration_seconds=context["settings"]["hook_duration_seconds"],
                                       asr_model_size=context["settings"]["asr_model"])
                result["analysis_settings"] = context["settings"]
                error_stage = "recommendation"
                recommendation, _ = _build_recommendation(
                    db, filename="evaluation.mp4", result=result,
                    settings_snapshot=context["settings"], evidence_as_of=cutoff.replace(tzinfo=None))
                result["recommendation"] = recommendation
                error_stage = "evidence_audit"
                transcript = result.get("cleaned_transcript") or ""
                overlaps = overlap_audit(spec, transcript, overlap_pool)
                speech_ok = result.get("analysis", {}).get("stt_meta", {}).get("transcript_source") == "speech_to_text"
                exclusions = scoring_exclusions(spec, overlaps, speech_ok=speech_ok)
                entry.update({"analysis_status": "completed", "duration_seconds": duration,
                              "predicted_label": recommendation.get("domain"),
                              "classification_confidence": recommendation.get("classification", {}).get("confidence"),
                              "transcript_sha256": digest(transcript), "overlaps": overlaps,
                              "exclusions": exclusions, "result_sha256": digest(result),
                              "variants": build_presentation_variants(result),
                              "recommendation_checks": audit_recommendation(result, references),
                              "actionable_evidence_checks": audit_actionable_evidence(result),
                              "result": result})
            except Exception as exc:
                entry["error"] = type(exc).__name__
                entry["error_stage"] = error_stage
                entry["variants"] = {}
            case_outputs[case_id] = entry
            write(out / "cases.json", {"cases": list(case_outputs.values())})
        db.rollback()
        final_context, _, _, _ = database_context(db, as_of=cutoff)
        if digest(stable_context_lock(final_context)) != digest(protocol["context_lock"]):
            raise ValueError("Evaluation inputs changed during prediction; this run cannot be rated")
        packets, private = build_blind_packets(
            protocol=protocol, allocations=allocations, case_outputs=case_outputs)
        write(out / "protocol.json", protocol)
        write(out / "manifest.json", manifest)
        write(out / "manifest-audit.json", audit)
        write(out / "readiness.json", readiness)
        write(out / "context.json", context)
        write(out / "cases.json", {"cases": list(case_outputs.values())})
        write(out / "variants.json", {case_id: row.get("variants", {})
                                      for case_id, row in case_outputs.items()})
        write(out / "analysis-audit.json", {case_id: {
            "analysis_status": row.get("analysis_status"),
            "exclusions": row.get("exclusions", []),
            "overlaps": row.get("overlaps", []),
            "error": row.get("error"),
        } for case_id, row in case_outputs.items()})
        write(out / "classification.json", pilot_classification_metrics(list(case_outputs.values())))
        write(out / "evidence-correctness.json", evidence_correctness_summary(case_outputs))
        private_dir = out / "private"
        private_dir.mkdir()
        write(private_dir / "allocation-key.json", private)
        packet_dir = out / "review-packets"
        packet_dir.mkdir()
        for reviewer, packet in packets.items():
            write(packet_dir / f"{reviewer}.json", packet)
            (packet_dir / f"{reviewer}.html").write_text(render_review_html(packet), encoding="utf-8")
        responses_dir = out / "responses"
        responses_dir.mkdir()
        (responses_dir / "README.md").write_text(
            "# Human responses\n\nPlace only JSON files downloaded from the blinded review packets here. "
            "Do not create ratings from fixtures or copy another reviewer's identity.\n", encoding="utf-8")
        write(out / "run-status.json", {"status": "ready_for_review"})
        seal_artifacts(out)
        print(json.dumps({"run": str(out), "cases": len(case_outputs),
                          "review_packets": len(packets)}, ensure_ascii=False, indent=2))
    except Exception as exc:
        write(out / "run-status.json", {"status": "failed", "error_type": type(exc).__name__})
        raise
    finally:
        db.rollback()
        db.close()


def report_study(args):
    run_dir = Path(args.run).resolve()
    verify_artifacts(run_dir)
    protocol = read(run_dir / "protocol.json")
    if not verify_utility_protocol(protocol):
        raise ValueError("Protocol hash mismatch")
    readiness = read(run_dir / "readiness.json")
    cases_doc = read(run_dir / "cases.json")
    case_outputs = {row["case_id"]: row for row in cases_doc["cases"]}
    private = read(run_dir / "private" / "allocation-key.json")
    response_documents = []
    if args.responses:
        response_path = Path(args.responses).resolve()
        paths = sorted(response_path.glob("*.json")) if response_path.is_dir() else [response_path]
        response_documents = [read(path) for path in paths]
    validated = validate_utility_responses(
        response_documents=response_documents, allocations=private["allocations"],
        protocol=protocol, case_outputs=case_outputs)
    adjudications = read(args.adjudications).get("adjudications", []) if args.adjudications else []
    classification = pilot_classification_metrics(list(case_outputs.values()))
    evidence = evidence_correctness_summary(case_outputs)
    utility = utility_metrics(validated=validated, case_outputs=case_outputs,
                              adjudications=adjudications)
    primary_cases = [row for row in case_outputs.values()
                     if row.get("role") == "heldout" and row.get("manifest_eligible")]
    all_completed = bool(primary_cases) and all(
        row.get("analysis_status") == "completed" for row in primary_cases)
    evaluation_complete = bool(
        readiness.get("state") == "ready_for_prediction" and all_completed and
        classification.get("status") in {"pass", "fail"} and
        utility.get("status") in {"pass", "fail"} and
        validated.get("accepted_reviewer_count", 0) >= 3 and not validated.get("rejected") and
        len(validated.get("ratings", [])) == len(private["allocations"]) and
        len(private["allocations"]) == len(primary_cases) * len(protocol["reviewer_ids"]) * 3
    )
    status = "evaluation_complete" if evaluation_complete else "tooling_ready"
    report = {"schema_version": "recommendation-utility-report-v1",
              "study_id": protocol["study_id"],
              "protocol_sha256": protocol["protocol_sha256"], "status": status,
              "evaluation_complete": evaluation_complete,
              "classification": classification, "evidence_correctness": evidence,
              "recommendation_utility": utility, "response_validation": validated,
              "readiness": readiness,
              "claims": {"causal_engagement_gain": "not_measured"}}
    out = new_output(args.out)
    write(out / "classification-report.json", classification)
    write(out / "evidence-correctness-report.json", evidence)
    write(out / "utility-report.json", utility)
    write(out / "response-validation.json", validated)
    write(out / "report.json", report)
    (out / "presentation-summary-th.md").write_text(
        thai_report(status=status, classification=classification, evidence=evidence,
                    utility=utility, readiness=readiness, validated=validated), encoding="utf-8")
    print(json.dumps({"report": str(out), "status": status,
                      "utility": utility.get("status")}, ensure_ascii=False, indent=2))


def review_template(cases):
    return [{"case_id": case["case_id"], "output_sha256": case["output_sha256"],
             "lane": check["lane"], "index": str(check["index"]), "keyword": check["keyword"],
             "reviewer": "", **{field: "" for field in REVIEW_FIELDS}, "notes": ""}
            for case in cases for check in case.get("recommendation_checks", [])]


def export_review(out, rows):
    with (out / "human-review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case_id", "output_sha256", "lane", "index", "keyword", "reviewer", *REVIEW_FIELDS, "notes"])
        writer.writeheader()
        writer.writerows(rows)


def markdown_report(out, report):
    historical = report["historical_test"]["metrics"]
    coverage = report["coverage"]
    lines = ["# Phase 7 evaluation evidence", "", "## Status", "",
             "Independent end-to-end evaluation is INCOMPLETE until new labeled clips and human recommendation reviews are available.",
             "No model training, activation, Dataset import or production analysis save was performed.", "",
             f"New independent scored clips: {coverage['scored_new_clips']}",
             f"Missing new-clip classes: {', '.join(coverage['new_clip_labels_missing']) or 'none'}",
             f"Scored self-recorded clips: {coverage['self_recorded_scored']}", "",
             "## Historical classifier regression", "",
             "Previously evaluated frozen transcripts, NOT unseen videos and NOT an ASR test.",
             f"Samples: {historical['sample_size']}; accuracy: {historical['accuracy']}; macro F1: {historical['macro_f1']}",
             f"Unknown recall: {historical['unknown_recall']} (null means not evaluated)", "",
             "## Real local video runs", "",
             "These clips are regression cases unless independent provenance and gold labels are confirmed.", "",
             "| Case | Seconds | Predicted class | Confidence (not accuracy) | Suggestions / flagged | Result |",
             "| --- | ---: | --- | ---: | --- | --- |"]
    for case in report["cases"]:
        result = case.get("result", {})
        classification = result.get("recommendation", {}).get("classification", {})
        checks = case.get("recommendation_checks", [])
        lines.append(f"| {case['case_id']} | {case.get('duration_seconds', 0):.1f} | {case.get('predicted_label', 'error')} | "
                     f"{classification.get('confidence', 0):.4f} | {len(checks)} / {sum(bool(c['structural_issues']) for c in checks)} | "
                     f"[{case['case_id']}.json]({case['case_id']}.json) |")
    lines.extend(["", "## Recommendation evaluation", "",
                  "Automated checks validate repetition and Dataset evidence consistency. They reuse production term normalization and do not independently prove semantic relevance, transcript correctness or usefulness.",
                  "Human ratings are pending in human-review.csv. Suggested changes cannot be claimed to increase engagement without a separate outcome study.", "",
                  "```json", json.dumps(report["recommendation_structure"], indent=2), "```"])
    if "paired_reference_comparison" in report:
        lines.extend(["", "## Before / after reference recommendations", "",
                      "Same ASR, model, settings and reference fingerprint. Current trend ideas are excluded from the paired claim.",
                      "```json", json.dumps(report["paired_reference_comparison"], indent=2), "```"])
    lines.extend(["", "## Traceability", "", "- context.json: settings, model artifact hash, code hashes and reference fingerprint.",
                  "- reference-rows.json: local evidence snapshot, not new training data.",
                  "- report.json: every prediction, exclusion and structural check.",
                  "- human-review.csv: blank reviewer/rating fields until a person reviews the actual clip.", ""])
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run(args):
    from app.database.db import SessionLocal
    from app.routes.analyze import _build_recommendation
    from app.services.ai_pipeline import analyze_video
    from app.services.media_validation import validate_user_upload_duration
    from app.services.classification import classify_text_domain
    out = new_output(args.out)
    baseline = read(args.replay) if args.replay else None
    manifest = read(args.manifest) if args.manifest else None
    specs = [case["spec"] for case in baseline["cases"]] if baseline else manifest["cases"]
    ids = [case["case_id"] for case in specs]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-zA-Z0-9_-]+", case_id) for case_id in ids):
        raise ValueError("Case IDs must be unique safe filenames")
    db = SessionLocal()
    try:
        context, splits, references, pool = database_context(db)
        if baseline:
            for key in ("reference_sha256", "dataset_manifest_sha256"):
                if context[key] != baseline["context"][key]:
                    raise ValueError(f"Paired replay requires unchanged {key}; make a new baseline")
            for key in ("classification_model", "asr_model", "hook_duration_seconds", "upload_max_duration_seconds"):
                if context["settings"][key] != baseline["context"]["settings"][key]:
                    raise ValueError(f"Paired replay settings changed: {key}")
        write(out / "context.json", context)
        write(out / "reference-rows.json", references)
        historical = []
        for row in splits["test"]:
            overlap = overlap_audit(row, row["transcript"], pool)
            prediction = classify_text_domain(db, text=row["transcript"], require_active_model=True,
                                             model_snapshot=context["settings"]["classification_model"])
            historical.append({"dataset_id": row["dataset_id"], "expected_label": row["taxonomy_leaf_key"],
                               "predicted_label": prediction["taxonomy_leaf_key"], "confidence": prediction["confidence"],
                               "overlaps": overlap, "exclusions": ["training_or_reference_overlap"] if overlap else []})
        report = {"protocol_version": 1, "context": context,
                  "historical_test": {"label": "previously evaluated frozen transcript test; not new videos and not ASR evaluation",
                                      "metrics": classification_metrics(historical), "rows": historical},
                  "cases": [], "claims": {"engagement_improvement": "not_measured", "independent_recommendation_quality": "human_review_pending"}}
        seen_media = set()
        for spec in specs:
            entry = {"case_id": spec["case_id"], "spec": spec, "expected_label": spec.get("expected_label"),
                     "exclusions": ["analysis_not_completed"]}
            try:
                video = (ROOT / spec["video_path"]).resolve()
                media_hash = file_hash(video)
                if media_hash != spec["media_sha256"]:
                    raise ValueError("Media changed after test inventory")
                duration = validate_user_upload_duration(video, max_duration_seconds=context["settings"]["upload_max_duration_seconds"])
                print(f"Evaluating {spec['case_id']} ({duration:.1f}s)", flush=True)
                if baseline:
                    original = next(r for r in baseline["cases"] if r["case_id"] == spec["case_id"])
                    result = copy.deepcopy(original["result"])
                    result.pop("recommendation", None)
                else:
                    result = analyze_video(str(video), display_name="evaluation.mp4",
                                           hook_duration_seconds=context["settings"]["hook_duration_seconds"],
                                           asr_model_size=context["settings"]["asr_model"])
                result["analysis_settings"] = context["settings"]
                recommendation, _ = _build_recommendation(db, filename="evaluation.mp4", result=result,
                                                         settings_snapshot=context["settings"])
                result["recommendation"] = recommendation
                transcript = result.get("cleaned_transcript") or ""
                overlaps = overlap_audit(spec, transcript, pool)
                speech_ok = result.get("analysis", {}).get("stt_meta", {}).get("transcript_source") == "speech_to_text"
                entry.update(result=result, duration_seconds=duration, output_sha256=digest(result),
                             transcript_sha256=digest(transcript), overlaps=overlaps,
                             predicted_label=recommendation["domain"],
                             exclusions=scoring_exclusions(spec, overlaps, duplicate=media_hash in seen_media, speech_ok=speech_ok),
                             recommendation_checks=audit_recommendation(result, references))
                seen_media.add(media_hash)
            except Exception as exc:
                entry["error"] = str(exc)
            report["cases"].append(entry)
            write(out / f"{spec['case_id']}.json", entry)
            write(out / "report.json", report)
        report["new_clip_classification"] = classification_metrics(report["cases"])
        report["recommendation_structure"] = structural_summary(report["cases"])
        report["coverage"] = {"scored_new_clips": report["new_clip_classification"]["sample_size"],
                              "failed_case_count": sum(bool(r.get("error")) for r in report["cases"]),
                              "new_clip_labels_missing": [label for label in LABELS if not any(
                                  r.get("expected_label") == label and not r["exclusions"] for r in report["cases"])],
                              "self_recorded_scored": sum(r["spec"].get("source_kind") == "self_recorded" and not r["exclusions"] for r in report["cases"])}
        if baseline:
            report["paired_reference_comparison"] = {"baseline_sha256": file_hash(args.replay),
                "same_asr_transcripts": all(r.get("transcript_sha256") and r.get("transcript_sha256") == old.get("transcript_sha256")
                    for r, old in zip(report["cases"], baseline["cases"])),
                "before": baseline["recommendation_structure"], "after": report["recommendation_structure"],
                "trend_ideas_comparison": "excluded: collection time may differ"}
        write(out / "report.json", report)
        export_review(out, review_template(report["cases"]))
        markdown_report(out, report)
        print(json.dumps({"report": str(out / "report.json"), "coverage": report["coverage"],
                          "historical_test": report["historical_test"]["metrics"],
                          "structure": report["recommendation_structure"]}, ensure_ascii=True, indent=2), flush=True)
    finally:
        db.rollback()
        db.close()


def reviews(args):
    report = read(args.report)
    with Path(args.reviews).open(encoding="utf-8-sig", newline="") as handle:
        summary = human_review_summary(list(csv.DictReader(handle)), review_template(report["cases"]))
    print(json.dumps(summary, indent=2))


def summarize(args):
    path = Path(args.report).resolve()
    markdown_report(path.parent, read(path))
    print(str(path.parent / "report.md"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("inventory")
    prepare.add_argument("--videos", default="videos")
    prepare.add_argument("--out", required=True)
    evaluate = sub.add_parser("run")
    inputs = evaluate.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--manifest")
    inputs.add_argument("--replay", help="Previous report; reuse identical ASR for paired recommendation comparison")
    evaluate.add_argument("--out", required=True)
    review = sub.add_parser("reviews")
    review.add_argument("--report", required=True)
    review.add_argument("--reviews", required=True)
    summary = sub.add_parser("summarize")
    summary.add_argument("--report", required=True)
    study_prepare = sub.add_parser("prepare-study", help="Freeze a new Phase 7 manifest and protocol before prediction")
    study_prepare.add_argument("--manifest", required=True)
    study_prepare.add_argument("--study-id", required=True)
    study_prepare.add_argument("--reviewers", required=True, help="Comma-separated anonymous IDs for real reviewers")
    study_prepare.add_argument("--seed", type=int, default=260930)
    study_prepare.add_argument("--out", required=True)
    study_run = sub.add_parser("run-study", help="Run the frozen read-only study and create blind packets")
    study_run.add_argument("--prepared", required=True)
    study_run.add_argument("--out", required=True)
    study_report = sub.add_parser("report-study", help="Validate real responses and write separated reports")
    study_report.add_argument("--run", required=True)
    study_report.add_argument("--responses", help="Response JSON file or directory; omit to report not_evaluated")
    study_report.add_argument("--adjudications", help="Optional JSON decisions for reported critical flags")
    study_report.add_argument("--out", required=True)
    args = parser.parse_args()
    {"inventory": inventory, "run": run, "reviews": reviews, "summarize": summarize,
     "prepare-study": prepare_study, "run-study": run_study,
     "report-study": report_study}[args.command](args)


if __name__ == "__main__":
    main()
