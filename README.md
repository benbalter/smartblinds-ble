# smartblinds-ble — local control for MySmartBlinds / Tilt smart blinds (no hub, no cloud)

[![CI](https://github.com/benbalter/smartblinds-ble/actions/workflows/ci.yml/badge.svg)](https://github.com/benbalter/smartblinds-ble/actions/workflows/ci.yml)

Keep your **MySmartBlinds / Tilt motorized blinds** working **even after the cloud
shuts down**. `smartblinds-ble` controls the shade motors **locally over Bluetooth
LE** — **no proprietary hub, no cloud account, no phone app required** — and is
built to run through **Home Assistant** and cheap **ESP32 / ESPHome Bluetooth
Proxies**.

> **Status depends on which hardware you own** — the two generations share a brand
> and nothing else ([details](docs/PROTOCOL.md)):
>
> - **Tilt roller shades** (advertise `RollerSh`) — **working.** The encrypted
>   protocol is implemented and verified on hardware: four shades authenticate,
>   report live position and battery, and move on command through an ESPHome
>   Bluetooth Proxy. Paired with the
>   [`ha-smartblinds-ble`](https://github.com/benbalter/ha-smartblinds-ble) Home
>   Assistant integration.
> - **Legacy MySmartBlinds tilt motors** (advertise `SmartBlind_DFU`) —
>   **unverified.** That protocol comes from 2018 reverse engineering and has never
>   been confirmed on a real motor; the constants are a labelled hypothesis. See
>   [`docs/ROADMAP.md`](docs/ROADMAP.md) (M0-L). The **cloud key-export tool below
>   works today**, independent of that.
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
# The cloud client must come from the maintained docBliny fork — PyPI's build is
# stale and no longer logs in, so a git URL can't be pinned in a published extra:
pip install smartblinds-ble "git+https://github.com/docBliny/smartblinds-client.git"

smartblinds-import-cloud            # cloud email/password -> smartblinds-keys.json
```

> If pip errors with `externally-managed-environment`, run it in a venv:
> `python3 -m venv .venv && . .venv/bin/activate` then re-run the install.

The output holds `{name, mac, key}` per shade and is your **offline insurance** if
the cloud disappears. Keep it safe — it contains secrets (gitignored by default).

> **Legacy app only.** This exports from the *legacy MySmartBlinds* cloud. If you
> set your shades up in the newer **Tilt** app, they live in a separate backend and
> won't appear here (login works but returns zero blinds). In that case, skip the
> cloud and read the key directly over BLE with `smartblinds-find-key`.

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
2. **[`ha-smartblinds-ble`](https://github.com/benbalter/ha-smartblinds-ble)** — a
   HACS-installable **Home Assistant** integration exposing each shade as a
   position `cover` plus a battery `sensor`, routed through ESPHome Bluetooth
   Proxies.

## Things everyone gets stuck on

- **The per-shade key.** *Legacy:* export it from the cloud with
  `smartblinds-import-cloud` (above) while you still can; offline fallback is
  brute-forcing the first byte with `smartblinds-find-key`. *Tilt:* the 32-byte
  `pairingKey` lives in the Tilt cloud store and **cannot** be brute-forced or
  sniffed — get it out before the cloud dies, and back it up, because there is no
  second chance. See [`docs/PROTOCOL.md`](docs/PROTOCOL.md).
- **State feedback differs by generation.** Tilt roller shades report real
  position, battery, and charge state. Legacy motors are open-loop (reads return
  `0xFF`), so their position is tracked optimistically and changes made from the
  app or a physical wand are invisible.
- **A position write returns before the shade arrives.** The motor acknowledges
  and starts moving; travel takes tens of seconds. Verify by re-reading later —
  never by re-sending the command.
- **Failed connections leak proxy connection slots.** An ESPHome proxy has three.
  Connect through `bleak_retry_connector.establish_connection()` (see the
  `client_factory` example below) rather than letting `bleak` connect directly, or
  a run of failed attempts will eventually take the proxy down for every shade
  behind it.

## Quick start (bring-up, local adapter)

```bash
pip install smartblinds-ble     # or: pip install -e ".[dev]" to hack on it
pytest                          # protocol/encoding tests against a fake shade
```

**Tilt roller shades** (verified path) — needs the shade's MAC and its 64-hex
pairing key:

```python
import asyncio
from smartblinds_ble.tilt import TiltShadeClient

MAC = "AA:BB:CC:DD:EE:FF"  # the shade's BLE MAC — its `id` in the Tilt cloud store
KEY = bytes.fromhex("<64 hex characters from the Tilt cloud store>")

async def main():
    status = await TiltShadeClient(MAC, KEY).read_status()
    print(status.position_percent, status.battery_percent)

    # Movement is opt-in. The call returns once the shade has accepted the
    # command and started moving — tens of seconds before it arrives.
    mover = TiltShadeClient(MAC, KEY, allow_position_writes=True)
    await mover.set_position_and_read_status(100)

asyncio.run(main())
```

### Hand off connection establishment (required behind a proxy)

Don't let the library open the connection itself. Pass a `client_factory` that
connects via
[`bleak_retry_connector`](https://github.com/Bluetooth-Devices/bleak-retry-connector),
which retries through proxies and — the part that bites — releases the proxy
connection slot when an attempt fails. An ESPHome proxy has only three, and leaked
slots take it down for every shade behind it.

The factory needs a **`BLEDevice`**, not a bare address: that object is what
carries the route to the proxy that can actually reach the shade. Home Assistant
supplies it; a local scan cannot produce one for a remote proxy.

```python
from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth

async def read_through_proxy(hass, mac, key):
    # HA resolves the address to a BLEDevice via whichever proxy hears the shade.
    device = bluetooth.async_ble_device_from_address(hass, mac, connectable=True)

    async def factory(address, *, timeout, **_kwargs):
        return await establish_connection(BleakClient, device, address)

    return await TiltShadeClient(mac, key, client_factory=factory).read_status()
```

Off Home Assistant, on a host whose own adapter is in range, the same factory
works with a locally scanned device
(`await BleakScanner.find_device_by_address(MAC)`) — that path is a local
connection, not a proxied one. See `contrib/gate_auth_mac.py` for a runnable
example.

The factory may be sync or async, and may hand back an **already connected**
client — the library awaits it when it is awaitable and skips `connect()` when it
is already connected (0.1.2+). This is how the Home Assistant integration routes
every session through ESPHome proxies.

**Legacy tilt motors** (unverified — constants are a hypothesis):

```bash
smartblinds-find-key            # scan + brute-force keys for nearby motors
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
Yes, for Tilt roller shades:
[`ha-smartblinds-ble`](https://github.com/benbalter/ha-smartblinds-ble) is a HACS
custom repository that gives each shade a position `cover` and a battery `sensor`,
with no cloud bridge. Legacy motors are not supported there yet — that waits on
M0-L in the roadmap.

### Do I need an ESP32 / ESPHome Bluetooth Proxy?
Only for range. Any Home Assistant Bluetooth adapter works if it's near the shades;
ESP32 ESPHome Bluetooth Proxies (a few dollars each) extend coverage across a house.

### Does it work with the Tilt app still installed?
Installed, yes; connected at the same time, no. A shade accepts **one central at a
time**, so a phone with the app open in the same room will make Home Assistant's
connections fail in a way that looks exactly like a range problem. Force-quit the
app when handing control over. (Tilt shades do report real position, so the two
won't disagree about state the way legacy motors would — they just can't share the
radio link.)

## Credits

- [`dnschneid/pysmartblinds`](https://github.com/dnschneid/pysmartblinds) — the
  original reverse engineering (Apache-2.0); this is a modern async port. See
  [`NOTICE`](NOTICE).
- [`ianlevesque/smartblinds-client`](https://github.com/ianlevesque/smartblinds-client)
  and [`docBliny/ha-mysmartblinds`](https://github.com/docBliny/ha-mysmartblinds) —
  the cloud client and (cloud-based) HA integration this borrows the key-export idea from.
- [`Sunrise-Labs-Dot-AI/tilt-local-bridge`](https://github.com/Sunrise-Labs-Dot-AI/tilt-local-bridge)
  — reverse engineered the **encrypted Tilt roller-shade protocol**, which packet
  captures alone could not yield. Its codec is vendored here byte-for-byte (MIT);
  this repo adds an async `bleak` transport, proxy routing, and a test harness.
- [`LennP/ha-motionblinds_ble`](https://github.com/LennP/ha-motionblinds_ble) — the
  template for the Home Assistant integration layer.

## Keywords

MySmartBlinds · Tilt · Tilt SmartHome · SmarterHome · Hall Labs · smart blinds ·
motorized blinds · local control · no cloud · no hub · cloud shutdown ·
discontinued · Home Assistant · HACS · Bluetooth · BLE · bleak · ESP32 · ESPHome ·
Bluetooth Proxy · retire the hub · keep working after cloud shutdown

## License

[Apache-2.0](LICENSE).
