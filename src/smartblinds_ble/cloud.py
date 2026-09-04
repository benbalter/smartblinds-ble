"""Optional cloud helper: pull each motor's MAC + passkey from the account.

While the MySmartBlinds/Tilt cloud is still online, it will hand back the *real*
per-motor BLE key (``encodedPasskey``) for every shade on your account after an
email/password login. That is far better than brute-forcing, and — given the
vendor is winding down — it is time-sensitive: once the cloud goes dark, the keys
are only recoverable by brute-force or BLE sniffing.

This module is intentionally isolated so the core library stays cloud-free. It
requires the optional ``cloud`` extra::

    pip install "smartblinds-ble[cloud]"

which pulls in ``smartblinds-client`` (the community cloud client).

⚠️  The mapping "cloud passkey == BLE key at handle 0x001b" is a strong but
    UNVERIFIED hypothesis until Milestone 0 confirms it on hardware.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloudBlind:
    """A shade as described by the cloud account."""

    name: str
    mac: str  # "AA:BB:CC:DD:EE:FF"
    key: str  # BLE passkey as a hex string (feed to SmartBlind(..., key=...))
    room: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"name": self.name, "mac": self.mac, "key": self.key, "room": self.room}


def _format_mac(raw: bytes) -> str:
    """Best-effort format of the decoded MAC into AA:BB:CC:DD:EE:FF."""
    if len(raw) == 6:
        return ":".join(f"{b:02X}" for b in raw)
    try:
        return raw.decode("ascii").strip().upper()
    except UnicodeDecodeError:
        return raw.hex().upper()


def fetch_blinds(username: str, password: str) -> list[CloudBlind]:
    """Log in to the cloud and return every shade's name, MAC, and BLE key.

    Raises ``ImportError`` if the optional ``cloud`` extra isn't installed, and
    surfaces whatever auth/network error ``smartblinds-client`` raises on a bad
    login.
    """
    try:
        from smartblinds_client import SmartBlindsClient  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ImportError(
            'The cloud importer needs the optional extra: pip install "smartblinds-ble[cloud]"'
        ) from exc

    client = SmartBlindsClient(username=username, password=password)
    client.login()
    blinds, rooms = client.get_blinds_and_rooms()
    room_names = {room.uuid: room.name for room in rooms}

    result: list[CloudBlind] = []
    for blind in blinds:
        result.append(
            CloudBlind(
                name=blind.name,
                mac=_format_mac(blind.mac_address),
                key=blind.passkey.hex(),
                room=room_names.get(blind.room_id),
            )
        )
    return result
