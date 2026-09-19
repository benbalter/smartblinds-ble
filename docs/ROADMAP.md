# Roadmap

There are two hardware tracks with nothing in common but a brand name (see
[PROTOCOL.md](PROTOCOL.md)). The **Tilt roller shade** track is working; the
**legacy MySmartBlinds** track is still an unverified hypothesis.

## ✅ Tilt roller shades — shipped (2026-09-11)

Verified end-to-end on four shades: authenticate, read live position/battery,
and physically move on command, routed through an ESPHome Bluetooth Proxy.

- [x] Encrypted session protocol implemented (vendored MIT codec from
      `Sunrise-Labs-Dot-AI/tilt-local-bridge` + async `bleak` transport).
- [x] Key auth confirmed against real shades with keys exported from the Tilt cloud store.
- [x] A position write physically moves the shade.
- [x] Works **through an ESPHome Bluetooth Proxy** (FireBeetle 2 ESP32-S3-U), not
      just a local adapter.
- [x] Proxy-routed connection handling hardened by real-world use: a
      `client_factory` may connect via `bleak_retry_connector.establish_connection()`,
      so failed attempts no longer leak the proxy's limited connection slots
      (0.1.2). Position writes no longer treat a still-travelling shade as a
      failure (0.1.1).
- [x] Fake-shade test harness covering both halves of the link layer.
- [x] Published to PyPI as [`smartblinds-ble`](https://pypi.org/project/smartblinds-ble/)
      (0.1.2; see [CHANGELOG.md](../CHANGELOG.md)).
- [x] Home Assistant integration
      ([`ha-smartblinds-ble`](https://github.com/benbalter/ha-smartblinds-ble)):
      config flow with live key validation, Bluetooth auto-discovery through
      proxies, position `cover` + battery `sensor`.
- [x] Findings recorded in [PROTOCOL.md](PROTOCOL.md).

Next, in rough priority order:

- [ ] Surface the shade's MAC in the HA config flow. Every shade advertises the
      same name, so discovery cards are indistinguishable until you paste a key
      and see whether it authenticates.
- [ ] Submit brand icons to `home-assistant/brands`.
- [ ] HACS default-repository submission (currently a custom repository).
- [ ] A published key-export path for Tilt accounts — **built, not yet run
      against the live cloud.** `smartblinds-import-tilt` / `tilt_cloud.py` do the
      Auth0 password-realm login (audience `Tilt Settings Storage API`, the piece
      that made a legacy login return zero devices) and read the store. Parsing is
      tested against a real captured response, but the round trip needs one live
      login to confirm — and that has to happen before the vendor cloud dies,
      because these keys have no offline substitute.
- [ ] Issue templates, CONTRIBUTING, Discussions for key-extraction help.
- [ ] Announce in the [HA community thread](https://community.home-assistant.io/t/tilt-my-blinds-mysmartblinds/12890)
      and r/homeassistant.

## ⛔ M0-L — Legacy MySmartBlinds motors: prove the protocol

The legacy side of this library rests on reverse engineering from ~2018 and has
**never been confirmed on hardware** — no legacy tilt motors were available to
test against. `const.py` and the plaintext GATT writes in `blind.py` are a
hypothesis, and are labelled as such in the code. If you own legacy motors,
these are the steps that would settle it:

- [ ] Discover a motor (`smartblinds-find-key` / `discover()`).
- [ ] Brute-force + confirm the key (`keyscan`).
- [ ] **Confirm the cloud `encodedPasskey` (base64-decoded) == the BLE key** the
      motor expects at handle `0x001b`. If true, cloud import becomes the primary
      key-acquisition path and brute-force is just a fallback.
- [ ] A position write physically moves the motor (`set_tilt`).
- [ ] The same through an ESPHome Bluetooth Proxy.
- [ ] Record findings + corrections in [PROTOCOL.md](PROTOCOL.md).

Until that happens, do not describe the legacy path as working. The cloud
key-export tool (`smartblinds-import-cloud`) is independent of it and does work
today for legacy accounts.

## Stretch

- [ ] ESPHome external component (protocol in C++ on the ESP32: better range, and
      it dodges the proxy's 3-connection limit).
- [ ] Scenes/schedules that survive HA being down (shade-side, if the firmware
      exposes anything).
- [ ] Propose for Home Assistant core.
