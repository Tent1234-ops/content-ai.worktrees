"""Frozen-bundle inputs and auditable Phase 2 outputs, without database writes."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from app.core.datetime_utils import utc_isoformat
from app.services.trend_topic_preparation import (
    CONTRACT, spreadsheet_text, title_fingerprint, validate_preparation_bundle,
)
from app.services.trend_topics import CATALOG_PATH, EXTRACTOR_VERSION


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_discovery_corpus(bundle: Path, *, source="development") -> tuple[list[dict], dict]:
    validation = validate_preparation_bundle(bundle)
    if not validation["valid"]:
        raise ValueError("Invalid frozen evaluation bundle: " + "; ".join(validation["errors"]))
    if source not in {"development", "discovery"}:
        raise ValueError("Only development or non-held-out discovery inputs are allowed")
    denylist = json.loads((bundle / "heldout_video_ids.json").read_text(encoding="utf-8"))
    heldout = set(denylist["video_ids"])
    # Read opaque hashes solely for exclusion; no test title enters extraction.
    title_hashes = set()
    for line in (bundle / "test" / "samples.jsonl").read_text(encoding="utf-8").splitlines():
        title_hashes.update(json.loads(line)["title_variants"])
    excluded_ids, excluded_title_ids, excluded_unverified = set(), set(), 0
    selected = {}
    if source == "development":
        for line in (bundle / "development" / "samples.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["video_id"] in heldout or set(row["title_variants"]) & title_hashes:
                raise ValueError("Development input overlaps the held-out set")
            selected[row["video_id"]] = row
    else:
        with (bundle / "observations.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                observation = json.loads(line)
                if observation["platform"] != "youtube":
                    continue
                for row in observation["items"]:
                    video_id = row.get("video_id")
                    if not video_id or not row.get("title_valid") or not row.get("rank_valid"):
                        excluded_unverified += 1
                        continue
                    if video_id in heldout:
                        excluded_ids.add(video_id)
                        continue
                    if title_fingerprint(row["title"]) in title_hashes:
                        excluded_title_ids.add(video_id)
                        continue
                    previous = selected.get(video_id)
                    at = observation["observed_at"]
                    if previous and datetime.fromisoformat(previous["provenance"]["observed_at"].replace("Z", "+00:00")) >= datetime.fromisoformat(at.replace("Z", "+00:00")):
                        continue
                    selected[video_id] = {"video_id": video_id, "title": row["title"],
                        "video_url": f"https://www.youtube.com/watch?v={video_id}",
                        "channel_title": row.get("channel_title"), "category": row.get("category"),
                        "provenance": {"run_id": observation["run_id"], "observed_at": at,
                            "ranking_scope": observation["ranking_scope"], "rank": row["rank"],
                            "identity_source": row["identity_source"], "trend_key": row.get("key")}}
    for video_id in excluded_title_ids:
        selected.pop(video_id, None)
    documents = sorted(selected.values(), key=lambda row: row["video_id"])
    input_sha = hashlib.sha256(json.dumps([(row["video_id"], row["title"]) for row in documents],
                                         ensure_ascii=False).encode("utf-8")).hexdigest()
    return documents, {"bundle": str(bundle.resolve()), "manifest_sha256": _sha(bundle / "manifest.json"),
        "contract": CONTRACT, "source": source, "documents": len(documents), "input_sha256": input_sha,
        "heldout_video_ids": len(heldout), "heldout_ids_excluded": len(excluded_ids),
        "heldout_title_copies_excluded": len(excluded_title_ids), "unverified_observation_rows_excluded": excluded_unverified,
        "label_status": validation["status"], "test_used_for_discovery": False}


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_discovery_run(output: Path, result: dict, *, input_report: dict, semantic_report: dict,
                        catalog_path: Path = CATALOG_PATH) -> dict:
    bundle = Path(input_report["bundle"]).resolve()
    if output.resolve().is_relative_to(bundle):
        raise ValueError("Discovery outputs must not modify the frozen evaluation bundle")
    output.mkdir(parents=True, exist_ok=False)
    for name, rows in (("documents.jsonl", result["documents"]), ("candidates.jsonl", result["candidates"])):
        with (output / name).open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    _write_json(output / "alias_suggestions.json", result["alias_suggestions"])
    columns = ("candidate_id", "label", "distinct_videos", "distinct_channel_titles", "semantic_similarity", "status")
    with (output / "candidates.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for candidate in result["candidates"]:
            row = {key: candidate[key] for key in columns}
            row["label"] = spreadsheet_text(row["label"])
            writer.writerow(row)
    manifest = {"phase": 2, "created_at": utc_isoformat(datetime.utcnow()), "extractor_version": EXTRACTOR_VERSION,
        "code_sha256": {name: _sha(Path(__file__).with_name(name))
                        for name in ("trend_topics.py", "trend_topic_discovery.py", "trend_topic_preparation.py")},
        "input": input_report, "semantic": semantic_report, "catalog": {"path": str(catalog_path.resolve()),
            "sha256": _sha(catalog_path), "version": result["catalog_version"]},
        "libraries": {name: version(name) for name in ("pythainlp", "keybert", "sentence-transformers")},
        "thresholds": result["thresholds"], "summary": result["summary"], "limitations": result["limitations"],
        "accuracy": None, "accuracy_status": "not_evaluated_against_human_labels", "files": {}}
    for name in ("documents.jsonl", "candidates.jsonl", "alias_suggestions.json", "candidates.csv"):
        manifest["files"][name] = _sha(output / name)
    _write_json(output / "run.json", manifest)
    known = Counter(topic["label"] for row in result["documents"] for topic in row["known_topics"])
    lines = ["# ผลการจับหัวข้อ Phase 2", "",
        "ผลนี้เป็นการทดลองสกัดหัวข้อจากชื่อ ไม่ใช่กราฟกระแสปัจจุบันหรือคะแนนความแม่น", "",
        f"- ชื่อคลิปไม่ซ้ำที่ประมวลผล: {result['summary']['unique_documents']}",
        f"- แหล่งข้อมูล: {input_report['source']} (กันชุด test แล้ว)",
        f"- หัวข้อใหม่ที่เสนอให้คนตรวจ: {len(result['candidates'])}",
        f"- คลิปที่ยังระบุหัวข้อไม่ได้: {result['summary']['statuses'].get('unknown', 0)}",
        f"- โมเดลจัดลำดับ: {semantic_report['status']}", "", "## หัวข้อที่รู้จัก", ""]
    lines += [f"- {label}: {count} คลิป" for label, count in known.items()] or ["ยังไม่พบหัวข้อในทะเบียนที่ตรงกับหลักฐานของชุดนี้"]
    lines += ["", "## ตัวอย่างข้อเสนอใหม่", "", "| หัวข้อที่เสนอ | คลิปไม่ซ้ำ | ชื่อช่องไม่ซ้ำ | สถานะ |",
              "|---|---:|---:|---|"]
    for candidate in result["candidates"][:20]:
        label = candidate["label"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {label} | {candidate['distinct_videos']} | {candidate['distinct_channel_titles']} | รอคนตรวจ |")
    lines += ["", "## เปิดไฟล์อะไรต่อ", "",
        "- [ข้อเสนอทั้งหมด](candidates.csv): รายการสำหรับตรวจ ยังไม่มีรายการใดถูกอนุมัติอัตโนมัติ",
        "- [หลักฐานของข้อเสนอ](candidates.jsonl): ชื่อคลิป ลิงก์ Video ID และตำแหน่งข้อความจริง",
        "- [ผลแต่ละคลิป](documents.jsonl): แยกหัวข้อที่รู้จัก ข้อเสนอรอตรวจ และ unknown",
        "- [คู่ชื่อที่คล้ายกัน](alias_suggestions.json): เป็นเพียงข้อเสนอ ไม่ได้รวมเป็นหัวข้อเดียวกัน",
        "- [วิธีและค่าที่ใช้รัน](run.json): โมเดล รุ่นข้อมูล เกณฑ์ และ hash ไฟล์", "",
        "จำนวนคลิปนับจากชุดที่นำมาทดลอง ไม่ใช่จำนวนคลิปใน Top 50 ณ เวลาปัจจุบัน",
        "semantic_similarity คือความเกี่ยวข้องของข้อความ ไม่ใช่เปอร์เซ็นต์ความแม่นหรือโอกาสไวรัล",
        "ยังไม่ใช้ยอดวิว ไลก์ คำอธิบาย หรือชุด test มาช่วยตัดสินหัวข้อ และยังไม่ได้สร้างคำตอบเฉลยแทนคน", ""]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return manifest
