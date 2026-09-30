import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.db import Base, engine
from app.database.migrations import archive_phase10_notification_tables
import app.database.models  # noqa: F401


def main() -> None:
    archived = archive_phase10_notification_tables(engine)
    Base.metadata.create_all(bind=engine)
    print({"status": "ok", "archived_tables": archived})


if __name__ == "__main__":
    main()
