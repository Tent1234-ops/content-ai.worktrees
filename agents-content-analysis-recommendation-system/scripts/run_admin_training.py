"""Independent worker; an API restart does not terminate a training run."""
import argparse
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.model_management import execute_training_run

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, type=UUID)
    args = parser.parse_args()
    execute_training_run(str(args.run_id))
