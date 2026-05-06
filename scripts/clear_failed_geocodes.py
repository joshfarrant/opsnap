#!/usr/bin/env python3
"""
Clear failed geocode cache entries so they can be retried.

Run this after improving location normalisation in ingest.py,
then re-run ingest.py followed by geocode.py.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "opsnap.db"


def clear_failed():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM geocode_cache WHERE geocode_status = 'not_found'")
    not_found = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM geocode_cache WHERE geocode_status = 'skipped'")
    skipped = cur.fetchone()[0]

    cur.execute("DELETE FROM geocode_cache WHERE geocode_status = 'not_found'")
    cur.execute("DELETE FROM geocode_cache WHERE geocode_status = 'skipped'")
    conn.commit()

    print(f"Cleared {not_found} not_found and {skipped} skipped entries")
    print("Re-run ingest.py then geocode.py to retry with improved normalisation")

    conn.close()


if __name__ == "__main__":
    clear_failed()
