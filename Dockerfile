FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir datasette datasette-cluster-map datasette-block-robots

COPY data/opsnap-deploy.db data/opsnap.db
COPY metadata.json .
COPY templates/ templates/
COPY static/ static/

EXPOSE 8001

CMD ["datasette", "-i", "data/opsnap.db", "-m", "metadata.json", "--template-dir", "templates", "--static", "static:static", "-h", "0.0.0.0", "-p", "8001", "--setting", "sql_time_limit_ms", "5000", "--setting", "max_returned_rows", "30000", "--setting", "suggest_facets", "off", "--setting", "allow_facet", "off", "--cors"]
