# Deployment

Disc Goblin is a Linux Docker appliance. The container needs:

- the optical drive's `/dev/sr*` block device;
- the matching `/dev/sg*` SCSI generic device used by MakeMKV;
- a writable host directory or mounted network share for `/media/library`;
- persistent `/config` storage for firmware manifests and payloads;
- PostgreSQL 17 for history, device state, jobs, and events;
- a valid MakeMKV beta or paid key when MakeMKV requires one.

## 1. Find the drive pairs

Install `lsscsi` on the Docker host and run:

```sh
lsscsi -g
```

Example:

```text
[5:0:0:0] cd/dvd PIONEER BD-RW BDR-212U 1.02 /dev/sr0 /dev/sg1
```

The default `compose.yaml` uses `privileged: true` because it is the most
reliable option for a multi-drive appliance and lets hot-added drives appear
without recreating the container. It bind-mounts `/dev` and `/run/udev` so
device nodes and hotplug events stay current. That grants broad host device
access.

For a fixed, tighter device list:

```sh
docker compose -f compose.yaml -f compose.devices.example.yaml up -d --build
```

Edit `compose.devices.example.yaml` first so every `/dev/sr*` device is paired
with the correct `/dev/sg*` device. For a genuinely strict deployment, also
remove the default `/dev:/dev` bind; the fixed-device mode then falls back to
periodic MakeMKV reconciliation instead of open-ended hotplug discovery.

## 2. Mount the destination on the host

Mount NFS or SMB on the Docker host, not inside the container. Confirm the
mount is writable before starting Disc Goblin:

```sh
touch /path/to/media/.disc-goblin-write-test
rm /path/to/media/.disc-goblin-write-test
```

Point `DISC_GOBLIN_LIBRARY_HOST_PATH` at that host path. Staging is kept below
the library root at `.disc-goblin-staging`, so publishing is normally an atomic
rename on the same filesystem.

For the current proxius home lab, do **not** map either of these existing
`fr0gz9ripper` mounts as the write target:

- `/mnt/proxius/media` — read-only;
- `/mnt/proxius/rips` — read-only recovery media.

Use a deliberately writable export. The already-writable
`/mnt/proxius/toshiba` mount is suitable for an inbox, or create a writable
export backed by the managed `/srv/content/media` tree on `big-nazty` if the
files should land directly in Jellyfin's managed libraries.

## 3. Configure PostgreSQL and start

```sh
cp .env.example .env
```

Set at least:

```dotenv
DISC_GOBLIN_LIBRARY_HOST_PATH=/path/to/writable/media
DISC_GOBLIN_MAKEMKV_KEY=your-current-key
DISC_GOBLIN_TMDB_TOKEN=your-optional-tmdb-v4-read-token
POSTGRES_PASSWORD=replace-this-with-a-long-random-password
```

Then:

```sh
docker compose up -d --build
docker compose logs -f disc-goblin
```

Open `http://DOCKER-HOST:8080`.

The application container waits for PostgreSQL health and applies Alembic
migrations before the API starts.

The TMDB token is optional. Without it, Disc Goblin still detects and rips a
disc immediately, ejects it after the data is safe, and then asks for a
title/year confirmation before publishing. This is deliberate: a disc volume
label alone is not reliable enough to promise correct library placement.

## 4. Reverse proxy and access

Disc Goblin currently has no built-in user accounts. Keep port 8080 on a trusted
LAN, or put it behind the existing authenticated/access-listed reverse proxy.
Do not expose it directly to the public internet.

## 5. Update MakeMKV

The MakeMKV runtime comes from the tag-and-digest-pinned
`jlesage/makemkv` base in `Dockerfile`. To upgrade, review a published image,
replace both its tag and digest in `Dockerfile`, then rebuild:

```sh
docker compose build --no-cache
docker compose up -d
```

MakeMKV beta builds are time-limited. A paid key avoids beta expiration; a
current beta key also works while valid.

## 6. Firmware audit and optional flashing

Every detected drive is audited with MakeMKV's firmware interface. The
dashboard reports its platform, firmware version, LibreDrive status, and a
conservative UHD readiness classification.

Flashing remains unavailable until you:

1. obtain the correct payload from a source you trust;
2. save it below `config/firmware/payloads/`;
3. copy `config/firmware/manifest.example.yaml` to
   `config/firmware/manifest.yaml`;
4. replace every matcher with the exact read-only audit values from that drive;
5. calculate and paste the payload SHA-256;
6. keep `auto_approved: false` for the first manual, attended flash.

The flasher refuses a non-matching model/platform/revision/date, a missing or
hash-mismatched payload, a drive with media inserted, or an active rip. It then
re-audits the drive and requires the configured target version.

Pioneer is audit-only. Current MakeMKV community guidance distinguishes genuine
UHD Pioneer models from non-UHD siblings and warns that many newer firmwares
cannot be generally crossflashed. Disc Goblin does not try to automate those
private/model-specific paths.

For an LG/ASUS profile that has already been proven on the exact drive variant,
automatic flashing can be enabled only by setting both:

```dotenv
DISC_GOBLIN_AUTO_FLASH=true
```

and:

```yaml
auto_approved: true
```

This is intentionally a double opt-in. Use stable power and do not restart,
unplug, or open the tray while a flash is in progress.

## 7. Simulation mode

To exercise the entire UI without optical hardware:

```sh
DISC_GOBLIN_SIMULATE=true docker compose up -d --build
```

Simulation writes a tiny placeholder file, never a real video.
