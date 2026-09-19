# Changelog

All notable changes to `smartblinds-ble`. Dates are the release tag's date.

This project has two hardware tracks (see [`docs/PROTOCOL.md`](docs/PROTOCOL.md)).
Everything below concerns the **Tilt roller shade** path; the legacy
`SmartBlind_DFU` path remains an unverified hypothesis and has not changed.

## Unreleased

- **Tilt cloud key export** (`smartblinds-import-tilt`, `smartblinds_ble.tilt_cloud`).
  One login returns every Tilt shade's BLE MAC and 32-byte `pairingKey` — the keys
  that cannot be brute-forced or sniffed, and that disappear with the vendor cloud.
- The Tilt backend shares the `mysmartblinds.auth0.com` tenant with the legacy
  cloud; the difference is `audience`. Requesting `Tilt Settings Storage API` with
  the app's public client id and the password-realm grant returns a token the
  store accepts, which is why a legacy login previously succeeded but returned
  zero devices.
- Needs **no optional extra** — unlike the legacy importer it uses only the
  standard library. `--access-token` skips the password grant for MFA accounts or
  when Auth0 attack protection blocks the login; `--include-bridges` and `--debug`
  mirror the legacy tool.
- Every request parameter is taken from a capture of the Tilt app's own login,
  and store parsing is tested against the captured response shape.

## 0.1.2 — 2026-09-12

- `TiltShadeClient`'s `client_factory` may now be **async** and may return an
  **already connected** client: an awaitable result is awaited, and `connect()` is
  only called when the client is not already connected. Sync factories returning a
  fresh client behave exactly as before, so this is additive.
- This lets a caller hand connection establishment to
  `bleak_retry_connector.establish_connection()`, which Home Assistant asks
  integrations to use. It retries through Bluetooth proxies and releases proxy
  connection slots that otherwise leak when an attempt fails — leaked slots had
  taken a live ESPHome proxy out of service.

## 0.1.1 — 2026-09-11

- **Fixed:** `set_position_and_read_status` raised on essentially every successful
  move. It slept `settle_seconds`, re-read, and raised unless the shade had already
  *arrived* — but these motors need tens of seconds to travel.
- It now raises only when the shade answered and did **not** move *toward* the
  target (a stuck motor, an obstruction, a rejected command). A partial move
  returns `(status, moved=True)`. The same rule applies to the ack-timeout branch.
- `moved` is documented as "a write was issued", not "travel finished". The command
  is still never re-sent; verify by re-reading later.
- The fake shade gained `travel_fraction`, covering the mid-travel path in tests.

## 0.1.0 — 2026-09-05

- First release, published to PyPI via Trusted Publishing.
- Tilt roller shade support: vendored MIT encrypted codec from
  `Sunrise-Labs-Dot-AI/tilt-local-bridge` plus an async `bleak` transport
  (`TiltShadeClient`, keyed by MAC + 32-byte pairing key). HMAC-SHA256 key proof,
  then AES-128-CTR; live position, battery, charge, and calibration.
- Legacy `SmartBlind_DFU` client (`SmartBlind`), scanner, and first-byte key
  brute-force — all **unverified on hardware**.
- Optional `[cloud]` extra: key export from the legacy MySmartBlinds cloud
  (`smartblinds-import-cloud`).
- Fake-shade test harness exercising both directions of the link layer.
