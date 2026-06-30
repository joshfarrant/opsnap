FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir datasette datasette-cluster-map

COPY data/opsnap-deploy.db data/opsnap.db
COPY metadata.json .
COPY templates/ templates/
COPY static/ static/

EXPOSE 8001

CMD ["datasette", "-i", "data/opsnap.db", "-m", "metadata.json", "--template-dir", "templates", "--static", "static:static", "-h", "0.0.0.0", "-p", "8001", "--setting", "sql_time_limit_ms", "10000", "--setting", "max_returned_rows", "50000", "--setting", "default_page_size", "1000", "--cors"]
