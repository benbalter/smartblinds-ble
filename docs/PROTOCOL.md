# MySmartBlinds / Tilt BLE protocol (reverse-engineered)

> Clean-room notes. Not affiliated with or endorsed by MySmartBlinds/Tilt.
> Derived from [`dnschneid/pysmartblinds`](https://github.com/dnschneid/pysmartblinds)
> (Apache-2.0) and re-validation on current hardware (Milestone 0).
>
> ⚠️ Everything below is **unverified on current firmware** until M0 passes.

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

## State feedback — there is none

Reads return `0xFF`; the motor does not report its true position. Consequences:

- Position must be **tracked client-side** (optimistic).
- Changes made by the **app, a physical wand, or the schedule are invisible** and
  will be clobbered by the next write.
- The Home Assistant `cover` entity should therefore be **optimistic**.

## Known limitations / open questions for M0

- [ ] Does key auth + position write still work on post-2018 (Tilt-era) firmware?
- [ ] Confirmed handle numbers under bleak (handle numbering can differ) vs UUIDs.
- [ ] The `0x001f` characteristic UUID.
- [ ] Whether newer firmware exposes any *readable* state.
- [ ] Battery level / solar charge characteristic, if any (nice-to-have entity).
- [ ] Behavior with the ESPHome proxy's 3-active-connection limit under load.

---

# Tilt-era (v2 roller shades) — ENCRYPTED, not crackable from captures alone

Everything above is the **legacy** MySmartBlinds protocol. Current **Tilt** roller
shades use a completely different, encrypted BLE protocol. Findings from an iOS
PacketLogger capture parsed with `contrib/parse_pklg.py`:

- **GATT:** client writes to handles `0x0010` and `0x0015`; notifications on
  `0x0012`. HCI ACL exposes plaintext ATT even though the link is encrypted.
- **Framing:** a `00 <seq> …` transport with `00 c0 01 <n>` heartbeats and
  `00 <seq> <hdr> <ciphertext>` data frames (monotonic sequence). A separate
  `2f <op> <seq> <payload>` auth channel, and an `18/19` channel that returns the
  device serial in the clear.
- **Auth handshake:** `→ 2f01<seq>` (start) · `← 2f10<seq> <16B challenge>` ·
  `→ 2f11<seq> <16B response>` · `← 2f02<seq> 00` (ok). 16-byte blocks ⇒ AES.
- **Session:** subsequent frames are high-entropy ciphertext with sequence-number
  nonces ⇒ an AEAD session (CCM/GCM-like).

**Tested** `response == AES-ECB / AES-CMAC(pairingKey, challenge)` for all shade
keys + bridge, 128- and 256-bit, both key halves, both directions, three challenge
paddings → **0 matches**. So the session/auth key is **derived** from the
pairingKey (KDF/handshake/ECDH), not used directly. The cloud `pairingKey` is
necessary but **not sufficient**.

**Conclusion:** local control of Tilt roller shades requires the key-derivation +
command format, which live in the app/firmware — not recoverable by sniffing.
Paths (all major efforts):
1. Reverse the **`TILT_ROLLER_SHADE` firmware** (downloadable from
   `firmware.smarterhome.xyz`) in Ghidra to find the KDF + command encoding.
2. **Frida-hook the Tilt app** crypto (needs an Android emulator or jailbroken iOS).

The legacy library/tools in this repo remain useful for legacy MySmartBlinds
hardware and for cloud key export; the encrypted Tilt path is out of scope until
someone completes the firmware/app RE above.
