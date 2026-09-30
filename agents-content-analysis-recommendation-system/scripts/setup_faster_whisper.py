from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from faster_whisper.utils import download_model

from models.speech_to_text import check_model_readiness, configured_model_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and verify the Faster Whisper model used by Content AI."
    )
    parser.add_argument("--model", default="small", help="Model size or Hugging Face model id")
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Materialize only from an existing Hugging Face cache without network access",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Check required model files without downloading",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = configured_model_path(args.model)
    if not args.verify_only:
        target.mkdir(parents=True, exist_ok=True)
        print(f"Preparing Faster Whisper '{args.model}' at {target}", flush=True)
        download_model(
            args.model,
            output_dir=str(target),
            local_files_only=args.local_files_only,
        )

    readiness = check_model_readiness(args.model)
    print(readiness)
    return 0 if readiness["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
