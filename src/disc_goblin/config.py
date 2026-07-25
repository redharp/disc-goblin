from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    library_root: Path = Path("/media/library")
    movie_root: Path = Path("/media/library/Movies")
    tv_root: Path = Path("/media/library/TV")
    database_url: str = "postgresql+psycopg://disc_goblin:disc_goblin@localhost:5432/disc_goblin"
    poll_interval: float = 8.0
    auto_rip: bool = True
    eject_on_success: bool = True
    max_concurrent_rips: int = 2
    min_title_seconds: int = 1200
    auto_publish_confidence: float = 0.88
    rip_mode: str = "smart"
    tmdb_token: str | None = None
    makemkv_bin: str = "makemkvcon"
    makemkv_key: str | None = None
    udev_discovery: bool = True
    firmware_audit: bool = True
    auto_flash: bool = False
    firmware_manifest: Path = Path("/config/firmware/manifest.yaml")
    firmware_root: Path = Path("/config/firmware")
    sdf_path: Path = Path("/opt/makemkv/appdata/sdf.bin")
    simulate: bool = False

    @property
    def staging_root(self) -> Path:
        return self.library_root / ".disc-goblin-staging"

    @classmethod
    def from_env(cls) -> Settings:
        library_root = Path(os.getenv("DISC_GOBLIN_LIBRARY_ROOT", "/media/library")).expanduser()
        return cls(
            library_root=library_root,
            movie_root=Path(
                os.getenv(
                    "DISC_GOBLIN_MOVIE_ROOT",
                    str(library_root / "Movies"),
                )
            ).expanduser(),
            tv_root=Path(
                os.getenv(
                    "DISC_GOBLIN_TV_ROOT",
                    str(library_root / "TV"),
                )
            ).expanduser(),
            database_url=os.getenv(
                "DISC_GOBLIN_DATABASE_URL",
                "postgresql+psycopg://disc_goblin:disc_goblin@localhost:5432/disc_goblin",
            ),
            poll_interval=float(os.getenv("DISC_GOBLIN_POLL_INTERVAL", "8")),
            auto_rip=_bool("DISC_GOBLIN_AUTO_RIP", True),
            eject_on_success=_bool("DISC_GOBLIN_EJECT_ON_SUCCESS", True),
            max_concurrent_rips=max(1, int(os.getenv("DISC_GOBLIN_MAX_CONCURRENT_RIPS", "2"))),
            min_title_seconds=max(0, int(os.getenv("DISC_GOBLIN_MIN_TITLE_SECONDS", "1200"))),
            auto_publish_confidence=min(
                1.0,
                max(
                    0.0,
                    float(os.getenv("DISC_GOBLIN_AUTO_PUBLISH_CONFIDENCE", "0.88")),
                ),
            ),
            rip_mode=os.getenv("DISC_GOBLIN_RIP_MODE", "smart").strip().lower(),
            tmdb_token=os.getenv("DISC_GOBLIN_TMDB_TOKEN") or None,
            makemkv_bin=os.getenv("DISC_GOBLIN_MAKEMKV_BIN", "makemkvcon"),
            makemkv_key=os.getenv("DISC_GOBLIN_MAKEMKV_KEY") or None,
            udev_discovery=_bool("DISC_GOBLIN_UDEV_DISCOVERY", True),
            firmware_audit=_bool("DISC_GOBLIN_FIRMWARE_AUDIT", True),
            auto_flash=_bool("DISC_GOBLIN_AUTO_FLASH", False),
            firmware_manifest=Path(
                os.getenv(
                    "DISC_GOBLIN_FIRMWARE_MANIFEST",
                    "/config/firmware/manifest.yaml",
                )
            ).expanduser(),
            firmware_root=Path(
                os.getenv("DISC_GOBLIN_FIRMWARE_ROOT", "/config/firmware")
            ).expanduser(),
            sdf_path=Path(
                os.getenv("DISC_GOBLIN_SDF_PATH", "/opt/makemkv/appdata/sdf.bin")
            ).expanduser(),
            simulate=_bool("DISC_GOBLIN_SIMULATE", False),
        )
