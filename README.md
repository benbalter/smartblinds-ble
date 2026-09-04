# smartblinds-ble

Local, **hub-free and cloud-free** control of MySmartBlinds / Tilt shade motors
over Bluetooth LE — designed to work through Home Assistant and ESPHome Bluetooth
Proxies, so you can retire the discontinued proprietary hub.

> **Status: pre-alpha / bring-up.** The protocol this relies on was
> reverse-engineered in 2018 and is **not yet re-verified** on current firmware.
> See [`docs/ROADMAP.md`](docs/ROADMAP.md) — **Milestone 0 gates everything.**
>
> Not affiliated with, authorized by, or endorsed by MySmartBlinds or Tilt. Use
> at your own risk; this may void your warranty.

## Why

The motors are ordinary BLE devices. The only reason the vendor's hub exists is to
bridge Wi-Fi → cloud → BLE. The company is effectively abandonware and the cloud
could vanish. This project talks to the motors **directly and locally**, so:

- No hub, no cloud, no account.
- Control routes through cheap **ESP32 ESPHome Bluetooth Proxies** for whole-home
  BLE coverage.
- Everything stays on your LAN.

## How it works

Two layers (see the roadmap):

1. **`smartblinds-ble`** (this repo) — a small async, `bleak`-based Python library.
2. **`ha-smartblinds-ble`** (planned) — a HACS-installable Home Assistant
   integration exposing each shade as an optimistic `cover` with tilt.

## The two things everyone gets stuck on

- **The per-motor key.** Each motor needs a BLE key. Discover it by brute-forcing
  the first byte (`smartblinds-find-key`) or by sniffing the app once. See
  [`docs/PROTOCOL.md`](docs/PROTOCOL.md).
- **No state feedback.** The motors are open-loop (reads return `0xFF`). Position
  is tracked optimistically; changes from the app/wand are invisible.

## Quick start (bring-up, local adapter)

```bash
pip install -e ".[dev]"
smartblinds-find-key            # scan + brute-force keys for nearby motors
pytest                          # protocol/encoding unit tests (mocked BLE)
```

```python
import asyncio
from smartblinds_ble import SmartBlind, discover

async def main():
    (device,) = await discover()
    blind = SmartBlind(device, key="2a")   # from smartblinds-find-key
    await blind.set_tilt_percent(50)       # flat-ish

asyncio.run(main())
```

## Credits

- [`dnschneid/pysmartblinds`](https://github.com/dnschneid/pysmartblinds) — the
  original reverse engineering (Apache-2.0); this is a modern async port. See
  [`NOTICE`](NOTICE).
- [`LennP/ha-motionblinds_ble`](https://github.com/LennP/ha-motionblinds_ble) —
  the template for the HA integration layer.

## License

[Apache-2.0](LICENSE).
