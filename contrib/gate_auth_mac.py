#!/usr/bin/env python3
"""Gate check: prove rescued Tilt pairing keys still authenticate, in range.

Run this on a machine physically near the shades (e.g. a Mac in the room). It
scans for advertising Tilt roller shades ("RollerSh..."), opens the real
encrypted session to each, and reports which rescued pairing key authenticates
it -- read-only. No position is ever written; nothing moves.

    python contrib/gate_auth_mac.py --key-dir ./keys
    python contrib/gate_auth_mac.py --keys-json ./keys.json

--key-dir  : a directory of "<name>.key" files, each 64 hex chars (the format the
             Tilt bridge stores keys in).
--keys-json: a JSON file mapping {"office_left": "<64 hex>", ...}.

macOS hides BLE MACs behind per-host UUIDs, so shades are matched to keys by the
handshake, not by address -- which also catches a shade whose static address
drifted after a battery brownout (the rescued MAC would be stale, but the key
still works).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from smartblinds_ble.tilt.ble import TiltShadeClient
from smartblinds_ble.tilt.protocol import AuthenticationError, TiltProtocolError

_LOGGER = logging.getLogger("tilt-gate")
_SHADE_NAME_PREFIX = "RollerSh"
_HEX = set("0123456789abcdefABCDEF")


def _parse_key(name: str, value: str) -> bytes:
    value = value.strip()
    if len(value) != 64 or any(character not in _HEX for character in value):
        raise SystemExit(f"Key {name!r} must be exactly 64 hex characters.")
    return bytes.fromhex(value)


def _load_keys(key_dir: str | None, keys_json: str | None) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    if keys_json:
        raw = json.loads(Path(keys_json).read_text(encoding="utf-8"))
        keys.update({name: _parse_key(name, value) for name, value in raw.items()})
    if key_dir:
        for path in sorted(Path(key_dir).glob("*.key")):
            keys[path.stem] = _parse_key(path.stem, path.read_text(encoding="ascii"))
    if not keys:
        raise SystemExit("No keys loaded: pass --key-dir or --keys-json.")
    return keys


async def _probe(device, address, keys, *, ack_timeout, response_timeout):
    """Try each key against one shade (read-only). Return (name, status) or (None, None)."""

    def factory(_address, *, timeout, **_kwargs):
        return BleakClient(device, timeout=timeout)

    for name, key in keys.items():
        client = TiltShadeClient(
            str(address),
            key,
            client_factory=factory,
            ack_timeout_seconds=ack_timeout,
            response_timeout_seconds=response_timeout,
        )
        try:
            status = await client.read_status()
        except AuthenticationError:
            continue  # wrong key for this shade; try the next candidate
        return name, status
    return None, None


async def _run(args: argparse.Namespace) -> int:
    keys = _load_keys(args.key_dir, args.keys_json)
    _LOGGER.info("Loaded %d candidate key(s): %s", len(keys), ", ".join(keys))
    _LOGGER.info("Scanning %.0fs for advertising Tilt shades...", args.scan_timeout)
    discovered = await BleakScanner.discover(timeout=args.scan_timeout, return_adv=True)
    shades = {
        address: (device, adv)
        for address, (device, adv) in discovered.items()
        if (adv.local_name or device.name or "").startswith(_SHADE_NAME_PREFIX)
    }
    if not shades:
        _LOGGER.error(
            "No %s* shades seen. Force-quit the Tilt app on ALL phones and unplug the "
            "cloud bridge (a shade only advertises while no central holds it), then retry.",
            _SHADE_NAME_PREFIX,
        )
        return 2

    _LOGGER.info("Found %d shade(s); probing each (read-only)...", len(shades))
    problems = 0
    for address, (device, adv) in sorted(
        shades.items(), key=lambda item: item[1][1].rssi or -999, reverse=True
    ):
        label = f"{adv.local_name or device.name} [{address}] {adv.rssi}dBm"
        try:
            name, status = await _probe(
                device,
                address,
                keys,
                ack_timeout=args.ack_timeout,
                response_timeout=args.response_timeout,
            )
        except (BleakError, TiltProtocolError, TimeoutError) as exc:
            _LOGGER.warning("  %s -> could not complete session: %s: %s", label, type(exc).__name__, exc)
            problems += 1
            continue
        if name is None:
            _LOGGER.error("  %s -> reached, but NO rescued key matched (stale/wrong key)", label)
            problems += 1
        else:
            _LOGGER.info(
                "  %s -> AUTHENTICATED by key %r  (position %d%%, battery %d%%)",
                label,
                name,
                status.position_percent,
                status.battery_percent,
            )

    if problems:
        _LOGGER.error("Gate result: %d shade(s) failed to authenticate.", problems)
        return 1
    _LOGGER.info("Gate result: PASS -- every shade in range authenticated with a rescued key.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key-dir", help="Directory of <name>.key files (64 hex each).")
    parser.add_argument("--keys-json", help="JSON file mapping name -> 64-hex key.")
    parser.add_argument("--scan-timeout", type=float, default=12.0)
    parser.add_argument("--ack-timeout", type=float, default=2.0)
    parser.add_argument("--response-timeout", type=float, default=6.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
