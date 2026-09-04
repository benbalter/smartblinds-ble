"""Discovery helpers for MySmartBlinds/Tilt motors."""

from __future__ import annotations

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from . import const


async def discover(timeout: float = 10.0) -> list[BLEDevice]:
    """Scan for shade motors, returning bleak ``BLEDevice`` objects.

    Filters on the advertised device name. In Home Assistant you would instead
    let the Bluetooth integration surface these (including via ESPHome proxies)
    rather than scanning directly.
    """
    devices = await BleakScanner.discover(timeout=timeout)
    return [d for d in devices if (d.name or "") == const.DEVICE_NAME]
