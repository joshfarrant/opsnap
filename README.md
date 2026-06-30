# Op Snap — West Midlands

Parsing, geocoding, and visualising [West Midlands Police Operation Snap](https://www.westmidlands.police.uk/police-forces/west-midlands-police/areas/campaigns/campaigns/operation-snap/) data.

Operation Snap lets the public submit dashcam and photo evidence of driving offences. West Midlands Police publish monthly PDFs of all submissions and outcomes. This project turns those PDFs into structured, geocoded, queryable data.

**Live instance:** [opsnap.farrant.me](https://opsnap.farrant.me)

## What's here

```
data/pdfs/              Monthly publications from WM Police — PDFs (Jan 2025–) and xlsx (Mar 2026–)
data/opsnap-deploy.db   Pre-built SQLite database with geocoded data (used by Docker)
scripts/ingest.py       Parse PDFs and xlsx → SQLite
scripts/geocode.py      Geocode locations via Nominatim → lat/lng
scripts/build_deploy.py Build opsnap-deploy.db from the view DB (WM bounding-box filter)
scripts/compare_sources.py  Compare a PDF vs xlsx publication for the same month
scripts/clear_failed_geocodes.py  Clear failed cache entries for retry
metadata.json           Datasette config with canned queries and UI settings
Dockerfile              Production deployment
```

> West Midlands Police published their first machine-readable **xlsx** for the
> March 2026 publication, after three years of PDF-only releases. `ingest.py`
> handles both: drop whichever single format WMP provide for a month into
> `data/pdfs/`. A side-by-side parse of the March 2026 PDF and xlsx agreed on
> 2,252/2,252 rows after normalisation (`scripts/compare_sources.py`).

## Quick start

```bash
# Install dependencies
pip install pdfplumber openpyxl

# Ingest publications (PDF and/or xlsx) into SQLite
python scripts/ingest.py

# Geocode locations (cached and resumable; only new locations hit Nominatim)
python scripts/geocode.py

# Build the deployable DB (copies view DB, clears out-of-area geocodes)
python scripts/build_deploy.py

# Browse with Datasette
pip install datasette datasette-cluster-map
datasette -i data/opsnap.db -m metadata.json
```

## Data

~27,900 records across 15 months (Jan 2025 – Mar 2026). 78% geocoded onto a map.

| Field | Example |
|-------|---------|
| Reporter | Car, Pedestrian, Pedal Bike |
| Vehicle make/model/colour | BMW 3 Series Black |
| Offence | Driving without Due Care and Attention |
| Location | Washwood Heath Road |
| Council area | Birmingham |
| Outcome | Fixed Penalty, Education, Warning Letter, Court, NFA |

Vehicle registration data (DVLA, Q3 2025) is included for normalising offence rates per 100,000 registered vehicles.

## Key stats

- **65%** of submissions result in action (education, warning, fine, or court)
- **Washwood Heath Road** is the most-reported location (1,036 reports in 15 months)
- **Seat** has the highest offence rate per 100k registered vehicles (136.3), followed by Mercedes-Benz (119.2) and Toyota (111.5)
- **Ford** leads raw counts but drops to 9th when normalised against registrations

## Queries

The live instance includes canned queries for:

- 🗺️ All offences on a clustered map
- 🚶 Pavement parking hotspots (with map)
- 📍 Top reported locations
- 🚗 Vehicle makes — normalised per 100k registered
- 📊 Monthly trends
- ⚠️ Offence type breakdown
- 🏛️ Council area comparison
- 👁️ What different reporter types see

## Data sources

- Offence data: [West Midlands Police Operation Snap](https://www.westmidlands.police.uk/police-forces/west-midlands-police/areas/campaigns/campaigns/operation-snap/) monthly PDFs
- Geocoding: [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/)
- Vehicle registrations: [DVLA via howmanyleft.co.uk](https://howmanyleft.co.uk)
- Map tiles: [CARTO](https://carto.com/)

## Licence

Op Snap data is published by West Midlands Police. Location data © OpenStreetMap contributors, [ODbL](https://openstreetmap.org/copyright).
