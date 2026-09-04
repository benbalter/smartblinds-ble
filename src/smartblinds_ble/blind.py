"""Async, bleak-based client for a single MySmartBlinds/Tilt motor.

This is a modern async port of the connect -> write-key -> write-position flow
from dnschneid/pysmartblinds (Apache-2.0), rebuilt on ``bleak`` +
``bleak-retry-connector`` so it works transparently through Home Assistant's
Bluetooth stack and ESPHome Bluetooth Proxies (no local BLE adapter required).

Design notes vs. the original:
- The original used pygatt and wrote by raw GATT *handle*. bleak can also write
  by handle, so the port stays faithful; UUIDs are preferred once confirmed (M0).
- The motor is OPEN-LOOP: reads return 0xFF and external changes (app, wand) are
  invisible. Position is therefore tracked client-side and is optimistic.
- Only one connection at a time per motor; connections are transient
  (connect -> write -> disconnect) which also plays nicely with the ESPHome
  proxy's 3-active-connection limit.

⚠️  The protocol constants this relies on are UNVERIFIED on current firmware.
    Milestone 0 gates any real use — see docs/ROADMAP.md.
"""

from __future__ import annotations

from collections.abc import Iterable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from . import const
from .exceptions import ConnectionFailed, InvalidPosition, KeyNotFound


def _normalize_key(key: int | str | Iterable[int]) -> bytes:
    """Coerce a key given as int, hex string, or byte iterable into bytes."""
    if isinstance(key, int):
        return bytes([key])
    if isinstance(key, str):
        return bytes(int(key[i : i + 2], 16) for i in range(0, len(key), 2))
    return bytes(key)


class SmartBlind:
    """Controls a single shade motor over BLE.

    Args:
        device: A bleak ``BLEDevice`` (e.g. from HA's Bluetooth discovery or a
            proxy). Passing the device object — not just an address — is what
            lets connections route through ESPHome proxies.
        key: The motor's BLE key (int first-byte, hex string, or byte iterable).
            Use :meth:`keyscan` if unknown.
    """

    def __init__(self, device: BLEDevice, key: int | str | Iterable[int] = 0) -> None:
        self._device = device
        self._key = _normalize_key(key)
        #: Optimistic, client-tracked tilt in native 0..200 units (open-loop).
        self.position: int = 0

    @property
    def key(self) -> bytes:
        """The current key as bytes."""
        return self._key

    @property
    def address(self) -> str:
        return self._device.address

    async def _write(self, handle: int, payload: bytes) -> None:
        """Connect, authenticate with the key, and write ``payload`` to ``handle``."""
        try:
            client: BleakClient = await establish_connection(
                BleakClient, self._device, self._device.address
            )
        except Exception as exc:  # noqa: BLE001 - surface a typed error
            raise ConnectionFailed(f"Could not connect to {self.address}: {exc}") from exc
        try:
            # Every operation must (re)send the key first.
            await client.write_gatt_char(const.KEY_CHAR_HANDLE, self._key, response=True)
            await client.write_gatt_char(handle, payload, response=True)
        finally:
            await client.disconnect()

    async def set_tilt(self, position: int) -> None:
        """Set the absolute tilt position in native units (0..200)."""
        if not const.POSITION_MIN <= position <= const.POSITION_MAX:
            raise InvalidPosition(
                f"{position} outside {const.POSITION_MIN}..{const.POSITION_MAX}"
            )
        await self._write(const.SET_CHAR_HANDLE, bytes([position]))
        self.position = position

    async def set_tilt_percent(self, percent: float) -> None:
        """Convenience wrapper: set tilt as 0..100% (maps onto 0..200)."""
        pct = max(0.0, min(100.0, percent))
        await self.set_tilt(round(pct / 100 * const.POSITION_MAX))

    async def keyscan(self) -> bytes:
        """Brute-force the first key byte (0x00..0xFF) until a write succeeds.

        Returns the working key. Raises :class:`KeyNotFound` if exhausted.
        A successful full-open write (position 200) is the success signal, mirroring
        the original library's approach.
        """
        for candidate in range(const.KEY_SCAN_FIRST, const.KEY_SCAN_LAST + 1):
            self._key = bytes([candidate])
            try:
                await self.set_tilt(const.POSITION_MAX)
            except ConnectionFailed:
                continue
            else:
                return self._key
        raise KeyNotFound(f"No working key for {self.address}")
