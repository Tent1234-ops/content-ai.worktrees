"""Windowless Task Scheduler entry point; launch with pythonw.exe on Windows."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_collector(*, root: Path | None = None, executable: str | None = None,
                  status_only: bool = False) -> int:
    root = root or Path(__file__).resolve().parents[1]
    python = Path(executable or sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    logs = root / "artifacts"
    try:
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / "trend-scheduler.stdout.log").open("w", encoding="utf-8") as stdout, \
                (logs / "trend-scheduler.stderr.log").open("w", encoding="utf-8") as stderr:
            command = [str(python), "-B", "-X", "utf8",
                       str(root / "scripts" / "collect_trend_snapshots.py")]
            if status_only:
                command.append("--status")
            try:
                # pythonw has no console; explicitly prevent its console child
                # from allocating one, and provide all three standard handles.
                result = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL,
                                        stdout=stdout, stderr=stderr, shell=False,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return result.returncode
            except OSError as exc:
                stderr.write(f"Cannot start trend collector ({type(exc).__name__}). "
                             "Check Python, workspace and database availability.\n")
                return 1
    except OSError:
        # pythonw may have no stderr. Task Scheduler must still report failure
        # if diagnostic files cannot be opened (for example an unavailable drive).
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Check settings without fetching providers")
    args = parser.parse_args()
    return run_collector(status_only=args.status)


if __name__ == "__main__":
    raise SystemExit(main())
