# syntax=docker/dockerfile:1.7
FROM jlesage/makemkv:v26.07.2@sha256:0b81851803e805cb1ac1428c790f18813697417d507a93db6945c1ac30378bc3 AS makemkv

FROM python:3.12-alpine3.22
LABEL org.opencontainers.image.title="Disc Goblin"
LABEL org.opencontainers.image.description="Automatic MakeMKV ingest for Plex and Jellyfin"
LABEL org.opencontainers.image.version="0.1.0"

COPY --from=makemkv /opt/makemkv /opt/makemkv

RUN apk add --no-cache \
      eudev-libs \
      util-linux-misc \
    && mkdir -p /opt/makemkv/appdata \
    && tar -xf /opt/makemkv/share/MakeMKV/appdata.tar -C /opt/makemkv/appdata \
    && ln -s "$(find /opt/makemkv/appdata -name 'sdf_*.bin' -print -quit)" \
      /opt/makemkv/appdata/sdf.bin

WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN pip install --no-cache-dir . \
    && mkdir -p /config /media/library \
    && chmod 0775 /config /media/library

COPY docker/entrypoint.sh /usr/local/bin/disc-goblin-entrypoint
RUN chmod +x /usr/local/bin/disc-goblin-entrypoint

ENV HOME=/config \
    PATH="/opt/makemkv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DISC_GOBLIN_DATABASE_URL=postgresql+psycopg://disc_goblin:disc_goblin@postgres:5432/disc_goblin \
    DISC_GOBLIN_LIBRARY_ROOT=/media/library \
    DISC_GOBLIN_MAKEMKV_BIN=/opt/makemkv/bin/makemkvcon \
    DISC_GOBLIN_SDF_PATH=/opt/makemkv/appdata/sdf.bin

VOLUME ["/config", "/media/library"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=4s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
ENTRYPOINT ["disc-goblin-entrypoint"]
CMD ["disc-goblin"]
