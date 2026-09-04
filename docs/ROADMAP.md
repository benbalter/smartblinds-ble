# Roadmap

## ⛔ M0 — Prove the protocol on current hardware (gates everything)

The whole project rests on a protocol reverse-engineered ~2018, on motors since
rebranded to "Tilt" with app updates through 2025. Before any packaging effort,
confirm on a real, current shade:

- [ ] Discover a motor (`smartblinds-find-key` / `discover()`).
- [ ] Brute-force + confirm the key (`keyscan`).
- [ ] **Confirm the cloud `encodedPasskey` (base64-decoded) == the BLE key** the
      motor expects at handle `0x001b`. If true, cloud import becomes the primary
      key-acquisition path (see PROTOCOL.md) and brute-force is just a fallback.
- [ ] A position write physically moves the motor (`set_tilt`).
- [ ] All of the above works **through an ESPHome Bluetooth Proxy**, not just a
      local adapter. (Reuse the FireBeetle ESP32-S3-U proxy config.)
- [ ] Record findings + corrections in [PROTOCOL.md](PROTOCOL.md).

**If M0 fails, this is a protocol-RE project, not a packaging project.** Stop and
say so before promising anyone a hub replacement.

## M1 — Library (`smartblinds-ble`)

- [ ] Fix constants/encoding per M0 findings; make `test_protocol.py` reflect reality.
- [ ] Robust connect/retry via `bleak-retry-connector`.
- [ ] Cloud-import helper: pull MAC + `encodedPasskey` for all shades via
      `smartblinds-client` (one login), so users skip brute-forcing. Keep it an
      optional extra so the core lib stays cloud-free.
- [ ] Publish to PyPI under a final, non-trademark-implying name.

## M2 — Home Assistant integration (`ha-smartblinds-ble`)

- [ ] Config flow + Bluetooth auto-discovery (works via proxies).
- [ ] Optimistic `cover` entity with tilt (0..100% → 0..200).
- [ ] Templated on [`LennP/ha-motionblinds_ble`](https://github.com/LennP/ha-motionblinds_ble).

## M3 — Ship it

- [ ] HACS release; key-extraction guide (app-sniff + brute-force paths).
- [ ] ESP32-proxy setup guide.
- [ ] Issue templates, CONTRIBUTING, Discussions for key-extraction help.
- [ ] Announce in the [HA community thread](https://community.home-assistant.io/t/tilt-my-blinds-mysmartblinds/12890)
      and r/homeassistant.

## M4 — Stretch

- [ ] ESPHome external component (protocol in C++ on the ESP32; better range,
      dodges the 3-connection proxy limit).
- [ ] Battery/solar entity if the firmware exposes it.
- [ ] Propose for Home Assistant core.
