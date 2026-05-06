#!/usr/bin/env python3
"""
Ingest Operation Snap PDFs into SQLite.

Reads all PDFs from data/pdfs/, parses them into structured records,
and writes to data/opsnap.db. Idempotent — drops and rebuilds on each run.
"""

import re
import sqlite3
import sys
from pathlib import Path

import pdfplumber

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
PDF_DIR = PROJECT_DIR / "data" / "pdfs"
DB_PATH = PROJECT_DIR / "data" / "opsnap.db"

# Map normalised (whitespace-collapsed, lowercased) headers to canonical names
HEADER_MAP = {
    "reporter transport mode": "reporter_transport_mode",
    "reporter transpor t mode": "reporter_transport_mode",
    "offender vehicle make": "vehicle_make",
    "offender vehicle model": "vehicle_model",
    "offnder vehicle model": "vehicle_model",
    "offender vehicle colour": "vehicle_colour",
    "offence": "offence",
    "second offence": "second_offence",
    "offence location": "offence_location",
    "off location": "offence_location",
    "council area": "council_area",
    "disposal": "disposal",
    "disposals": "disposal",
    "rationale for nfa": "nfa_rationale",
    "witness contacted": "witness_contacted",
}

# Known valid disposal values for normalising garbled text
VALID_DISPOSALS = [
    "Education",
    "Warning Letter",
    "Fixed Penalty",
    "NFA",
    "Court",
    "Other Action Taken",
    "Duplicate Submission",
    "RTC - Actioned",
    "Out of Force",
    "No Offence",
    "No Independent Evidence Available",
    "No VRM",
    "N/A",
]

CANONICAL_COLUMNS = [
    "reporter_transport_mode",
    "vehicle_make",
    "vehicle_model",
    "vehicle_colour",
    "offence",
    "second_offence",
    "offence_location",
    "council_area",
    "disposal",
    "nfa_rationale",
    "witness_contacted",
]


def normalise_header(raw: str) -> str | None:
    """Map a raw PDF header string to its canonical column name."""
    # Collapse all whitespace (newlines, multiple spaces) into single spaces
    cleaned = re.sub(r"\s+", " ", raw.strip()).lower()
    return HEADER_MAP.get(cleaned)


def _is_subsequence(needle: str, haystack: str) -> bool:
    """Check if needle appears as a character subsequence in haystack."""
    it = iter(haystack.lower())
    return all(c in it for c in needle.lower())


def normalise_disposal(raw: str | None) -> str | None:
    """Fix garbled disposal values from PDF extraction artefacts."""
    if not raw:
        return None

    val = raw.strip()

    # Exact match (case-insensitive)
    for valid in VALID_DISPOSALS:
        if val.lower() == valid.lower():
            return valid

    # Substring match (handles truncation like "Other Action Take")
    for valid in VALID_DISPOSALS:
        if valid.lower() in val.lower():
            return valid

    # Prefix match (raw value is a truncated version of a valid disposal)
    for valid in sorted(VALID_DISPOSALS, key=len, reverse=True):
        if valid.lower().startswith(val.lower()) or val.lower().startswith(valid.lower()):
            return valid

    # Handle newlines in the middle of a disposal
    collapsed = re.sub(r"\s+", " ", val).strip()
    for valid in VALID_DISPOSALS:
        if collapsed.lower() == valid.lower():
            return valid

    # Subsequence match (handles garbled interleaved text)
    # Check longest valid disposals first to avoid false matches
    for valid in sorted(VALID_DISPOSALS, key=len, reverse=True):
        if _is_subsequence(valid, val):
            return valid

    return val


def extract_month_year(filename: str) -> str:
    """Extract YYYY-MM from a filename like 'op-snap---monthly-publication-january-2026.pdf'."""
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    name = filename.lower().replace(".pdf", "")
    for month_name, month_num in months.items():
        if month_name in name:
            year_match = re.search(r"(\d{4})", name)
            if year_match:
                return f"{year_match.group(1)}-{month_num}"
    return "unknown"


