#!/usr/bin/env python3
"""
Compare a PDF and an xlsx Operation Snap publication for the same month.

West Midlands Police published their first machine-readable xlsx for the
March 2026 publication, alongside the usual PDF. This harness parses both
through the shared pipeline (scripts/ingest.py) and reports how faithfully
each format ingests — row counts, per-field agreement (raw and normalised),
sample divergences, and value-set differences.

It does not touch the production database. Pure read + report.

Usage:
    python scripts/compare_sources.py <pdf-or-xlsx> <pdf-or-xlsx>
    # or, with no args, defaults to the March 2026 pair in ~/Downloads
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest import PARSERS, extract_month_year, normalise_record

# Fields present in both formats (the xlsx has no "witness contacted" column,
# and the March 2026 PDF carries no witness data either, so it's excluded).
RAW_FIELDS = [
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
]

# Normalised fields gain the *_raw companions written by normalise_record.
NORMALISED_FIELDS = [
    "vehicle_make",
    "offence_location",
    "council_area",
    "disposal",
]

DEFAULT_PAIR = [
    Path.home() / "Downloads" / "op-snap---monthly-publication---march-2026---pdf.pdf",
    Path.home() / "Downloads" / "op-snap---monthly-publication---march-2026---excel(1).xlsx",
]


def load(path: Path) -> list[dict]:
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        sys.exit(f"No parser for {path.suffix} ({path})")
    rows = parser(path)
    if rows is None:
        sys.exit(f"Parser returned no rows for {path}")
    for r in rows:
        normalise_record(r)
    return rows


def _norm(v):
    """Treat None and empty string as equal for comparison purposes."""
    return (v or "").strip()


def field_agreement(a: list[dict], b: list[dict], field: str) -> tuple[int, list[int]]:
    """Count index-aligned matches for a field; return (matches, mismatch_indices)."""
    matches = 0
    mismatches = []
    for i in range(min(len(a), len(b))):
        if _norm(a[i].get(field)) == _norm(b[i].get(field)):
            matches += 1
        else:
            mismatches.append(i)
    return matches, mismatches


def print_field_table(label: str, a, b, fields, a_name, b_name):
    n = min(len(a), len(b))
    print(f"\n{label} (index-aligned over {n} rows)")
    print(f"  {'field':<26} {'match':>7} {'rate':>7}  example divergence")
    for field in fields:
        matches, mismatches = field_agreement(a, b, field)
        rate = matches / n * 100 if n else 0.0
        example = ""
        if mismatches:
            i = mismatches[0]
            example = f"row {i}: {a_name}={a[i].get(field)!r}  {b_name}={b[i].get(field)!r}"
        flag = "" if not mismatches else "  <-- differs"
        print(f"  {field:<26} {matches:>7} {rate:>6.2f}%  {example}{flag}")


def value_set_diff(a, b, field, a_name, b_name):
    ca, cb = Counter(_norm(r.get(field)) for r in a), Counter(_norm(r.get(field)) for r in b)
    only_a = set(ca) - set(cb)
    only_b = set(cb) - set(ca)
    if only_a or only_b:
        print(f"\n  {field}: distinct values differ")
        for v in sorted(only_a):
            print(f"    only in {a_name} ({ca[v]}x): {v!r}")
        for v in sorted(only_b):
            print(f"    only in {b_name} ({cb[v]}x): {v!r}")


def main():
    args = sys.argv[1:]
    paths = [Path(p) for p in args] if len(args) == 2 else list(DEFAULT_PAIR)

    for p in paths:
        if not p.exists():
            sys.exit(f"File not found: {p}")

    # Order as (pdf, xlsx) regardless of argument order, for stable labelling.
    paths.sort(key=lambda p: p.suffix.lower() != ".pdf")
    pdf_path, xlsx_path = paths
    pdf_name, xlsx_name = "pdf", "xlsx"

    print(f"PDF : {pdf_path.name}  (month {extract_month_year(pdf_path.name)})")
    print(f"XLSX: {xlsx_path.name}  (month {extract_month_year(xlsx_path.name)})")

    pdf_rows = load(pdf_path)
    xlsx_rows = load(xlsx_path)

    print("\n=== Row counts ===")
    print(f"  pdf : {len(pdf_rows)}")
    print(f"  xlsx: {len(xlsx_rows)}")
    if len(pdf_rows) != len(xlsx_rows):
        print("  WARNING: row counts differ — index alignment below is best-effort")

    print("\n=== RAW field agreement (as extracted, before normalisation) ===")
    print_field_table("Raw", pdf_rows, xlsx_rows,
                       [f + "_raw" if f in ("vehicle_make", "offence_location", "council_area", "disposal")
                        else f for f in RAW_FIELDS],
                       pdf_name, xlsx_name)

    print("\n=== NORMALISED field agreement (post-pipeline) ===")
    print_field_table("Normalised", pdf_rows, xlsx_rows, NORMALISED_FIELDS, pdf_name, xlsx_name)

    print("\n=== Value-set differences (normalised) ===")
    for field in ["disposal", "council_area", "offence", "reporter_transport_mode"]:
        value_set_diff(pdf_rows, xlsx_rows, field, pdf_name, xlsx_name)

    # Whole-row exact match (normalised, shared fields only)
    n = min(len(pdf_rows), len(xlsx_rows))
    exact = 0
    first_divergent = None
    for i in range(n):
        same = all(_norm(pdf_rows[i].get(f)) == _norm(xlsx_rows[i].get(f)) for f in RAW_FIELDS)
        if same:
            exact += 1
        elif first_divergent is None:
            first_divergent = i
    print("\n=== Whole-row agreement (normalised, shared fields) ===")
    print(f"  identical rows: {exact}/{n} ({exact / n * 100:.2f}%)" if n else "  no rows")
    if first_divergent is not None:
        i = first_divergent
        print(f"  first divergent row {i}:")
        for f in RAW_FIELDS:
            pv, xv = pdf_rows[i].get(f), xlsx_rows[i].get(f)
            if _norm(pv) != _norm(xv):
                print(f"    {f}: pdf={pv!r}  xlsx={xv!r}")


if __name__ == "__main__":
    main()
