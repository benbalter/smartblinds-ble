"""CLI: scan for shade motors and brute-force their keys.

Successor to pysmartblinds' examples/search.py, on bleak. Run with no args to
discover + keyscan all nearby motors, or pass one or more MAC addresses.

    $ smartblinds-find-key
    $ smartblinds-find-key AA:BB:CC:DD:EE:FF

⚠️  Requires a local BLE adapter and physically-nearby motors. This is a bring-up
    / Milestone-0 tool; day-to-day control goes through Home Assistant.
"""

from __future__ import annotations

import asyncio
import sys

from bleak import BleakScanner

from ..blind import SmartBlind
from ..exceptions import KeyNotFound
from ..scanner import discover


async def _keyscan_address(address: str) -> None:
    print(f"[{address}] locating device...", file=sys.stderr)
    device = await BleakScanner.find_device_by_address(address, timeout=10.0)
    if device is None:
        print(f"[{address}] not found", file=sys.stderr)
        return
    await _keyscan_device(device)


async def _keyscan_device(device) -> None:
    blind = SmartBlind(device)
    print(f"[{device.address}] scanning key 0x00..0xFF (motor will tilt fully)...",
          file=sys.stderr)
    try:
        key = await blind.keyscan()
    except KeyNotFound:
        print(f"[{device.address}] keyscan failed", file=sys.stderr)
        return
    print(f"{device.address} = {key.hex()}")


async def _main() -> None:
    addresses = sys.argv[1:]
    if addresses:
        for addr in addresses:
            await _keyscan_address(addr)
        return
    print("Scanning for shade motors...", file=sys.stderr)
    devices = await discover()
    if not devices:
        print("no motors detected", file=sys.stderr)
        return
    for device in devices:
        await _keyscan_device(device)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
