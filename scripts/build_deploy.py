#!/usr/bin/env python3
"""
Build the deployable database from the working (view) database.

Datasette ships data/opsnap-deploy.db (see Dockerfile). This script produces
it from data/opsnap-view.db by copying the file and clearing coordinates that
fall outside the West Midlands county bounding box — Nominatim occasionally
mis-geocodes motorway junctions and out-of-force locations to other counties
(Leeds, Shropshire, etc.), and those would otherwise show as stray map pins.

The bounding box below reproduces the original 6 May 2026 cleanup exactly
(retains 20,186 of 20,251 geocoded reports, clears 65 outliers).

Usage:
    python scripts/build_deploy.py
"""

import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
VIEW_DB = PROJECT_DIR / "data" / "opsnap-view.db"
DEPLOY_DB = PROJECT_DIR / "data" / "opsnap-deploy.db"

# West Midlands metropolitan county bounding box
WM_LAT_MIN, WM_LAT_MAX = 52.30, 52.70
WM_LNG_MIN, WM_LNG_MAX = -2.21, -1.43


def build_deploy():
    if not VIEW_DB.exists():
        sys.exit(f"View DB not found: {VIEW_DB}. Run ingest.py + geocode.py first.")

    shutil.copyfile(VIEW_DB, DEPLOY_DB)

    conn = sqlite3.connect(DEPLOY_DB)
    cur = conn.cursor()

    before = cur.execute(
        "SELECT COUNT(*) FROM reports WHERE latitude IS NOT NULL"
    ).fetchone()[0]

    cur.execute(
        """
        UPDATE reports
        SET latitude = NULL, longitude = NULL
        WHERE latitude IS NOT NULL
          AND NOT (
            latitude BETWEEN ? AND ?
            AND longitude BETWEEN ? AND ?
          )
        """,
        (WM_LAT_MIN, WM_LAT_MAX, WM_LNG_MIN, WM_LNG_MAX),
    )
    cleared = cur.rowcount
    conn.commit()

    after = cur.execute(
        "SELECT COUNT(*) FROM reports WHERE latitude IS NOT NULL"
    ).fetchone()[0]
    total = cur.execute("SELECT COUNT(*) FROM reports").fetchone()[0]

    # Reclaim space from the in-place updates so the shipped file stays lean.
    conn.isolation_level = None
    cur.execute("VACUUM")
    conn.close()

    print(f"Copied {VIEW_DB.name} -> {DEPLOY_DB.name}")
    print(f"Geocoded before cleanup: {before}")
    print(f"Outliers cleared (outside WM bbox): {cleared}")
    print(f"Geocoded after cleanup: {after} / {total} ({100 * after / total:.1f}%)")


if __name__ == "__main__":
    build_deploy()
