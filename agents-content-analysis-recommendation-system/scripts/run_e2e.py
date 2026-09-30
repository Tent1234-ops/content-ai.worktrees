"""
Simple E2E runner to analyze a video file and save artifacts (before/after transcript, recommendation).
Usage:
  python scripts/run_e2e.py --input Z:\path\to\video.mp4 --model small --out artifacts/

The script calls the same analyze pipeline used by the API but in-process and saves outputs for review.
"""
import os
import argparse
import json
from app.services.pipeline.core import analyze_video

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--model", default="small", choices=["small","medium","large"]) 
parser.add_argument("--out", default="artifacts")
args = parser.parse_args()

os.makedirs(args.out, exist_ok=True)

print(f"Running E2E analyze for {args.input} using model={args.model}")
# Set runtime model via environment runtime store if available
try:
    from app.runtime import set as runtime_set
    runtime_set('asr_model', args.model)
except Exception:
    pass

res = analyze_video(args.input)

out_path = os.path.join(args.out, os.path.basename(args.input) + ".json")
with open(out_path, 'w', encoding='utf8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)

print('Saved artifact to', out_path)
