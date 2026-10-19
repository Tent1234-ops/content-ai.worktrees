"""Read-only actual saved-content comparison; never retrain or rewrite history."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['CONTENT_AI_SKIP_DB_BOOTSTRAP'] = '1'

from app.database.db import SessionLocal, engine
from app.database.models import AnalysisResult, UserContent
from app.schemas.performance_clustering import PerformanceClusteringResponse
from app.services.performance_clustering import performance_for_content
from app.services.outcome_prediction_readiness import reject_database_writes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content-id', type=int, default=41)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / 'artifacts')
    with reject_database_writes(engine), SessionLocal() as db:
        content = db.get(UserContent, args.content_id)
        if not content:
            raise ValueError('Saved content not found')
        before = [(a.result_id, a.summary) for a in db.query(AnalysisResult).filter_by(content_id=content.content_id)]
        result = PerformanceClusteringResponse.model_validate(performance_for_content(
            db, user_id=content.user_id, content_id=content.content_id, minimum_views=25000)).model_dump(mode='json')
        db.expire_all()
        after = [(a.result_id, a.summary) for a in db.query(AnalysisResult).filter_by(content_id=content.content_id)]
        assert before == after
        report = {'mode': 'read_only_actual_data', 'saved_results_unchanged': True,
            'content_id': content.content_id, 'title': content.title,
            **{k: result[k] for k in ('as_of', 'category', 'reference_count', 'eligible_count',
                'minimum_views', 'excluded_counts', 'clustering', 'content_similarity', 'data_fingerprint')}}
        output.mkdir(parents=True, exist_ok=True)
        for filename, payload in [('actual-response.json', result), ('audit.json', report)]:
            (output / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
