from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator


def optical_media_labels() -> dict[str, str]:
    """Return loaded optical media labels keyed by /dev/sr* device path."""
    if os.name == "nt":
        return {}

    try:
        import pyudev

        context = pyudev.Context()
    except (ImportError, OSError):
        return {}

    labels: dict[str, str] = {}
    for device in context.list_devices(subsystem="block"):
        name = device.device_node or ""
        if not name.startswith("/dev/sr"):
            continue
        label = str(device.get("ID_FS_LABEL", "")).strip()
        if label:
            labels[name] = label
    return labels


async def optical_hotplug_events() -> AsyncIterator[str]:
    """Yield Linux optical-device events; quietly idle on unsupported platforms."""
    if os.name == "nt":
        while True:
            await asyncio.sleep(3600)

    try:
        import pyudev

        context = pyudev.Context()
    except (ImportError, OSError):
        while True:
            await asyncio.sleep(3600)

    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="block")
    monitor.start()
    while True:
        device = await asyncio.to_thread(monitor.poll, 1)
        if device is None:
            await asyncio.sleep(0)
            continue
        name = device.get("DEVNAME", "")
        optical = (
            name.startswith("/dev/sr")
            or device.get("ID_CDROM") == "1"
            or device.get("ID_CDROM_MEDIA") == "1"
        )
        if optical:
            yield f"{device.action or 'change'}:{name}"
