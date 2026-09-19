"""Optional cloud helper: export every Tilt shade's BLE pairing key.

The **Tilt** app's backend is a different system from the legacy MySmartBlinds
cloud that :mod:`smartblinds_ble.cloud` talks to. Both sit on the same Auth0
tenant (``mysmartblinds.auth0.com``), which is why a legacy login *succeeds* for
a Tilt account and then returns zero blinds: the token is minted for the legacy
API's audience, and the Tilt store rejects it.

The difference that matters is ``audience``. Asking Auth0 for a token scoped to
``Tilt Settings Storage API`` yields an ``access_token`` the Tilt store accepts::

    POST https://mysmartblinds.auth0.com/oauth/token
        grant_type = http://auth0.com/oauth/grant-type/password-realm
        client_id  = <the Tilt app's public client id>
        realm      = Username-Password-Authentication
        audience   = Tilt Settings Storage API
    GET  https://api.tiltsmarthome.com/v2/store/tilt   (Bearer access_token)

The store returns ``rooms[]``, each holding ``rollerShades[]`` and ``bridges[]``
where every device is ``{id = BLE MAC, name, pairingKey}``. The 32-byte
``pairingKey`` is exactly what :class:`smartblinds_ble.tilt.TiltShadeClient`
needs, so one login recovers local control of every shade on the account.

⚠️  **Time-sensitive.** A Tilt pairing key cannot be brute-forced (32 bytes) or
    recovered from a BLE sniff, and the vendor is winding down. When this cloud
    goes dark, un-exported keys are gone for good. Export now, back the file up.

Unlike :mod:`smartblinds_ble.cloud` this needs no third-party client library and
no optional extra — it speaks Auth0 and one REST endpoint over the standard
library. It is still kept out of the package's public API so the core stays
cloud-free.

The client id below is a *public* OAuth client identifier, extractable from any
copy of the app; it is not a secret. This logs into **your own account** to
retrieve **your own devices'** keys, for interoperability with hardware you own.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

AUTH0_TOKEN_URL = "https://mysmartblinds.auth0.com/oauth/token"
TILT_STORE_URL = "https://api.tiltsmarthome.com/v2/store/tilt"

#: The Tilt iOS app's public Auth0 client id (no client secret: a native client).
TILT_CLIENT_ID = "Owjr4yOJ2HauKaQhBpICgmfTf7naJsRd"
#: Without this audience Auth0 mints a legacy-API token and the store 401s.
TILT_AUDIENCE = "Tilt Settings Storage API"
TILT_REALM = "Username-Password-Authentication"
TILT_SCOPE = "openid profile email offline_access"
_PASSWORD_REALM_GRANT = "http://auth0.com/oauth/grant-type/password-realm"

_TIMEOUT_SECONDS = 30


class TiltCloudError(RuntimeError):
    """Raised when the Tilt cloud cannot be logged into or read."""


@dataclass(frozen=True)
class TiltDevice:
    """One device from the Tilt cloud store."""

    name: str
    mac: str  # the store's `id`, already "AA:BB:CC:DD:EE:FF"
    key: str  # 64-hex pairing key; feed to TiltShadeClient(mac, bytes.fromhex(key))
    room: str | None = None
    kind: str = "roller_shade"  # or "bridge"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mac": self.mac,
            "key": self.key,
            "room": self.room,
            "kind": self.kind,
        }


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode())


def _get_json(url: str, bearer: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"authorization": f"Bearer {bearer}", "accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode())


def _auth0_failure(exc: urllib.error.HTTPError) -> TiltCloudError:
    """Translate an Auth0 error body into something the user can act on."""
    try:
        body = json.loads(exc.read().decode())
    except (ValueError, OSError):
        body = {}
    code = body.get("error", "")
    description = body.get("error_description") or exc.reason

    if code == "invalid_grant":
        return TiltCloudError(f"Auth0 rejected the email/password: {description}")
    if code == "mfa_required":
        return TiltCloudError(
            "This account has multi-factor authentication enabled, which the "
            "password grant cannot complete. Capture the access_token from the "
            "app instead and pass it to fetch_devices(access_token=...)."
        )
    if code in {"too_many_attempts", "access_denied"}:
        return TiltCloudError(
            f"Auth0 blocked the login ({code}): {description}. Its attack protection "
            "trips on password grants from an unfamiliar IP; clear the block from the "
            "Tilt app on the same network, or pass an access_token captured from it."
        )
    return TiltCloudError(f"Auth0 login failed ({exc.code} {code or exc.reason}): {description}")


def login(username: str, password: str) -> dict[str, Any]:
    """Return Auth0's full token response for a Tilt account."""
    try:
        return _post_json(
            AUTH0_TOKEN_URL,
            {
                "grant_type": _PASSWORD_REALM_GRANT,
                "client_id": TILT_CLIENT_ID,
                "username": username,
                "password": password,
                "realm": TILT_REALM,
                "scope": TILT_SCOPE,
                "audience": TILT_AUDIENCE,
            },
        )
    except urllib.error.HTTPError as exc:
        raise _auth0_failure(exc) from exc
    except urllib.error.URLError as exc:
        raise TiltCloudError(f"Could not reach Auth0: {exc.reason}") from exc


