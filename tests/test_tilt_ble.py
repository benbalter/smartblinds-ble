"""End-to-end transport tests: the real central against an in-memory fake shade.

These exercise the full stack with no radio — GATT surface, chunking, both-way
ACKs, the crypto handshake, key authentication, and AES-CTR reads/writes — by
running the production ``TiltShadeClient`` against ``FakeShadeClient`` (the
peripheral half of the same protocol).
"""

from __future__ import annotations

import pytest
import tilt_helpers as H
from bleak.exc import BleakError

from smartblinds_ble.tilt.ble import TiltBleError, TiltShadeClient
from smartblinds_ble.tilt.protocol import AuthenticationError

KEY = bytes(range(32))
MAC = "AA:BB:CC:DD:EE:01"


def _factory_for(*clients):
    """Return a client_factory that yields the given clients in order."""

    queue = list(clients)

    def factory(_address, *, timeout, pair):
        assert pair is False  # the shade uses app-layer auth, never BLE pairing
        return queue.pop(0)

    return factory


async def test_read_status_end_to_end():
    shade = H.FakeShadeClient(KEY, start_position=30, battery=66)
    client = TiltShadeClient(MAC, KEY, client_factory=_factory_for(shade))
    status = await client.read_status()
    assert status.position_percent == 30
    assert status.battery_percent == 66
    assert status.calibrated is True
    assert shade.is_connected is False  # session cleaned up


async def test_set_position_moves_and_verifies():
    shade = H.FakeShadeClient(KEY, start_position=0)
    client = TiltShadeClient(
        MAC, KEY, allow_position_writes=True, client_factory=_factory_for(shade)
    )
    status, moved = await client.set_position_and_read_status(100, settle_seconds=0)
    assert moved is True
    assert status.position_percent == 100
    assert shade.set_position_calls == 1


async def test_set_position_is_noop_when_already_at_target():
    shade = H.FakeShadeClient(KEY, start_position=50)
    client = TiltShadeClient(
        MAC, KEY, allow_position_writes=True, client_factory=_factory_for(shade)
    )
    status, moved = await client.set_position_and_read_status(50, settle_seconds=0)
    assert moved is False
    assert status.position_percent == 50
    assert shade.set_position_calls == 0  # never issued a movement


async def test_position_write_disabled_by_default():
    shade = H.FakeShadeClient(KEY, start_position=0)
    client = TiltShadeClient(MAC, KEY, client_factory=_factory_for(shade))
    with pytest.raises(TiltBleError):
        await client.set_position_and_read_status(80, settle_seconds=0)
    assert shade.set_position_calls == 0


async def test_wrong_pairing_key_raises_authentication_error():
    # Shade proves knowledge of a different key than the client was configured with.
    shade = H.FakeShadeClient(KEY, proof_key=bytes(range(1, 33)))
    client = TiltShadeClient(MAC, KEY, client_factory=_factory_for(shade))
    with pytest.raises(AuthenticationError):
        await client.read_status()


async def test_read_status_retries_once_after_transient_failure():
    class DeadClient:
        is_connected = False

        async def connect(self):
            raise BleakError("simulated transient connect failure")

        async def disconnect(self):
            pass

    good = H.FakeShadeClient(KEY, start_position=42)
    client = TiltShadeClient(MAC, KEY, client_factory=_factory_for(DeadClient(), good))
    status = await client.read_status()  # first session fails, retry succeeds
    assert status.position_percent == 42


def test_rejects_short_pairing_key():
    with pytest.raises(Exception):  # noqa: B017 - constructor guards key length
        TiltShadeClient(MAC, bytes(16))
