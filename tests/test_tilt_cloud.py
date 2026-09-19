"""Tilt cloud export: request shape, store parsing, and error translation.

The store fixture mirrors the shape of a real captured
``GET /v2/store/tilt`` response (rooms -> rollerShades/bridges, each
``{id = BLE MAC, name, pairingKey}``).
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import patch

import pytest

from smartblinds_ble.tilt_cloud import (
    TILT_AUDIENCE,
    TILT_CLIENT_ID,
    TiltCloudError,
    fetch_devices,
    login,
    parse_store,
)

STORE = {
    "name": "Someone",
    "rooms": [
        {
            "name": "Office",
            "rollerShades": [
                {"id": "C2:A3:D6:9B:F0:86", "name": "Left", "pairingKey": "ab" * 32},
                {"id": "ff:c8:29:08:57:f5", "name": "Right", "pairingKey": "CD" * 32},
            ],
            "bridges": [],
        },
        {
            "name": "Dining",
            "rollerShades": [{"id": "FE:36:EC:4E:20:12", "name": "Left", "pairingKey": "ef" * 32}],
            "bridges": [{"id": "AA:00:00:00:00:01", "name": "Bridge", "pairingKey": "11" * 32}],
        },
    ],
}


def _http_error(code: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.invalid", code, "err", {}, BytesIO(json.dumps(body).encode())
    )


def test_parse_store_extracts_mac_and_key() -> None:
    devices = parse_store(STORE)
    assert [d.mac for d in devices] == [
        "C2:A3:D6:9B:F0:86",
        "FF:C8:29:08:57:F5",  # normalized to upper case
        "FE:36:EC:4E:20:12",
    ]
    assert [d.room for d in devices] == ["Office", "Office", "Dining"]
    # Keys come back lower-case hex, ready for bytes.fromhex().
    assert all(len(bytes.fromhex(d.key)) == 32 for d in devices)
    assert devices[1].key == "cd" * 32


def test_bridges_are_excluded_by_default() -> None:
    """Bridges carry a key but are cloud-only, with no local control path."""
    assert all(d.kind == "roller_shade" for d in parse_store(STORE))
    with_bridges = parse_store(STORE, include_bridges=True)
    assert [d.kind for d in with_bridges].count("bridge") == 1


def test_entries_without_a_key_are_skipped() -> None:
    store = {"rooms": [{"name": "R", "rollerShades": [{"id": "AA:BB", "name": "no key"}]}]}
    assert parse_store(store) == []


def test_login_requests_the_tilt_audience() -> None:
    """Without this audience Auth0 mints a legacy token the store rejects."""
    with patch("smartblinds_ble.tilt_cloud._post_json", return_value={"access_token": "t"}) as post:
        login("someone@example.com", "pw")
    _url, payload = post.call_args[0]
    assert payload["audience"] == TILT_AUDIENCE
    assert payload["client_id"] == TILT_CLIENT_ID
    assert payload["grant_type"] == "http://auth0.com/oauth/grant-type/password-realm"
    assert payload["realm"] == "Username-Password-Authentication"
    assert "client_secret" not in payload  # public native client


def test_fetch_devices_uses_the_access_token() -> None:
    with (
        patch("smartblinds_ble.tilt_cloud.login", return_value={"access_token": "tok"}),
        patch("smartblinds_ble.tilt_cloud._get_json", return_value=STORE) as get,
    ):
        devices = fetch_devices("someone@example.com", "pw")
    assert get.call_args[0][1] == "tok"
    assert len(devices) == 3


def test_fetch_devices_accepts_a_captured_token_without_logging_in() -> None:
    with (
        patch("smartblinds_ble.tilt_cloud.login", side_effect=AssertionError("must not log in")),
        patch("smartblinds_ble.tilt_cloud._get_json", return_value=STORE),
    ):
        assert len(fetch_devices(access_token="captured")) == 3


def test_mfa_account_is_told_what_to_do() -> None:
    error = _http_error(403, {"error": "mfa_required", "error_description": "MFA required"})
    with (
        patch("smartblinds_ble.tilt_cloud._post_json", side_effect=error),
        pytest.raises(TiltCloudError, match="multi-factor"),
    ):
        login("someone@example.com", "pw")


def test_bad_password_is_reported_as_such() -> None:
    error = _http_error(403, {"error": "invalid_grant", "error_description": "Wrong email or password."})
    with (
        patch("smartblinds_ble.tilt_cloud._post_json", side_effect=error),
        pytest.raises(TiltCloudError, match="rejected the email/password"),
    ):
        login("someone@example.com", "pw")


def test_store_401_explains_the_audience_trap() -> None:
    from smartblinds_ble.tilt_cloud import fetch_store

    error = urllib.error.HTTPError("u", 401, "Unauthorized", {}, BytesIO(b""))
    with (
        patch("smartblinds_ble.tilt_cloud._get_json", side_effect=error),
        pytest.raises(TiltCloudError, match="id_token"),
    ):
        fetch_store("wrong-audience-token")