def fetch_store(access_token: str) -> dict[str, Any]:
    """Return the raw Tilt store document for the logged-in account."""
    try:
        store = _get_json(TILT_STORE_URL, access_token)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise TiltCloudError(
                "The Tilt store rejected this token (401). An id_token will always "
                f"401 here — use the access_token, and make sure it was minted for "
                f"the {TILT_AUDIENCE!r} audience."
            ) from exc
        raise TiltCloudError(f"Tilt store request failed ({exc.code} {exc.reason}).") from exc
    except urllib.error.URLError as exc:
        raise TiltCloudError(f"Could not reach the Tilt store: {exc.reason}") from exc

    if not isinstance(store, dict):
        raise TiltCloudError("Tilt store returned an unexpected document.")
    return store


def parse_store(store: dict[str, Any], *, include_bridges: bool = False) -> list[TiltDevice]:
    """Extract every keyed device from a Tilt store document.

    Bridges carry a pairing key too, but they are cloud-only MQTT clients with no
    local control path, so they are left out unless asked for.
    """
    devices: list[TiltDevice] = []
    for room in store.get("rooms") or []:
        room_name = room.get("name")
        groups = [("roller_shade", room.get("rollerShades") or [])]
        if include_bridges:
            groups.append(("bridge", room.get("bridges") or []))
        for kind, entries in groups:
            for entry in entries:
                key = entry.get("pairingKey")
                mac = entry.get("id")
                if not key or not mac:
                    continue
                devices.append(
                    TiltDevice(
                        name=entry.get("name") or mac,
                        mac=str(mac).upper(),
                        key=str(key).lower(),
                        room=room_name,
                        kind=kind,
                    )
                )
    return devices


def fetch_devices(
    username: str | None = None,
    password: str | None = None,
    *,
    access_token: str | None = None,
    include_bridges: bool = False,
) -> list[TiltDevice]:
    """Log in (or reuse a token) and return every shade's MAC + pairing key."""
    if access_token is None:
        if not username or password is None:
            raise TiltCloudError("Provide either username+password or access_token.")
        tokens = login(username, password)
        access_token = tokens.get("access_token")
        if not access_token:
            raise TiltCloudError("Auth0 login returned no access_token.")
    return parse_store(fetch_store(access_token), include_bridges=include_bridges)


def diagnose(
    username: str | None = None,
    password: str | None = None,
    *,
    access_token: str | None = None,
) -> str:
    """Return a human-readable report of what the account exposes (for `--debug`)."""
    lines: list[str] = []
    if access_token is None:
        if not username or password is None:
            raise TiltCloudError("Provide either username+password or access_token.")
        tokens = login(username, password)
        lines.append(f"token keys: {sorted(tokens)}")
        lines.append(f"token_type: {tokens.get('token_type')}")
        lines.append(f"expires_in: {tokens.get('expires_in')}")
        lines.append(f"scope: {tokens.get('scope')}")
        access_token = tokens.get("access_token")
        if not access_token:
            lines.append("\nNo access_token in the response — cannot read the store.")
            return "\n".join(lines)

    store = fetch_store(access_token)
    rooms = store.get("rooms") or []
    lines.append(f"\nstore top-level keys: {sorted(store)}")
    lines.append(f"rooms: {len(rooms)}")
    for room in rooms:
        shades = room.get("rollerShades") or []
        bridges = room.get("bridges") or []
        lines.append(f"  {room.get('name')!r}: {len(shades)} shade(s), {len(bridges)} bridge(s)")
        for entry in [*shades, *bridges]:
            key = entry.get("pairingKey") or ""
            lines.append(f"    {entry.get('name')!r} id={entry.get('id')} key_len={len(key)}")
    return "\n".join(lines)
