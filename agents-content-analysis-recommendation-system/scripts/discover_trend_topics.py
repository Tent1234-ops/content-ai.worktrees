"""Run title-only topic discovery on non-held-out data with local models."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--source", choices=("development", "discovery"), default="development")
    parser.add_argument("--semantic", choices=("required", "off"), default="required")
    parser.add_argument("--min-videos", type=int, default=3)
    parser.add_argument("--min-channel-titles", type=int, default=2)
    parser.add_argument("--min-similarity", type=float, default=0.30)
    parser.add_argument("--max-candidates", type=int, default=2000)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "trend_topics" / "catalog.v1.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    os.environ["CONTENT_AI_SKIP_DB_BOOTSTRAP"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from app.services.trend_topics import LocalSemanticRanker, analyze_topic_titles, load_catalog
    from app.services.trend_topic_discovery import read_discovery_corpus, write_discovery_run

    output = args.output or ROOT / "artifacts" / "trend-topics" / "runs" / datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    if output.exists():
        parser.error("Output already exists; previous evidence must not be overwritten")
    catalog = load_catalog(args.catalog)
    documents, input_report = read_discovery_corpus(args.bundle, source=args.source)
    print(json.dumps({"stage": "inputs_verified", **input_report}, ensure_ascii=False), flush=True)
    semantic = LocalSemanticRanker() if args.semantic == "required" else None
    semantic_report = semantic.metadata if semantic else {"status": "explicitly_disabled", "ranker": "document_support_only"}
    result = analyze_topic_titles(documents, catalog=catalog, semantic=semantic,
        min_videos=args.min_videos, min_channel_titles=args.min_channel_titles,
        min_similarity=args.min_similarity, max_candidates=args.max_candidates)
    manifest = write_discovery_run(output, result, input_report=input_report,
        semantic_report=semantic_report, catalog_path=args.catalog)
    print(json.dumps({"output": str(output.resolve()), "summary": manifest["summary"],
        "semantic": manifest["semantic"], "accuracy_status": manifest["accuracy_status"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
