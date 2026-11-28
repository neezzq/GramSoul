"""A consistent copy of the database for deploy/backup.sh (encrypted with the same key when DATA_KEY is set).

    python -m app.backup /data/backup.sqlite3
"""
import sys

from . import crypto
from .config import settings
from .db import Database


def main(dest: str) -> None:
    db = Database(settings.db_path, crypto.db_key_hex())
    try:
        db.backup_to(dest)
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/data/backup.sqlite3")