def try_table_extraction(pdf: pdfplumber.PDF) -> list[dict] | None:
    """
    Try to extract data using pdfplumber's table detection.
    Returns list of row dicts if successful, None if format not suitable.
    """
    page = pdf.pages[0]
    tables = page.extract_tables()

    if not tables or len(tables[0]) < 2:
        return None

    # Validate headers
    raw_headers = tables[0][0]
    if len(raw_headers) < 8:
        return None

    header_map = {}
    for i, raw in enumerate(raw_headers):
        canonical = normalise_header(raw or "")
        if canonical:
            header_map[i] = canonical

    # Need at least the core columns
    mapped = set(header_map.values())
    required = {
        "reporter_transport_mode",
        "vehicle_make",
        "offence",
        "offence_location",
        "council_area",
        "disposal",
    }
    if not required.issubset(mapped):
        return None

    # Extract all rows from all pages
    rows = []
    for page in pdf.pages:
        page_tables = page.extract_tables()
        for table in page_tables:
            for row in table:
                # Skip header rows
                first_cell = (row[0] or "").strip().lower()
                if not first_cell or "reporter" in first_cell or "transport" in first_cell:
                    continue

                record = {col: None for col in CANONICAL_COLUMNS}
                for i, canonical in header_map.items():
                    if i < len(row):
                        val = (row[i] or "").strip()
                        record[canonical] = val if val else None
                rows.append(record)

    return rows


def normalise_location(raw: str | None) -> str | None:
    """Normalise location strings for consistency and better geocoding."""
    if not raw:
        return None

    loc = raw.strip()
    loc = loc.rstrip(",.")
    loc = re.sub(r"\.\.", "", loc)
    loc = loc.strip()

    if not loc or loc.lower() == "unknown":
        return None

    # Expand common abbreviations
    loc = re.sub(r"\bRd\b", "Road", loc)
    loc = re.sub(r"\bSt\b", "Street", loc)
    loc = re.sub(r"\bLn\b", "Lane", loc)
    loc = re.sub(r"\bAv\b", "Avenue", loc)
    loc = re.sub(r"\bDr\b", "Drive", loc)
    loc = re.sub(r"\bBlvd\b", "Boulevard", loc)
    loc = re.sub(r"\bCres\b", "Crescent", loc)
    loc = re.sub(r"\bNB\b", "Northbound", loc)
    loc = re.sub(r"\bSB\b", "Southbound", loc)

    # Normalise whitespace
    loc = re.sub(r"\s+", " ", loc).strip()

    # Strip leading A-road prefixes when followed by a road name
    # e.g. "A38 Bristol Road" -> "Bristol Road" (the name is more geocodable)
    loc = re.sub(r"^A\d+\s+(?=[A-Z][a-z])", "", loc)

    # Title-case if all lower or all upper
    if loc == loc.lower() or loc == loc.upper():
        loc = loc.title()

    # Known corrections (from fuzzy matching analysis)
    corrections = {
        "Barsnley Road": "Barnsley Road",
        "Barnslaey Road": "Barnsley Road",
        "Barnsley Raod": "Barnsley Road",
        "Startford Road": "Stratford Road",
        "Stratfrod Road": "Stratford Road",
        "Harbourne Road": "Harborne Road",
        "Tetenhall High Street": "Tettenhall High Street",
        "Hill Villiage Road": "Hill Village Road",
        "Foles Hill Road": "Foleshill Road",
        "Sherbourne Street": "Sherborne Street",
        "Alceseter Road": "Alcester Road",
        "Ancester Road": "Alcester Road",
        "Aslcester Road": "Alcester Road",
        "Bekgrave Middleway": "Belgrave Middleway",
        "Belgrade Middleway": "Belgrave Middleway",
        "Aston Web Boulevard": "Aston Webb Boulevard",
        "Aston Weeb Boulevard": "Aston Webb Boulevard",
        "Aston Webb Bouelvard": "Aston Webb Boulevard",
        "Barclary Road": "Barclay Road",
        "Aldrige Road": "Aldridge Road",
        "Alridge Road": "Aldridge Road",
        "Abey Road": "Abbey Road",
        "Hight Street": "High Street",
    }
    loc = corrections.get(loc, loc)

    return loc if loc else None


def normalise_council_area(raw: str | None) -> str | None:
    """Standardise council area names."""
    if not raw:
        return None

    area = raw.strip().title()

    aliases = {
        "Sutton Coldfield": "Sutton Coldfield",
        "Out Of Force Area": "Out of Force Area",
        "Out Of Force": "Out of Force Area",
        "Metropolitan Borough Of Walsall": "Walsall",
    }
    return aliases.get(area, area)


# Vehicle make normalisation — maps common variations to canonical names
VEHICLE_MAKE_MAP = {
    "mercedes": "Mercedes-Benz",
    "mercedes-benz": "Mercedes-Benz",
    "mercedes benz": "Mercedes-Benz",
    "merc": "Mercedes-Benz",
    "vw": "Volkswagen",
    "volkswagon": "Volkswagen",
    "volkswagen": "Volkswagen",
    "bmw": "BMW",
    "land rover": "Land Rover",
    "landrover": "Land Rover",
    "range rover": "Land Rover",
    "alfa romeo": "Alfa Romeo",
    "rolls royce": "Rolls-Royce",
    "rolls-royce": "Rolls-Royce",
    "aston martin": "Aston Martin",
    "mini": "Mini",
    "mini cooper": "Mini",
}


