# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Local, hub-free & cloud-free BLE control of **MySmartBlinds / Tilt** shade motors, so
they keep working after the (winding-down) vendor cloud dies. Two layers: this
`smartblinds-ble` async, `bleak`-based Python library, and a planned
`ha-smartblinds-ble` HACS integration (separate repo). Unofficial, not affiliated
with the vendor. Apache-2.0; a modern async port of `dnschneid/pysmartblinds` (see
`NOTICE`).

## ⚠️ M0 gates everything

The BLE protocol here was reverse-engineered in 2018 (legacy MySmartBlinds, firmware
2.0) and is **UNVERIFIED on current hardware**. The constants in `const.py` and the
GATT writes in `blind.py` are a *hypothesis*, marked as such. Do not describe them as
working. `docs/ROADMAP.md` Milestone 0 = confirm connect + key + tilt-write on a real
shade before any packaging/publishing. Everything downstream is contingent on M0.

## Commands

- Install (dev): `pip install -e ".[dev]"`
- Test: `pytest -q` — single: `pytest tests/test_protocol.py::test_set_tilt_writes_key_then_position`
- Lint (the CI gate): `ruff check .`
  - CI deliberately does **not** run `ruff format --check` — this ruff version
    reformats Python inside markdown code blocks, which is brittle for the docs.
- Run a tool without installing (src/ layout needs the path): `PYTHONPATH=src python -m smartblinds_ble.tools.find_key`
- CLIs (`[project.scripts]`): `smartblinds-find-key` (BLE brute-force key discovery),
  `smartblinds-import-cloud` (legacy-cloud key export; flags `--debug`,
  `--include-deleted`, `--token`).
- CI: `.github/workflows/ci.yml` runs `ruff check` + `pytest` on Python 3.11/3.12/3.13.

## Architecture

- `blind.py` — `SmartBlind`, the async `bleak` client. Takes a `BLEDevice` (not just an
  address) so connections route through Home Assistant / ESPHome Bluetooth proxies.
  Every op: connect → write key (handle `0x001b`) → write a position byte 0–200 (handle
  `0x001f`) → disconnect. **Open-loop**: motors don't report state (reads return
  `0xFF`), so `position` is tracked optimistically — the eventual HA cover must be
  `assumed_state`.
- `const.py` — protocol constants, all flagged UNVERIFIED. `scanner.py` — discover
  `SmartBlind_DFU` devices.
- `cloud.py` + `tools/import_cloud.py` — **optional** (`[cloud]` extra) key export from
  the vendor cloud, isolated so the core stays cloud-free. See "Two backends" below.
- `tools/find_key.py` — cloud-independent BLE brute-force of the first key byte.
- `contrib/mitm_tilt_addon.py` — mitmproxy addon for reversing the Tilt cloud API;
  auto-redacts secrets, writes `tilt-capture/`.
- `docs/` — `PROTOCOL.md` (RE'd protocol), `ROADMAP.md` (M0-gated milestones),
  `CAPTURE.md` (definitive field notes for capturing the protocol; read before
  attempting either a network-MITM or BLE capture).

## Two backends / device generations (critical, non-obvious)

The hardware split into two ecosystems that do **not** share a data backend:

- **Legacy "MySmartBlinds"** → cloud `api.mysmartblinds.com` (GraphQL). `cloud.py`
  targets this. Key is short (first byte often suffices → brute-forceable). BLE is
  plaintext (`0x001b`/`0x001f`).
- **Newer "Tilt"** → cloud `api.tiltsmarthome.com/v2/store/tilt`. **Same Auth0 tenant**
  (`mysmartblinds.auth0.com`), so a legacy login *succeeds* but returns 0 devices for
  Tilt users. Store: `rooms[].rollerShades[]`/`bridges[]`, each `{id = BLE MAC, name,
  pairingKey}`; `pairingKey` is 32 bytes → Tilt BLE is likely **encrypted/authenticated**,
  unlike the legacy protocol. Use `access_token` (id_token → 401).

Implications: `cloud.py` only serves *legacy* accounts. Tilt devices need the Tilt API
(different Auth0 client_id `Owjr4yOJ2H…`, not yet built) or BLE. The **Tilt bridge is a
cloud-only AWS IoT MQTT client with no local API** (verified: all ports closed) — it is
**not** a local control path. Direct BLE is the only durable local path.

## Conventions / gotchas

- **ruff broad-except**: an `except Exception` that **re-raises** must NOT have
  `# noqa: BLE001` (RUF100 flags it unused); one that swallows / `sys.exit`s **must**.
  `BLE001` is enabled here; `PLC0415` (lazy import) is not.
- `__all__` must be sorted per RUF022 (SCREAMING_SNAKE, then CamelCase, then lowercase;
  alphabetical within each group).
- **Cloud dep**: PyPI `smartblinds-client` is stale (0.6, 2019; won't log in). Install
  the docBliny fork from git; the `[cloud]` extra pin is a floor only (a git URL can't
  live in a PyPI-published extra).
- **Secrets**: `*-keys.json` and `.pklg`/`.pcap` traces contain keys; `tilt-capture/`
  is redacted but still holds emails/MACs/room names — all gitignored, keep them out.
- **Python**: `requires-python >=3.11`; the `type X = Y` statement (3.12+) breaks older
  parsers — avoid it.
- Not on PyPI yet — install from git. Publishing (final name + PyPI) waits for M0.
