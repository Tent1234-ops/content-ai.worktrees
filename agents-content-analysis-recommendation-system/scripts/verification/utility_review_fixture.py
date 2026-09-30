"""Create isolated browser fixtures, never research or human-review artifacts."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.analysis_evaluation import (allocate_variant_orders, build_presentation_variants,
                                            freeze_utility_protocol, validate_utility_responses)
from app.services.recommendation_utility_study import build_blind_packets, render_review_html
from scripts.evaluate_analysis import new_output, read, write
from tests.test_recommendation_utility_evaluation import recommendation_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if args.validate:
        fixture = read(out / "fixture.private.json")
        response = read(out / "synthetic-responses.json")
        result = validate_utility_responses(response_documents=[response], allocations=fixture["allocations"],
                                           protocol=fixture["protocol"], case_outputs=fixture["outputs"])
        assert result["accepted_rating_count"] == 6, result
        assert not result["rejected"], result
        write(out / "validation.json", {"synthetic_only": True, "rating_count": 6, "passed": True})
        return
    out = new_output(out)
    result = recommendation_result()
    evidence = result["recommendation"]["evidence_bundle"]
    for doc in evidence["reference_documents"]:
        doc.update(title=f"Synthetic source {doc['dataset_id']}", url="https://www.youtube.com/watch?v=fixture-only",
                   statistics={"views": 1500, "likes": 50, "comments": 5})
    evidence["topic_comparisons"]["items"][0]["metrics"] = {
        "views": {"status": "comparison_descriptive", "detected": {"count": 10, "median": 1200, "p25": 950, "p75": 1400},
                  "not_detected": {"count": 10, "median": 1500, "p25": 1300, "p75": 1900},
                  "paired_channel_count": 5, "within_channel_median_difference": -300,
                  "uncertainty": {"status": "uncertainty_unavailable"},
                  "limitation": "ข้อมูลจำลองสำหรับทดสอบซอฟต์แวร์ ไม่ใช่ผลวิจัย"}}
    outputs = {"case-advice": {"analysis_status": "completed", "variants": build_presentation_variants(result)},
               "case-empty": {"analysis_status": "completed", "variants": build_presentation_variants({})}}
    for value in outputs.values():
        value["video_uri"] = (out / "fixture.mp4").as_uri()
    protocol = freeze_utility_protocol(study_id="synthetic-browser-only", manifest_sha256="a"*64,
                                      context_lock={}, reviewer_ids=["browser-fixture"], seed=42)
    allocations = allocate_variant_orders(study_id=protocol["study_id"], protocol_sha256=protocol["protocol_sha256"],
        case_ids=list(outputs), reviewer_ids=protocol["reviewer_ids"], seed=42)
    packets, private = build_blind_packets(protocol=protocol, allocations=allocations, case_outputs=outputs)
    (out / "review.html").write_text(render_review_html(packets["browser-fixture"]), encoding="utf-8")
    write(out / "fixture.private.json", {"synthetic_only": True, "protocol": protocol,
                                         "outputs": outputs, "allocations": private["allocations"]})


if __name__ == "__main__":
    main()
