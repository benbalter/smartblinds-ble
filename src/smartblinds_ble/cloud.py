"""Optional cloud helper: pull each motor's MAC + passkey from the account.

While the MySmartBlinds/Tilt cloud is still online, it will hand back the *real*
per-motor BLE key (``encodedPasskey``) for every shade on your account after an
email/password login. That is far better than brute-forcing, and — given the
vendor is winding down — it is time-sensitive: once the cloud goes dark, the keys
are only recoverable by brute-force or BLE sniffing.

This module is intentionally isolated so the core library stays cloud-free. It
requires the optional ``cloud`` extra::

    pip install "smartblinds-ble[cloud]"

which pulls in ``smartblinds-client`` (used only for its auth0 login). The GraphQL
query is issued directly here so we can choose the auth token (``id_token`` vs
``access_token``) and optionally include ``deleted`` shades — neither of which the
upstream client exposes.

⚠️  The mapping "cloud passkey == BLE key at handle 0x001b" is a strong but
    UNVERIFIED hypothesis until Milestone 0 confirms it on hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The single query the app uses. `deleted` is included so we can optionally keep
# shades the account has soft-deleted (their passkeys are usually still valid).
_USER_QUERY = (
    "query GetUserInfo { user { "
    "rooms { id name deleted } "
    "blinds { name encodedMacAddress encodedPasskey roomId deleted } } }"
)


@dataclass(frozen=True)
class CloudBlind:
    """A shade as described by the cloud account."""

    name: str
    mac: str  # "AA:BB:CC:DD:EE:FF"
    key: str  # BLE passkey as a hex string (feed to SmartBlind(..., key=...))
    room: str | None = None
    deleted: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mac": self.mac,
            "key": self.key,
            "room": self.room,
            "deleted": self.deleted,
        }


def _client(username: str, password: str):
    """Return a logged-in SmartBlindsClient (raises ImportError without the extra)."""
    try:
        from smartblinds_client import SmartBlindsClient
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ImportError(
            'The cloud importer needs the optional extra: pip install "smartblinds-ble[cloud]"'
        ) from exc
    client = SmartBlindsClient(username=username, password=password)
    client.login()
    return client


def _graphql(client, token: str, query: str) -> dict[str, Any]:
    """POST a GraphQL query using the chosen token (``id_token``/``access_token``)."""
    import requests  # provided transitively by smartblinds-client

    bearer = client._tokens.get(token)
    if not bearer:
        raise ValueError(f"login did not return a {token!r}")
    resp = requests.post(
        client.GRAPHQL_ENDPOINT,
        headers={
            "Authorization": f"Bearer {bearer}",
            "auth0-client-id": client.AUTH0_CLIENT_ID,
            "user-agent": "MySmartBlinds/1 CFNetwork/1404.0.5 Darwin/22.3.0",
        },
        json={"query": query},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _format_mac(raw: bytes) -> str:
    """Best-effort format of the decoded MAC into AA:BB:CC:DD:EE:FF."""
    if len(raw) == 6:
        return ":".join(f"{b:02X}" for b in raw)
    try:
        return raw.decode("ascii").strip().upper()
    except UnicodeDecodeError:
        return raw.hex().upper()


def fetch_blinds(
    username: str,
    password: str,
    *,
    include_deleted: bool = False,
    token: str = "id_token",
) -> list[CloudBlind]:
    """Log in to the cloud and return every shade's name, MAC, and BLE key.

    Args:
        include_deleted: also return shades the account has soft-deleted.
        token: which auth token to send — ``"id_token"`` (default, what the
            original client used) or ``"access_token"``.
    """
    import base64

    client = _client(username, password)
    data = _graphql(client, token, _USER_QUERY)
    if data.get("errors"):
        raise RuntimeError(f"cloud returned errors: {data['errors']}")
    user = (data.get("data") or {}).get("user") or {}
    rooms = {r["id"]: r["name"] for r in (user.get("rooms") or [])}

    result: list[CloudBlind] = []
    for b in user.get("blinds") or []:
        if b.get("deleted") and not include_deleted:
            continue
        result.append(
            CloudBlind(
                name=b["name"],
                mac=_format_mac(base64.b64decode(b["encodedMacAddress"])),
                key=base64.b64decode(b["encodedPasskey"]).hex(),
                room=rooms.get(b.get("roomId")),
                deleted=bool(b.get("deleted")),
            )
        )
    return result


def diagnose(username: str, password: str) -> str:
    """Return a human-readable report probing both tokens (for `--debug`)."""
    client = _client(username, password)
    lines = [
        f"token keys: {list(client._tokens.keys())}",
        f"token_type: {client._tokens.get('token_type')}",
    ]
    for token in ("id_token", "access_token"):
        if not client._tokens.get(token):
            lines.append(f"\n[{token}] not present")
            continue
        try:
            data = _graphql(client, token, _USER_QUERY)
        except Exception as exc:  # noqa: BLE001 - report any failure per token
            lines.append(f"\n[{token}] request failed: {exc}")
            continue
        user = (data.get("data") or {}).get("user") or {}
        rooms = user.get("rooms")
        blinds = user.get("blinds")
        lines.append(f"\n[{token}]")
        if data.get("errors"):
            lines.append(f"  errors: {data['errors']}")
        lines.append(f"  user present: {bool(user)}")
        lines.append(f"  rooms: {'null' if rooms is None else len(rooms)}")
        lines.append(f"  blinds: {'null' if blinds is None else len(blinds)}")
        for b in blinds or []:
            pk = b.get("encodedPasskey") or ""
            lines.append(f"    {b['name']!r} deleted={b['deleted']} passkey_len={len(pk)}")
    return "\n".join(lines)
