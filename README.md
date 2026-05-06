# Op Snap — West Midlands

Parsing, geocoding, and visualising [West Midlands Police Operation Snap](https://www.westmidlands.police.uk/police-forces/west-midlands-police/areas/campaigns/campaigns/operation-snap/) data.

Operation Snap lets the public submit dashcam and photo evidence of driving offences. West Midlands Police publish monthly PDFs of all submissions and outcomes. This project turns those PDFs into structured, geocoded, queryable data.

**Live instance:** [opsnap.farrant.me](https://opsnap.farrant.me)

## What's here

```
data/pdfs/              Monthly PDFs from WM Police (Jan 2025 – Feb 2026)
data/opsnap-deploy.db   Pre-built SQLite database with geocoded data (used by Docker)
scripts/ingest.py       Parse PDFs → SQLite
scripts/geocode.py      Geocode locations via Nominatim → lat/lng
scripts/clear_failed_geocodes.py  Clear failed cache entries for retry
metadata.json           Datasette config with canned queries and UI settings
Dockerfile              Production deployment
```

## Quick start

```bash
# Install dependencies
pip install pdfplumber

# Ingest PDFs into SQLite
python scripts/ingest.py

# Geocode locations (~3 hours first run, cached and resumable)
python scripts/geocode.py

# Browse with Datasette
pip install datasette datasette-cluster-map
datasette -i data/opsnap.db -m metadata.json
```

## Data

~25,600 records across 14 months (Jan 2025 – Feb 2026). 79% geocoded onto a map.

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

- **71%** of submissions result in action (education, warning, fine, or court)
- **Washwood Heath Road** is the most-reported location (923 reports in 14 months)
- **Seat** has the highest offence rate per 100k registered vehicles (122.8), followed by Mercedes-Benz (108.3) and Toyota (102.6)
- **Ford** leads raw counts but drops to 10th when normalised against registrations

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
