# Disc Goblin

**Automatic Blu-ray ingest without automatic library chaos.**

Disc Goblin watches every MakeMKV-visible optical drive, starts ripping as soon
as a disc is inserted, and publishes the result into naming layouts understood
by Plex, Jellyfin, Emby, Sonarr, and Radarr.

The important safety rule is simple: **rip first, publish second**. A disc begins
ripping to a hidden staging directory immediately. Disc Goblin only moves it
into the watched media tree when metadata confidence is high, or after a fast
title/year confirmation in the dashboard. It never guesses low-confidence
metadata directly into the library.

## What works

- Multiple concurrently connected Blu-ray/DVD drives.
- Linux udev hotplug discovery reconciled against MakeMKV's own drive indexes,
  with polling as a fallback.
- Smart title selection:
  - longest title for a normal movie disc;
  - similarly sized episode titles for an episodic disc;
  - configurable `main_feature`, `smart`, or `all` mode.
- Optional TMDB matching for high-confidence automatic movie naming.
- Plex/Jellyfin movie layout:

  ```text
  Movies/Dune Part Two (2024)/Dune Part Two (2024).mkv
  ```

- Plex/Jellyfin TV layout:

  ```text
  TV/Show Name (2024)/Season 01/Show Name - S01E01.mkv
  ```

- Plex edition tags and an `Extras` folder for secondary selected titles.
- PostgreSQL 17 history and state managed through SQLAlchemy 2 and Alembic
  migrations.
- Per-drive firmware, LibreDrive, raw-BD, and UHD readiness auditing.
- Manifest-gated firmware flashing with exact hardware matching, SHA-256
  verification, empty-tray/idle checks, explicit confirmation, and post-flash
  version verification.
- Per-title details, progress, errors, retry, cancel, and eject.
- Collision protection: an existing library file is never overwritten.
- Disc fingerprinting and a duplicate-completion warning.
- Responsive real-time dashboard over WebSockets.
- Docker image layered on the pinned, packaged `jlesage/makemkv` appliance.
- Hardware-free simulation mode for development and demos.

## Quick start

Linux + Docker:

```sh
cp .env.example .env
```

Set `DISC_GOBLIN_LIBRARY_HOST_PATH` and a strong `POSTGRES_PASSWORD` in `.env`,
then:

```sh
docker compose up -d --build
```

Open `http://localhost:8080`.

The default Compose file is privileged so MakeMKV can discover all current and
hot-added optical/SCSI devices. A fixed-device, least-privilege example is
included in [`compose.devices.example.yaml`](compose.devices.example.yaml).
Read [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) before deploying against a real
media share.

## Local development

Python 3.12+:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d postgres
export DISC_GOBLIN_SIMULATE=true
export DISC_GOBLIN_LIBRARY_ROOT=./library
export DISC_GOBLIN_DATABASE_URL=postgresql+psycopg://disc_goblin:change-me@localhost:5432/disc_goblin
alembic upgrade head
disc-goblin
```

On Windows PowerShell:

```powershell
$env:DISC_GOBLIN_SIMULATE = "true"
$env:DISC_GOBLIN_LIBRARY_ROOT = ".\library"
$env:DISC_GOBLIN_DATABASE_URL = "postgresql+psycopg://disc_goblin:change-me@localhost:5432/disc_goblin"
alembic upgrade head
disc-goblin
```

Run checks:

```sh
pytest
ruff check .
```

## API

Interactive API documentation is available at `/api/docs`. Core endpoints:

- `GET /api/overview`
- `GET /api/jobs/{id}`
- `POST /api/jobs/{id}/metadata`
- `POST /api/jobs/{id}/retry`
- `POST /api/jobs/{id}/cancel`
- `POST /api/drives/{id}/rip`
- `POST /api/drives/{id}/eject`
- `POST /api/drives/{id}/firmware/audit`
- `POST /api/drives/{id}/firmware/flash`
- `WS /api/ws`

## Configuration

All settings use environment variables documented in [`.env.example`](.env.example).
Important knobs:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DISC_GOBLIN_LIBRARY_ROOT` | `/media/library` | Final library and same-filesystem staging root |
| `DISC_GOBLIN_MOVIE_ROOT` | `/media/library/Movies` | Plex/Jellyfin movie destination |
| `DISC_GOBLIN_TV_ROOT` | `/media/library/TV` | Plex/Jellyfin television destination |
| `DISC_GOBLIN_DATABASE_URL` | PostgreSQL DSN | Durable app state |
| `DISC_GOBLIN_RIP_MODE` | `smart` | `smart`, `main_feature`, or `all` |
| `DISC_GOBLIN_MIN_TITLE_SECONDS` | `1200` | Ignore short menus/trailers in automatic selection |
| `DISC_GOBLIN_AUTO_PUBLISH_CONFIDENCE` | `0.88` | Metadata threshold for unattended publishing |
| `DISC_GOBLIN_TMDB_TOKEN` | empty | Optional TMDB v4 read token |
| `DISC_GOBLIN_MAX_CONCURRENT_RIPS` | `2` | Concurrent drives allowed to rip |
| `DISC_GOBLIN_UDEV_DISCOVERY` | `true` | Trigger immediate discovery on Linux hotplug events |
| `DISC_GOBLIN_FIRMWARE_AUDIT` | `true` | Collect read-only LibreDrive/UHD firmware state |
| `DISC_GOBLIN_AUTO_FLASH` | `false` | Permit double-opt-in auto-flash profiles |
| `DISC_GOBLIN_SIMULATE` | `false` | Use two fake drives and a tiny fake rip |

## Firmware safety model

Firmware auditing is read-only and enabled by default. Flashing is not.

Disc Goblin will only expose a flash action when a local manifest exactly
matches manufacturer, product, drive platform, current revision, and firmware
date; the payload lives below `/config/firmware`; and its SHA-256 matches the
manifest. It also requires an idle drive with an empty tray and verifies the
reported firmware version afterward.

Automatic flashing adds two more gates:

1. `DISC_GOBLIN_AUTO_FLASH=true`
2. the exact profile contains `auto_approved: true`

Pioneer drives are always audit-only in this release. Their model-family and
post-2022 firmware rules are too risky for generic unattended crossflashing.
Start from [`config/firmware/manifest.example.yaml`](config/firmware/manifest.example.yaml)
when intentionally onboarding an LG/ASUS MT1959 firmware path.

## Operational boundaries

- Disc Goblin remuxes tracks through MakeMKV; it does not transcode video.
- Correct metadata cannot be guaranteed from every Blu-ray label. The staging
  gate is how the app guarantees it will not knowingly publish a bad guess.
- TV episode ordering still needs a season/first-episode confirmation unless a
  future metadata provider can identify the physical disc unambiguously.
- Use Disc Goblin only for media you are legally permitted to copy in your
  jurisdiction.
- MakeMKV is separate software with its own license and beta-key requirements.
- LibreDrive `Status: Enabled` is a capability report; a real disc open is the
  final proof that LibreDrive engaged and that a particular UHD disc is readable.

## License

Disc Goblin is MIT licensed. The packaged MakeMKV runtime remains separate
software and is not covered by this license.
