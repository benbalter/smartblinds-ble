# Capturing the Tilt / MySmartBlinds protocol

Field notes for reverse-engineering current **Tilt**-era hardware (roller shades +
bridge). Written from a real capture session; save yourself the dead ends.

> **The Tilt shade protocol no longer needs capturing** — it is solved,
> implemented, and verified on hardware; see [PROTOCOL.md](PROTOCOL.md) Part 2.
> What remains useful here: a **fallback** route to the pairing keys when the
> scripted export cannot log in, the proof that the bridge is not a local control
> path, and the method itself if you are chasing a *different* device. The one
> lesson worth carrying: the answer was already published by another project, and
> capturing came first only because nobody checked.

## The two control paths (and which one to target)

| Path | Transport | Durable? | Use it for |
|------|-----------|----------|------------|
| **Direct BLE** (phone ↔ shade, BT on, in range) | Bluetooth LE | ✅ local, survives cloud + bridge death | **This is the target.** |
| Bridge (BT off / remote) | phone → **AWS IoT Core MQTT** → bridge → BLE | ❌ cloud-relayed | nothing — see below |

**Do not chase the bridge for local control.** Observed on a live setup:
- The bridge is an Espressif device that connects *outbound* to an AWS IoT endpoint
  (`*-ats.iot.<region>.amazonaws.com`, MQTT/TLS 8883) — visible in the router's
  traffic log, invisible to an HTTP proxy.
- `nmap` of the bridge shows **all TCP + UDP ports closed** — no local API.
- So commands round-trip through AWS even on the same LAN, and you can't publish to
  it without the bridge's provisioned X.509 device cert. Dead end.

## Route A — network MITM (fallback for key export)

> **Try `smartblinds-import-tilt` first.** The login this capture revealed is now
> implemented (`tilt_cloud.py`), so an email and a password export every shade's
> key with no proxy, no CA trust, and no phone. Come back here only if that fails:
> an MFA-enabled account, or Auth0 attack protection blocking a password grant.
> Then capture an `access_token` below and pass it with `--access-token`.

Reveals the Tilt cloud "store": rooms, `rollerShades[]`, `bridges[]`, each with a
32-byte `pairingKey`, where **`id` is the device's BLE MAC**. Auth is
`mysmartblinds.auth0.com` (`/oauth/token`); data is `api.tiltsmarthome.com/v2/store/tilt`.

1. `brew install mitmproxy`, then `mitmdump -s contrib/mitm_tilt_addon.py`.
2. iPhone → Wi-Fi → Configure Proxy → Manual → `<mac-ip>:8080`.
3. Trust the CA: AirDrop `~/.mitmproxy/mitmproxy-ca-cert.pem` to the phone, install
   it, then **Settings → General → About → Certificate Trust Settings → enable it**
   (the step everyone misses). `mitm.it` only works *through* the proxy — a GitHub
   404 there means traffic isn't being intercepted.
4. Log out / log in in the Tilt app → the full store (with pairingKeys) is returned.
   The addon writes redacted JSON to `tilt-capture/`.

No cert pinning was observed on the Tilt app as of this writing.

## Route B — iOS BLE HCI capture (the durable path)

Decodes how the `pairingKey` authenticates and how position is written over GATT.
BLE isn't HTTP, so mitmproxy can't see it — you need a Bluetooth HCI trace.

1. **iPhone:** install Apple's **Bluetooth logging profile**
   (developer.apple.com → Bug Reporting → Profiles and Logs → "Bluetooth"), then
   **reboot** (required for logging to start).
2. **Mac:** install **PacketLogger** (Apple's "Additional Tools for Xcode", Hardware
   folder).
3. Tether the iPhone via USB, trust the Mac.
4. In PacketLogger, start a capture **from the connected iOS device**.
5. Bluetooth **on**, phone near a shade, move **one** shade open→close a few times.
6. Stop, save the `.pklg`.
7. Open in Wireshark (`btatt` filter): find the connection, the key handshake, and
   the position writes. A 32-byte key suggests the Tilt-era BLE is
   encrypted/authenticated (not the legacy plaintext `0x001b`/`0x001f`).

## Redaction

`contrib/mitm_tilt_addon.py` masks values of key/token/secret/password fields (and
those headers) but keeps structure, MACs, ids, names, and positions — so a
`tilt-capture/*.json` is safe to share. BLE `.pklg` traces contain the pairingKey
in the clear once decoded — treat them as secret.
