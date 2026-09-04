# smartblinds-ble — local control for MySmartBlinds / Tilt smart blinds (no hub, no cloud)

[![CI](https://github.com/benbalter/smartblinds-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/benbalter/smartblinds-ble/actions/workflows/ci.yml)

Keep your **MySmartBlinds / Tilt motorized blinds** working **even after the cloud
shuts down**. `smartblinds-ble` controls the shade motors **locally over Bluetooth
LE** — **no proprietary hub, no cloud account, no phone app required** — and is
built to run through **Home Assistant** and cheap **ESP32 / ESPHome Bluetooth
Proxies**.

> **Status: pre-alpha / bring-up.** The BLE protocol was reverse-engineered in 2018
> and is **not yet re-verified** on current firmware — see [`docs/ROADMAP.md`](docs/ROADMAP.md)
> (Milestone 0 gates everything). The **cloud key-export tool below works today**,
> independent of that.
>
> Unofficial project. Not affiliated with, authorized by, or endorsed by
> MySmartBlinds, Tilt, or SmarterHome. Use at your own risk; may void your warranty.

## Is this you?

If you're searching for any of the following, you're in the right place:

- **"Is MySmartBlinds / Tilt shutting down / discontinued / out of business?"** —
  the signs point that way (`tiltsmarthome.com` now redirects to a wind-down page,
  parts are unavailable, support has gone quiet).
- **"MySmartBlinds app not working / won't connect / no one answers support."**
- **"How do I control MySmartBlinds without the hub / without the cloud / without the app?"**
- **"MySmartBlinds / Tilt Home Assistant integration"** — a *local* one, not the
  old laggy cloud bridge.
- **"Will my smart blinds keep working if the servers go offline?"**
- **"MySmartBlinds ESP32 / ESPHome / Bluetooth local control."**

## ⏳ Rescue your keys now (do this before the cloud goes dark)

Each motor needs a small BLE **key** to accept commands. While the vendor cloud is
still online, it will hand back the real key for **every shade on your account**
after a single login. Once the cloud shuts down, keys are only recoverable the hard
way (brute-force or Bluetooth sniffing). This step needs **no extra hardware**:

```bash
# Not on PyPI yet — install from GitHub. Use the maintained docBliny fork of the
# cloud client (PyPI's build is stale and no longer logs in):
pip install "git+https://github.com/docBliny/smartblinds-client.git" \
            "git+https://github.com/benbalter/smartblinds-ble.git"

smartblinds-import-cloud            # cloud email/password -> smartblinds-keys.json
```

> If pip errors with `externally-managed-environment`, run it in a venv:
> `python3 -m venv .venv && . .venv/bin/activate` then re-run the install.
> Once this is published to PyPI, the above collapses to `pip install "smartblinds-ble[cloud]"`.

The output holds `{name, mac, key}` per shade and is your **offline insurance** if
the cloud disappears. Keep it safe — it contains secrets (gitignored by default).

> The importer logs into **your own account** to retrieve **your own devices'**
> keys, for interoperability with hardware you own. Use your own credentials, at
> your own risk.

## Why this exists

The motors are ordinary Bluetooth LE devices. The only reason the vendor's hub
exists is to bridge Wi-Fi → cloud → Bluetooth. With the company winding down, that
cloud is a single point of failure that could take your blinds offline. This
project talks to the motors **directly and locally**, so:

- **No hub, no cloud, no account** — everything stays on your LAN.
- Control routes through inexpensive **ESP32 ESPHome Bluetooth Proxies** for
  whole-home coverage, or any Home Assistant Bluetooth adapter.
- Your **MySmartBlinds keep working after the cloud shuts down**.

## How it works

Two layers:

1. **`smartblinds-ble`** (this repo) — a small async, `bleak`-based Python library
   for talking to the motors over BLE.
2. **`ha-smartblinds-ble`** (in progress) — a HACS-installable **Home Assistant**
   integration exposing each shade as an optimistic tilt `cover`, working through
   ESPHome Bluetooth Proxies.

## Two things everyone gets stuck on

- **The per-motor key.** Best: export it from the cloud with `smartblinds-import-cloud`
  (above) while you still can. Offline fallback: brute-force the first byte with
  `smartblinds-find-key`, or sniff the app once. See [`docs/PROTOCOL.md`](docs/PROTOCOL.md).
- **No state feedback.** The motors are open-loop (reads return `0xFF`). Position is
  tracked optimistically; changes made from the app or a physical wand are invisible.

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
    blind = SmartBlind(device, key="2a")   # from the cloud export or find-key
    await blind.set_tilt_percent(50)       # flat-ish

asyncio.run(main())
```

## FAQ

### Is MySmartBlinds / Tilt going out of business?
There's no formal shutdown announcement, but the signals are strong: the operator
(SmarterHome, a Hall Labs subsidiary) is winding down, `tiltsmarthome.com`
permanently redirects to that wind-down page, replacement parts have been
unavailable for a while, and support has gone quiet. The app still received updates
into 2025, so the cloud is alive **for now** — which is exactly why you should
export your keys today.

### Will my blinds stop working if the cloud/app shuts down?
The blinds themselves are local Bluetooth devices, so they don't *need* the cloud —
but the **official app and hub depend on it**, and you need each motor's key to
control it locally. That's what this project (and the key-export tool) is for:
keeping your **MySmartBlinds working after the cloud goes offline**.

### How do I control MySmartBlinds without the hub or the app?
Get each motor's key (cloud export or brute-force), then send BLE commands with
this library — directly from a computer/Raspberry Pi, or through Home Assistant +
an ESP32 Bluetooth Proxy.

### Does this work with Home Assistant?
That's the goal — a local HACS integration (`ha-smartblinds-ble`) exposing each
shade as a tilt `cover`, no cloud bridge. It's in progress and gated on hardware
validation (see the roadmap).

### Do I need an ESP32 / ESPHome Bluetooth Proxy?
Only for range. Any Home Assistant Bluetooth adapter works if it's near the shades;
ESP32 ESPHome Bluetooth Proxies (a few dollars each) extend coverage across a house.

### Does it work with the Tilt app still installed?
Avoid using both at once — the app and this library can fight over position, since
the motors don't report their true state.

## Credits

- [`dnschneid/pysmartblinds`](https://github.com/dnschneid/pysmartblinds) — the
  original reverse engineering (Apache-2.0); this is a modern async port. See
  [`NOTICE`](NOTICE).
- [`ianlevesque/smartblinds-client`](https://github.com/ianlevesque/smartblinds-client)
  and [`docBliny/ha-mysmartblinds`](https://github.com/docBliny/ha-mysmartblinds) —
  the cloud client and (cloud-based) HA integration this borrows the key-export idea from.
- [`LennP/ha-motionblinds_ble`](https://github.com/LennP/ha-motionblinds_ble) — the
  template for the Home Assistant integration layer.

## Keywords

MySmartBlinds · Tilt · Tilt SmartHome · SmarterHome · Hall Labs · smart blinds ·
motorized blinds · local control · no cloud · no hub · cloud shutdown ·
discontinued · Home Assistant · HACS · Bluetooth · BLE · bleak · ESP32 · ESPHome ·
Bluetooth Proxy · retire the hub · keep working after cloud shutdown

## License

[Apache-2.0](LICENSE).
