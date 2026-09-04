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
