#!/usr/bin/env python
"""Hidden background worker entry point for one Outcome training run."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("CONTENT_AI_SKIP_DB_BOOTSTRAP", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.outcome_model_management import execute_training_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    execute_training_run(args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
