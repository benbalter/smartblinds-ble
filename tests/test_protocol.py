"""Protocol-level unit tests with a mocked BLE transport.

These pin the *encoding* (key normalization, position clamping, write sequence)
so a future M0 hardware fix changes constants, not behavior. They do NOT prove
the protocol works on real hardware — that's Milestone 0.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from smartblinds_ble import const
from smartblinds_ble.blind import SmartBlind, _normalize_key
from smartblinds_ble.exceptions import InvalidPosition


class FakeDevice:
    def __init__(self, address: str = "AA:BB:CC:DD:EE:FF") -> None:
        self.address = address
        self.name = const.DEVICE_NAME


def test_normalize_key_int():
    assert _normalize_key(0x2A) == b"\x2a"


def test_normalize_key_hex_string():
    assert _normalize_key("2a1b") == b"\x2a\x1b"


def test_normalize_key_iterable():
    assert _normalize_key([0x01, 0x02]) == b"\x01\x02"


@pytest.mark.parametrize("bad", [-1, 201, 999])
async def test_set_tilt_rejects_out_of_range(bad):
    blind = SmartBlind(FakeDevice(), key=0x01)
    with pytest.raises(InvalidPosition):
        await blind.set_tilt(bad)


async def test_set_tilt_writes_key_then_position():
    """Every op must send the key first, then the position byte."""
    client = AsyncMock()
    with patch("smartblinds_ble.blind.establish_connection", AsyncMock(return_value=client)):
        blind = SmartBlind(FakeDevice(), key=0x2A)
        await blind.set_tilt(150)

    assert client.write_gatt_char.await_count == 2
    (first_handle, first_payload), _ = client.write_gatt_char.await_args_list[0]
    (second_handle, second_payload), _ = client.write_gatt_char.await_args_list[1]
    assert first_handle == const.KEY_CHAR_HANDLE
    assert first_payload == b"\x2a"
    assert second_handle == const.SET_CHAR_HANDLE
    assert second_payload == bytes([150])
    assert blind.position == 150
    client.disconnect.assert_awaited_once()


async def test_set_tilt_percent_maps_to_native_range():
    client = AsyncMock()
    with patch("smartblinds_ble.blind.establish_connection", AsyncMock(return_value=client)):
        blind = SmartBlind(FakeDevice(), key=0x01)
        await blind.set_tilt_percent(50)
    assert blind.position == 100  # 50% of 0..200
