from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import hash_password  # noqa: E402
from app.database.db import SessionLocal  # noqa: E402
from app.database.models import User  # noqa: E402


def _password_from_prompt() -> str:
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match")
    if len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a local Content AI admin account without storing a password in a script."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    username = args.username.strip()
    email = args.email.strip().lower()
    if len(username) < 3:
        parser.error("username must contain at least 3 characters")
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        parser.error("email is invalid")

    try:
        password = _password_from_prompt()
    except ValueError as exc:
        parser.error(str(exc))

    db = SessionLocal()
    try:
        existing = (
            db.query(User)
            .filter((User.email == email) | (User.username == username))
            .first()
        )
        if existing is not None:
            print(
                "Account already exists. Use another username/email; "
                "this command does not silently promote existing users."
            )
            return 1
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(
            f"Admin created: user_id={user.user_id}, "
            f"username={user.username}, email={user.email}"
        )
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
