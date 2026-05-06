#!/usr/bin/env python3
"""
Geocode Operation Snap offence locations using OpenStreetMap Nominatim.

Reads unique (offence_location, council_area) pairs from opsnap.db,
geocodes them via Nominatim, and stores results in a geocode_cache table.
Then updates the reports table with lat/lng from the cache.

Uses a persistent cache — only geocodes locations not already cached.
Rate-limited to 1 request per second per Nominatim usage policy.
"""

import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DB_PATH = PROJECT_DIR / "data" / "opsnap.db"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "opsnap-geocoder/0.1 (civic data project)"

# Council areas mapped to search suffixes for better geocoding
COUNCIL_SEARCH_AREAS = {
    "Birmingham": "Birmingham, West Midlands, England",
    "Coventry": "Coventry, West Midlands, England",
    "Dudley": "Dudley, West Midlands, England",
    "Sandwell": "Sandwell, West Midlands, England",
    "Solihull": "Solihull, West Midlands, England",
    "Walsall": "Walsall, West Midlands, England",
    "Wolverhampton": "Wolverhampton, West Midlands, England",
    "Sutton Coldfield": "Sutton Coldfield, Birmingham, England",
}


def setup_cache(conn: sqlite3.Connection):
    """Create geocode cache table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocode_cache (
            location_key TEXT PRIMARY KEY,
            offence_location TEXT NOT NULL,
            council_area TEXT,
            query_sent TEXT,
            latitude REAL,
            longitude REAL,
            display_name TEXT,
            geocode_status TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def ensure_report_columns(conn: sqlite3.Connection):
    """Add lat/lng columns to reports table if they don't exist."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(reports)")
    columns = {row[1] for row in cur.fetchall()}

    if "latitude" not in columns:
        cur.execute("ALTER TABLE reports ADD COLUMN latitude REAL")
    if "longitude" not in columns:
        cur.execute("ALTER TABLE reports ADD COLUMN longitude REAL")
    conn.commit()


def make_cache_key(location: str, council_area: str | None) -> str:
    """Create a stable cache key from location + council area."""
    return f"{(location or '').lower().strip()}|{(council_area or '').lower().strip()}"


def build_query(location: str, council_area: str | None) -> str:
    """Build a geocoding query string from location and council area."""
    loc = location.strip()

    # Skip vague motorway references without junctions
    if re.match(r"^[AM]\d+$", loc):
        return ""

    # For motorway junctions, build a specific query
    m = re.match(r"^(M\d+)\s+(?:NB|SB|EB|WB)?\s*(?:J|Jct|Junction)\s*(\d+)", loc, re.IGNORECASE)
    if m:
        return f"{m.group(1)} Junction {m.group(2)}, England"

    # Get the search area suffix
    area_suffix = COUNCIL_SEARCH_AREAS.get(council_area, "West Midlands, England")

    return f"{loc}, {area_suffix}"


def geocode_nominatim(query: str) -> dict:
    """
    Query Nominatim and return result.
    Returns dict with lat, lon, display_name, status.
    """
    if not query:
        return {"status": "skipped", "lat": None, "lon": None, "display_name": None}

    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "gb",
    })
    url = f"{NOMINATIM_URL}?{params}"

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if data:
            result = data[0]
            return {
                "status": "found",
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "display_name": result.get("display_name"),
            }
        else:
            return {"status": "not_found", "lat": None, "lon": None, "display_name": None}
    except Exception as e:
        return {"status": f"error: {e}", "lat": None, "lon": None, "display_name": None}


def geocode():
    """Main geocoding pipeline."""
    conn = sqlite3.connect(DB_PATH)
    setup_cache(conn)
    ensure_report_columns(conn)

    cur = conn.cursor()

    # Get all unique location+council pairs
    cur.execute("""
        SELECT DISTINCT offence_location, council_area
        FROM reports
        WHERE offence_location IS NOT NULL
        ORDER BY COUNT(*) OVER (PARTITION BY offence_location, council_area) DESC
    """)
    all_pairs = cur.fetchall()
    total = len(all_pairs)

    # Check which ones are already cached
    uncached = []
    for location, council_area in all_pairs:
        key = make_cache_key(location, council_area)
        cur.execute("SELECT 1 FROM geocode_cache WHERE location_key = ?", (key,))
        if not cur.fetchone():
            uncached.append((location, council_area))

    cached_count = total - len(uncached)
    print(f"Total unique locations: {total}")
    print(f"Already cached: {cached_count}")
    print(f"To geocode: {len(uncached)}")

    if not uncached:
        print("Nothing to geocode.")
    else:
        # Estimate time
        est_minutes = len(uncached) / 60
        print(f"Estimated time: {est_minutes:.0f} minutes (1 req/sec)")
        print()

        found = 0
        not_found = 0
        skipped = 0
        errors = 0

        for i, (location, council_area) in enumerate(uncached):
            key = make_cache_key(location, council_area)
            query = build_query(location, council_area)
            result = geocode_nominatim(query)

            cur.execute(
                """
                INSERT OR REPLACE INTO geocode_cache
                (location_key, offence_location, council_area, query_sent,
                 latitude, longitude, display_name, geocode_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    location,
                    council_area,
                    query,
                    result["lat"],
                    result["lon"],
                    result["display_name"],
                    result["status"],
                ),
            )

            if result["status"] == "found":
                found += 1
            elif result["status"] == "not_found":
                not_found += 1
            elif result["status"] == "skipped":
                skipped += 1
            else:
                errors += 1

            # Progress every 100
            if (i + 1) % 100 == 0 or i + 1 == len(uncached):
                conn.commit()
                pct = 100 * (i + 1) / len(uncached)
                print(
                    f"  [{i+1}/{len(uncached)}] ({pct:.0f}%) "
                    f"found={found} not_found={not_found} skipped={skipped} errors={errors}"
                )

            # Rate limit: 1 request per second
            if result["status"] != "skipped":
                time.sleep(1.05)

        conn.commit()
        print(f"\nGeocoding complete: {found} found, {not_found} not found, {skipped} skipped, {errors} errors")

    # Update reports table with lat/lng from cache
    print("\nUpdating reports with coordinates...")
    cur.execute("""
        UPDATE reports
        SET latitude = gc.latitude,
            longitude = gc.longitude
        FROM geocode_cache gc
        WHERE gc.location_key = (
            LOWER(TRIM(reports.offence_location)) || '|' || LOWER(TRIM(COALESCE(reports.council_area, '')))
        )
        AND gc.latitude IS NOT NULL
    """)
    updated = cur.rowcount
    conn.commit()

    # Stats
    cur.execute("SELECT COUNT(*) FROM reports WHERE latitude IS NOT NULL")
    geocoded = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM reports")
    total_reports = cur.fetchone()[0]
    print(f"Reports with coordinates: {geocoded} / {total_reports} ({100*geocoded/total_reports:.1f}%)")

    cur.execute("""
        SELECT geocode_status, COUNT(*) FROM geocode_cache
        GROUP BY geocode_status ORDER BY COUNT(*) DESC
    """)
    print("\nCache status breakdown:")
    for status, count in cur.fetchall():
        print(f"  {status}: {count}")

    conn.close()


if __name__ == "__main__":
    geocode()
