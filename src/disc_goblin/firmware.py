from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

KNOWN_UHD_PRODUCTS = {
    "BP60NB10",
    "BP50NB40",
    "WP50NB40",
    "WH16NS60",
    "BU40N",
    "WH14NS40",
    "WH16NS40",
    "BW-16D1HT",
    "BW-16D1HT PRO",
    "BH16NS55",
    "BRUHD-PU3",
    "BDR-XD08UMB-S",
    "BDR-XD07UHD",
    "BDR-XD06JUHD",
    "BDR-S12UHT",
    "BDR-XS07UHD",
    "BDR-212UBK",
    "BDR-211UBK",
    "BDR-UD04",
    "BDR-S13U-X",
    "BDR-S13UBK",
}


@dataclass(slots=True)
class FirmwareInfo:
    manufacturer: str = ""
    product: str = ""
    revision: str = ""
    serial: str = ""
    firmware_date: str = ""
    platform: str = ""
    firmware_type: str = ""
    firmware_version: str = ""
    libredrive_status: str = ""
    bd_raw_data_read: bool = False
    bd_raw_metadata_read: bool = False
    unrestricted_read_speed: bool = False
    uhd_status: str = "unknown"
    message: str = "Firmware information has not been audited yet"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FlashProfile:
    id: str
    manufacturer: str
    product_regex: str
    platform: str
    revision_regex: str
    firmware_date_regex: str
    image: str
    sha256: str
    target_version: str
    flash_mode: str = "main"
    encrypted: bool = False
    auto_approved: bool = False


def _yes(value: str) -> bool:
    return value.strip().casefold() == "yes"


def parse_firmware_info(output: str) -> FirmwareInfo:
    values: dict[str, str] = {}
    libre_values: dict[str, str] = {}
    in_libredrive = False
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.casefold().startswith("libredrive information"):
            in_libredrive = True
            continue
        if line.casefold().startswith(("disc information", "no disc inserted")):
            in_libredrive = False
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        target = libre_values if in_libredrive else values
        target[key.casefold()] = value

    info = FirmwareInfo(
        manufacturer=values.get("manufacturer", ""),
        product=values.get("product", ""),
        revision=values.get("revision", ""),
        serial=values.get("serial number", ""),
        firmware_date=values.get("firmware date", ""),
        platform=libre_values.get("drive platform", ""),
        firmware_type=libre_values.get("firmware type", ""),
        firmware_version=libre_values.get("firmware version", ""),
        libredrive_status=libre_values.get("status", ""),
        bd_raw_data_read=_yes(libre_values.get("bd raw data read", "")),
        bd_raw_metadata_read=_yes(libre_values.get("bd raw metadata read", "")),
        unrestricted_read_speed=_yes(libre_values.get("unrestricted read speed", "")),
    )
    info.uhd_status, info.message = classify_uhd(info)
    return info


def classify_uhd(info: FirmwareInfo) -> tuple[str, str]:
    product = info.product.upper()
    known = any(model in product for model in KNOWN_UHD_PRODUCTS)
    enabled = "enabled" in info.libredrive_status.casefold()
    possible = "possible" in info.libredrive_status.casefold()
    pioneer = "PIONEER" in info.manufacturer.upper() or product.startswith("BDR-")
    if known and enabled and info.bd_raw_data_read:
        return "ready", "LibreDrive reports raw BD access on a known UHD-capable model"
    if known and (possible or info.platform == "MT1959"):
        return "flash_possible", "Known UHD-capable hardware may need an approved firmware"
    if pioneer:
        return (
            "audit_only",
            "Pioneer firmware is audit-only; Disc Goblin will not auto-crossflash it",
        )
    if info.platform == "MT1959":
        return (
            "review_required",
            "MT1959 detected, but the exact model and service code need an allowlisted profile",
        )
    if info.product:
        return "unsupported", "No verified UHD firmware path is configured for this drive"
    return "unknown", "MakeMKV did not return enough firmware information"


class FirmwareManifest:
    def __init__(self, path: Path, firmware_root: Path):
        self.path = path
        self.firmware_root = firmware_root.resolve()
        self.profiles: list[FlashProfile] = []

    def load(self) -> None:
        self.profiles = []
        if not self.path.exists():
            return
        payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if payload.get("version") != 1:
            raise ValueError("Firmware manifest version must be 1")
        for item in payload.get("profiles", []):
            profile = FlashProfile(**item)
            if profile.flash_mode not in {"main", "full"}:
                raise ValueError(f"Unsupported flash mode in profile {profile.id}")
            if not re.fullmatch(r"[a-fA-F0-9]{64}", profile.sha256):
                raise ValueError(f"Invalid SHA-256 in profile {profile.id}")
            self.profiles.append(profile)

    def match(self, info: FirmwareInfo) -> FlashProfile | None:
        self.load()
        if "PIONEER" in info.manufacturer.upper() or info.product.upper().startswith("BDR-"):
            return None
        for profile in self.profiles:
            if profile.manufacturer.casefold() != info.manufacturer.casefold():
                continue
            if profile.platform != info.platform:
                continue
            if not re.fullmatch(profile.product_regex, info.product, re.IGNORECASE):
                continue
            if not re.fullmatch(profile.revision_regex, info.revision, re.IGNORECASE):
                continue
            if not re.fullmatch(profile.firmware_date_regex, info.firmware_date, re.IGNORECASE):
                continue
            return profile
        return None

    def image_path(self, profile: FlashProfile) -> Path:
        candidate = (self.firmware_root / profile.image).resolve()
        if self.firmware_root not in candidate.parents:
            raise ValueError("Firmware image must stay below the configured firmware root")
        return candidate

    def validate_image(self, profile: FlashProfile) -> Path:
        image = self.image_path(profile)
        if not image.is_file():
            raise FileNotFoundError(f"Firmware image is missing: {profile.image}")
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        if digest.casefold() != profile.sha256.casefold():
            raise ValueError(f"Firmware SHA-256 mismatch for profile {profile.id}")
        return image
