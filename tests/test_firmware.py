import hashlib
from pathlib import Path

from disc_goblin.firmware import FirmwareManifest, parse_firmware_info

LG_INFO = """
Drive Information
OS device name: /dev/sr0
Manufacturer: HL-DT-ST
Product: BD-RE WH16NS40
Revision: 1.05
Serial number: KLIJ123456
Firmware date: 2120-05-06 11:42
Bus encryption flags: 17

LibreDrive Information
Status: Possible, not yet enabled
Drive platform: MT1959
Firmware type: Original (unpatched)
Firmware version: 1.05
DVD all regions: Possible
BD raw data read: Possible
BD raw metadata read: Possible
Unrestricted read speed: Possible
"""

PIONEER_INFO = """
Drive Information
Manufacturer: PIONEER
Product: BD-RW BDR-XD08
Revision: 1.02
Firmware date: 2022-12-27

LibreDrive Information
Status: Enabled
Drive platform: RS9330
Firmware type: Original (unpatched)
Firmware version: 1.02
BD raw data read: Yes
BD raw metadata read: Yes
"""

SDF_TOOL_INFO = """
[Drive Specific SDF] Embedded Info Strings:
8000:LibreDrive Information
8013:Status
8105:Enabled
8001:Drive platform
:MT1959
8002:Firmware type
8107:Patched (microcode access re-enabled)
8003:Firmware version
:1.03
8006:BD raw data read
8100:Yes
8007:BD raw metadata read
8100:Yes
8009:Unrestricted read speed
8100:Yes

[Identification SDF] Embedded Info Strings:
8000:LibreDrive Information
8013:Status
8102:Possible, not yet enabled
8001:Drive platform
:MT1959
"""


def test_parse_firmware_and_classify_flash_possible() -> None:
    info = parse_firmware_info(LG_INFO)
    assert info.platform == "MT1959"
    assert info.libredrive_status == "Possible, not yet enabled"
    assert info.uhd_status == "flash_possible"


def test_non_uhd_pioneer_is_never_generic_flash_candidate() -> None:
    info = parse_firmware_info(PIONEER_INFO)
    assert info.uhd_status == "audit_only"


def test_parse_firmware_tool_prefers_drive_specific_sdf() -> None:
    info = parse_firmware_info(
        SDF_TOOL_INFO,
        manufacturer="HL-DT-ST",
        product="BD-RE BU40N",
        revision="1.03",
    )
    assert info.platform == "MT1959"
    assert info.firmware_version == "1.03"
    assert info.libredrive_status == "Enabled"
    assert info.bd_raw_data_read is True
    assert info.uhd_status == "ready"


def test_manifest_requires_exact_identity_and_payload_hash(tmp_path: Path) -> None:
    firmware_root = tmp_path / "firmware"
    payload = firmware_root / "payloads" / "approved.bin"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"verified firmware fixture")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    manifest_path = firmware_root / "manifest.yaml"
    manifest_path.write_text(
        f"""
version: 1
profiles:
  - id: fixture-lg
    manufacturer: HL-DT-ST
    product_regex: "^BD-RE WH16NS40$"
    platform: MT1959
    revision_regex: "^1\\\\.05$"
    firmware_date_regex: "^2120-05-06 11:42$"
    image: payloads/approved.bin
    sha256: "{digest}"
    target_version: "1.02"
    flash_mode: main
    encrypted: true
    auto_approved: false
""",
        encoding="utf-8",
    )
    manifest = FirmwareManifest(manifest_path, firmware_root)
    info = parse_firmware_info(LG_INFO)
    profile = manifest.match(info)
    assert profile is not None
    assert profile.id == "fixture-lg"
    assert manifest.validate_image(profile) == payload


def test_pioneer_cannot_match_even_a_malicious_manifest(tmp_path: Path) -> None:
    firmware_root = tmp_path / "firmware"
    payload = firmware_root / "payload.bin"
    firmware_root.mkdir()
    payload.write_bytes(b"do not flash")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    manifest_path = firmware_root / "manifest.yaml"
    manifest_path.write_text(
        f"""
version: 1
profiles:
  - id: forbidden-pioneer
    manufacturer: PIONEER
    product_regex: ".*"
    platform: RS9330
    revision_regex: ".*"
    firmware_date_regex: ".*"
    image: payload.bin
    sha256: "{digest}"
    target_version: "1.99"
""",
        encoding="utf-8",
    )
    manifest = FirmwareManifest(manifest_path, firmware_root)
    assert manifest.match(parse_firmware_info(PIONEER_INFO)) is None
