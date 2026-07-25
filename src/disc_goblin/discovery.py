from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator


async def optical_hotplug_events() -> AsyncIterator[str]:
    """Yield Linux optical-device events; quietly idle on unsupported platforms."""
    if os.name == "nt":
        while True:
            await asyncio.sleep(3600)

    try:
        import pyudev
    except ImportError:
        while True:
            await asyncio.sleep(3600)

    context = pyudev.Context()
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
