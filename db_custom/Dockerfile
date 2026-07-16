FROM pgvector/pgvector:pg14

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgis \
    postgresql-14-postgis-3 \
    postgresql-14-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*