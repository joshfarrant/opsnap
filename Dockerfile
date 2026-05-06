FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir datasette datasette-cluster-map pdfplumber

COPY data/pdfs/ data/pdfs/
COPY scripts/ scripts/
COPY metadata.json .

# Run ingestion at build time so the db is baked into the image
RUN python scripts/ingest.py

EXPOSE 8001

CMD ["datasette", "data/opsnap.db", "-m", "metadata.json", "-h", "0.0.0.0", "-p", "8001", "--setting", "sql_time_limit_ms", "5000", "--cors"]