def normalise_vehicle_make(raw: str | None) -> str | None:
    """Standardise vehicle make names."""
    if not raw:
        return None

    make = raw.strip()
    if not make:
        return None

    canonical = VEHICLE_MAKE_MAP.get(make.lower())
    if canonical:
        return canonical

    # Title-case if all lower or all upper
    if make == make.lower() or make == make.upper():
        make = make.title()

    return make


def create_database(db_path: Path, records: list[dict]):
    """Create SQLite database and write all records."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS reports")
    cur.execute("""
        CREATE TABLE reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            source_page INTEGER,
            source_row INTEGER,
            month TEXT NOT NULL,
            reporter_transport_mode TEXT,
            vehicle_make TEXT,
            vehicle_model TEXT,
            vehicle_colour TEXT,
            offence TEXT,
            second_offence TEXT,
            offence_location_raw TEXT,
            offence_location TEXT,
            council_area_raw TEXT,
            council_area TEXT,
            disposal TEXT,
            nfa_rationale TEXT,
            witness_contacted TEXT
        )
    """)

    cur.execute("CREATE INDEX idx_month ON reports(month)")
    cur.execute("CREATE INDEX idx_council_area ON reports(council_area)")
    cur.execute("CREATE INDEX idx_offence ON reports(offence)")
    cur.execute("CREATE INDEX idx_disposal ON reports(disposal)")
    cur.execute("CREATE INDEX idx_location ON reports(offence_location)")

    cur.executemany(
        """
        INSERT INTO reports (
            source_file, source_page, source_row, month,
            reporter_transport_mode, vehicle_make, vehicle_model, vehicle_colour,
            offence, second_offence,
            offence_location_raw, offence_location,
            council_area_raw, council_area,
            disposal, nfa_rationale, witness_contacted
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r["source_file"],
                r["source_page"],
                r["source_row"],
                r["month"],
                r["reporter_transport_mode"],
                r["vehicle_make"],
                r["vehicle_model"],
                r["vehicle_colour"],
                r["offence"],
                r["second_offence"],
                r["offence_location_raw"],
                r["offence_location"],
                r["council_area_raw"],
                r["council_area"],
                r["disposal"],
                r["nfa_rationale"],
                r["witness_contacted"],
            )
            for r in records
        ],
    )

    conn.commit()
    conn.close()


def ingest():
    """Main ingestion pipeline."""
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {PDF_DIR}")
        sys.exit(1)

    print(f"Found {len(pdf_files)} PDFs in {PDF_DIR}")

    all_records = []

    for pdf_path in pdf_files:
        filename = pdf_path.name
        month_year = extract_month_year(filename)

        pdf = pdfplumber.open(pdf_path)

        rows = try_table_extraction(pdf)
        if rows is None:
            print(f"  {filename}: SKIPPED (unsupported format)")
            pdf.close()
            continue

        # Add metadata and normalise
        for i, row in enumerate(rows):
            row["source_file"] = filename
            row["source_page"] = None
            row["source_row"] = i
            row["month"] = month_year
            row["offence_location_raw"] = row.get("offence_location")
            row["offence_location"] = normalise_location(row.get("offence_location"))
            row["council_area_raw"] = row.get("council_area")
            row["council_area"] = normalise_council_area(row.get("council_area"))
            row["disposal"] = normalise_disposal(row.get("disposal"))
            row["vehicle_make"] = normalise_vehicle_make(row.get("vehicle_make"))

        all_records.extend(rows)
        print(f"  {filename}: {len(rows)} rows")

        pdf.close()

    print(f"\nTotal records: {len(all_records)}")

    create_database(DB_PATH, all_records)
    print(f"Database written to {DB_PATH}")

    # Summary stats
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("\n--- Summary ---")
    cur.execute("SELECT month, COUNT(*) FROM reports GROUP BY month ORDER BY month")
    for month, count in cur.fetchall():
        print(f"  {month}: {count}")

    cur.execute(
        "SELECT disposal, COUNT(*) FROM reports GROUP BY disposal ORDER BY COUNT(*) DESC"
    )
    print("\nDisposal breakdown:")
    for disposal, count in cur.fetchall():
        print(f"  {disposal}: {count}")

    conn.close()


if __name__ == "__main__":
    ingest()
