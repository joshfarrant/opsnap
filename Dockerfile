FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir datasette datasette-cluster-map

COPY data/opsnap-deploy.db data/opsnap.db
COPY metadata.json .

EXPOSE 8001

CMD ["datasette", "data/opsnap.db", "-i", "-m", "metadata.json", "-h", "0.0.0.0", "-p", "8001", "--setting", "sql_time_limit_ms", "5000", "--cors"]
