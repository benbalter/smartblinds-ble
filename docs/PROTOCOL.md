# MySmartBlinds / Tilt BLE protocol (reverse-engineered)

> Clean-room notes. Not affiliated with or endorsed by MySmartBlinds/Tilt.

**There are two unrelated protocols here, and which one you have depends on your
hardware, not your app version:**

| | Legacy **MySmartBlinds** tilt motors | **Tilt** roller shades |
|---|---|---|
| Advertised name | `SmartBlind_DFU` | `RollerSh` |
| Wire protocol | plaintext GATT writes | encrypted session (AES-128-CTR) |
| Key | short; first byte often suffices | 32-byte `pairingKey` |
| State feedback | none (reads return `0xFF`) | position, battery, charge, calibration |
| Status in this repo | **⚠️ hypothesis, unverified on hardware** — see [ROADMAP.md](ROADMAP.md) M0-L | **implemented and verified on hardware 2026-09-11** |

Part 1 below is the legacy protocol, derived from
[`dnschneid/pysmartblinds`](https://github.com/dnschneid/pysmartblinds) (Apache-2.0).
Nothing in it has been re-confirmed on a current motor; treat every constant as a
guess. Part 2 is the Tilt protocol, which is implemented in
`src/smartblinds_ble/tilt/` and confirmed end-to-end against four shades.

---

# Part 1 — Legacy MySmartBlinds (`SmartBlind_DFU`) — UNVERIFIED

## Discovery

- Motors advertise with BLE name **`SmartBlind_DFU`**.
- They use a **random** BLE address (not public) — relevant when connecting.

## Authentication

Every operation must first write the **key** to the motor:

| What | Value |
|------|-------|
| Handle | `0x001b` |
| Characteristic UUID | `00001409-1212-efde-1600-785feabcd123` |
| Payload | multi-byte key; **in practice only the first byte usually matters** |

Because only the first byte typically matters, the key can be brute-forced by
trying `0x00..0xFF` and seeing which value makes a subsequent position write
"take" (the motor visibly moves). But brute-forcing is a fallback — prefer the
cloud path below, which yields the *full* key.

## Key acquisition (two paths)

1. **Cloud passkey (preferred, while the cloud lives).** The MySmartBlinds/Tilt
   cloud stores each motor's real key. The
   [`ianlevesque`/`docBliny/smartblinds-client`](https://github.com/ianlevesque/smartblinds-client)
   Python library logs in with the account email/password (auth0) and a GraphQL
   query returns, per blind: `encodedMacAddress` and **`encodedPasskey`**
   (base64 → the passkey bytes). One login yields MAC + full key for every shade —
   no brute-forcing, and it explains the "only first byte matters" note above
   (that was a brute-force artifact; the full passkey is retrievable).
   - **TODO(M0): confirm the base64-decoded `encodedPasskey` is exactly the value
     the motor expects at handle `0x001b`.** Strong hypothesis, unproven.
2. **Brute-force first byte (offline fallback).** `smartblinds-find-key` /
   `keyscan()` — works with no account, but only finds a first-byte key and is slow.

## Setting position (tilt)

Immediately after the key, write a **single byte** position:

| What | Value |
|------|-------|
| Handle | `0x001f` |
| Characteristic UUID | **TODO(M0): capture** — original wrote by raw handle only |
| Payload | one byte, **`0` (closed one way) .. `200` (closed the other)**, `100` ≈ flat |

Smooth transitions in the original library are purely client-side: it steps the
byte value over time. There is no native "move to X over N seconds" command.

## State feedback — there is none (legacy only)

Reads return `0xFF`; the legacy motor does not report its true position. Tilt
roller shades *do* report state — see Part 2; do not carry this limitation over.
Consequences for legacy hardware:

- Position must be **tracked client-side** (optimistic).
- Changes made by the **app, a physical wand, or the schedule are invisible** and
  will be clobbered by the next write.
- The Home Assistant `cover` entity should therefore be **optimistic**.

## Known limitations / open questions (legacy hardware)

Open, and only answerable by someone who still owns legacy tilt motors — none
were available to test against:

- [ ] Does key auth + position write still work on post-2018 firmware?
- [ ] Confirmed handle numbers under bleak (handle numbering can differ) vs UUIDs.
- [ ] The `0x001f` characteristic UUID.
- [ ] Whether newer firmware exposes any *readable* state.
- [ ] Battery level / solar charge characteristic, if any.

Answered for Tilt hardware (Part 2), and probably transferable:

- **ESPHome proxy connection limits.** A proxy advertises 3 connection slots by
  default. Brief connect → session → disconnect cycles make four shades workable
  on a single proxy; nothing needs a persistent connection.

---

# Part 2 — Tilt roller shades (`RollerSh`) — IMPLEMENTED & VERIFIED

A completely different protocol from Part 1: an encrypted, ACK'd session layer.
It is **solved**, implemented in `src/smartblinds_ble/tilt/`, and confirmed on
real hardware on 2026-09-11 — four shades authenticated, reported live
position/battery, and moved on command, all routed through an ESPHome Bluetooth
Proxy.

Credit: the codec is vendored byte-for-byte (MIT) from
[`Sunrise-Labs-Dot-AI/tilt-local-bridge`](https://github.com/Sunrise-Labs-Dot-AI/tilt-local-bridge),
which did the reverse engineering that packet captures alone could not (see
"Why sniffing wasn't enough" below). This repo contributes an async `bleak`
transport, Home Assistant proxy routing, and a fake-shade test harness.

## Discovery

- Shades advertise the local name **`RollerSh`** — truncated, so match on a prefix
  (`RollerSh*`), not equality.
- Addresses are BLE **static random** (top two address bits set). They are stable
  across reboots, so they are safe to persist as a device identity. Note that
  macOS/CoreBluetooth hides them behind per-host UUIDs, so identifiers captured on
  a Mac will not match what Linux or Home Assistant reports.

## GATT

| Role | UUID |
|------|------|
| Service | `05960001-d71e-4845-ab02-bf27bb160401` |
| Command (central → shade, write) | `05960002-d71e-4845-ab02-bf27bb160401` |
| Response (shade → central, notify) | `05960003-d71e-4845-ab02-bf27bb160401` |

## Link layer

Messages are chunked to fit the MTU and **acknowledged per chunk in both
directions**, with sequence numbers cycling `1..63`. A chunk header carries an
end-of-message flag; a Bluetooth-layer flag distinguishes ACK frames from data.
Integrity is CRC16/CCITT-FALSE. Both halves of this are exercised by the fake
shade in `tests/tilt_helpers.py`, so a passing test proves the two directions are
byte-compatible.

## Handshake (plaintext)

1. **Request protocol versions** (`0x02`) → shade answers with a version list.
2. **Select version** (`0x03`) → v2.
3. **Request nonce** (`0x0A`) → shade returns a **12-byte nonce** plus a proof of
   key possession.

The proof is:

```
HMAC-SHA256(pairingKey, b"Signed Trogdor string, by Ryjan.")
```

Both sides can compute it, so the shade proving it is what lets the client reject
a wrong key *before* writing anything. A mismatch is an authentication failure,
not a transport error — which is why a wrong key fails immediately and distinctly
from a shade that is merely out of range.

## Application layer (encrypted)

- **Cipher:** AES-128-CTR.
- **Key:** `pairingKey[:16]` — the first half of the 32-byte pairing key.
- **IV:** `nonce(12) || counter(2, big-endian) || 0x0000`. The counter is
  `1..0x7FFF`; shade → central frames set the counter's **high bit**, which keeps
  the two directions' keystreams disjoint.
- **Presentation:** a 4-bit message id plus a response flag, then the command byte
  and payload, checksummed with CRC16 over header + presentation.

### Commands

| Command | Value | Notes |
|---|---|---|
| `ACK` | `0x01` | |
| `GET_VERSION` | `0x04` | |
| `GET_NAME` | `0x05` | |
| `GET_STATUS` | `0x10` | position, battery %, charge status, calibration flag |
| `GET_POSITION` | `0x12` | |
| `SET_POSITION` | `0x13` | position × 10, little-endian, plus a speed byte |
| `GET_BATTERY` | `0x16` | |

Position is **0–1000 on the wire** (0 closed, 1000 open) and exposed as 0–100%.

## State feedback — unlike legacy, there is real state

`GET_STATUS` returns position, battery percent, charge status, and whether the
shade is calibrated. A Home Assistant `cover` for these shades therefore reports
genuine position and **must not** be `assumed_state`.

## Operational notes learned on hardware

- **A position write returns long before the shade arrives.** The motor
  acknowledges and starts moving; travel takes tens of seconds. Nothing in the
  protocol reports "moving", so an in-session read-back a couple of seconds after
  the write will show a position still in transit. Treat *accepted* and *arrived*
  as different states: verify by re-reading later, never by re-sending the
  command. (`smartblinds-ble` ≤ 0.1.0 got this wrong and raised on every
  successful move; fixed in 0.1.1.)
- **One central at a time.** A shade connected to a phone running the Tilt app
  will refuse or drop other connections. Symptoms look exactly like a range
  problem.
- **Range.** Authentication succeeded reliably at −55 to −60 dBm and still worked
  at −85 to −89 dBm, though sustained polling at that level is not something to
  depend on. One proxy per room beats one central proxy.
- **Sessions should be brief.** Connect → authenticate → one operation →
  disconnect. It spares the solar battery, avoids holding a proxy connection slot,
  and leaves the shade reachable from the app.

## Key acquisition

Each shade needs its 32-byte `pairingKey` (64 hex characters). These come from the
Tilt cloud store (`api.tiltsmarthome.com/v2/store/tilt`), where each shade appears
as `{id = BLE MAC, name, pairingKey}`. Use the `access_token` — an `id_token` gets
a 401. Note the Tilt backend shares the `mysmartblinds.auth0.com` tenant with the
legacy cloud but uses a different `client_id`, so a *legacy* login succeeds and
returns zero devices for a Tilt account.

**There is no offline path to these keys.** They cannot be brute-forced (32 bytes)
or sniffed (see below). With the vendor cloud winding down, treat an exported key
as irreplaceable and back it up somewhere durable.

The **Tilt bridge is not a local control path**: it is a cloud-only AWS IoT MQTT
client with every port closed (verified). Direct BLE is the only durable option.

## Why sniffing wasn't enough (historical)

Kept because it explains why the cloud `pairingKey` alone looked insufficient, and
saves anyone else the same dead end. From an iOS PacketLogger capture parsed with
`contrib/parse_pklg.py`:

- **GATT:** writes to handles `0x0010` and `0x0015`; notifications on `0x0012`.
  HCI ACL exposes plaintext ATT even though the link is encrypted.
- **Framing:** a `00 <seq> …` transport with `00 c0 01 <n>` heartbeats and
  `00 <seq> <hdr> <ciphertext>` data frames. A separate `2f <op> <seq> <payload>`
  auth channel, and an `18/19` channel returning the device serial in the clear.
- **Auth handshake:** `→ 2f01<seq>` · `← 2f10<seq> <16B challenge>` ·
  `→ 2f11<seq> <16B response>` · `← 2f02<seq> 00`.

Testing `response == AES-ECB / AES-CMAC(pairingKey, challenge)` across all shade
keys and the bridge, 128- and 256-bit, both key halves, both directions, three
challenge paddings → **0 matches**. The conclusion drawn at the time — that the
auth key must be *derived* from the pairing key and that local control would need
firmware RE in Ghidra or a Frida hook on the app — was right about the derivation
and wrong about the difficulty: the derivation is the HMAC proof above, and
`tilt-local-bridge` had already published it. **Check for prior art before
reaching for a disassembler.**
