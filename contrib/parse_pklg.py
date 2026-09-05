#!/usr/bin/env python3
"""Parse an Apple PacketLogger (.pklg) BLE HCI trace into an ATT transcript.

    python3 contrib/parse_pklg.py capture.pklg [--handle-map] [--all]

HCI ACL frames carry plaintext ATT even on an encrypted BLE link (the controller
decrypts on RX / encrypts on TX), so this reveals the GATT writes/reads/notifies
regardless of pairing. Used to reverse the Tilt roller-shade protocol: find the
pairingKey write + any challenge/response + the position write.

No dependencies. PacketLogger record: u32be len | u32be secs | u32be usecs | u8
type | payload(len-9). ACL types are 0x02 (sent, phone->device) and 0x03 (recv).
"""

from __future__ import annotations

import struct
import sys

ATT_CID = 0x0004
SMP_CID = 0x0006

ATT_OPS = {
    0x01: "ERROR_RSP",
    0x02: "MTU_REQ",
    0x03: "MTU_RSP",
    0x04: "FIND_INFO_REQ",
    0x05: "FIND_INFO_RSP",
    0x06: "FIND_BY_TYPE_REQ",
    0x07: "FIND_BY_TYPE_RSP",
    0x08: "READ_BY_TYPE_REQ",
    0x09: "READ_BY_TYPE_RSP",
    0x0A: "READ_REQ",
    0x0B: "READ_RSP",
    0x0C: "READ_BLOB_REQ",
    0x0D: "READ_BLOB_RSP",
    0x10: "READ_BY_GROUP_REQ",
    0x11: "READ_BY_GROUP_RSP",
    0x12: "WRITE_REQ",
    0x13: "WRITE_RSP",
    0x16: "PREPARE_WRITE_REQ",
    0x17: "PREPARE_WRITE_RSP",
    0x18: "EXEC_WRITE_REQ",
    0x19: "EXEC_WRITE_RSP",
    0x1B: "NOTIFY",
    0x1D: "INDICATE",
    0x1E: "CONFIRM",
    0x52: "WRITE_CMD",
    0xD2: "SIGNED_WRITE_CMD",
}

# ATT ops that carry (handle, value).
HANDLE_VALUE_OPS = {0x12, 0x52, 0x1B, 0x1D, 0xD2}
HANDLE_ONLY_OPS = {0x0A, 0x0C}  # read req / read blob req (handle, no value)
VALUE_ONLY_OPS = {0x0B, 0x0D}  # read rsp / read blob rsp (value, no handle)


def records(buf: bytes):
    pos, n = 0, len(buf)
    while pos + 13 <= n:
        (length,) = struct.unpack_from("<I", buf, pos)
        if length < 9 or pos + 4 + length > n:
            break
        ptype = buf[pos + 12]
        payload = buf[pos + 13 : pos + 4 + length]
        yield ptype, payload
        pos += 4 + length


def att_from_acl(payload: bytes, reasm: dict) -> bytes | None:
    """Return a complete ATT PDU from an ACL fragment, handling reassembly."""
    if len(payload) < 4:
        return None
    handle_flags, acl_len = struct.unpack_from("<HH", payload, 0)
    conn = handle_flags & 0x0FFF
    pb = (handle_flags >> 12) & 0x3
    data = payload[4 : 4 + acl_len]
    if pb == 0x1:  # continuation
        buf = reasm.get(conn)
        if buf is None:
            return None
        buf["data"] += data
    else:  # start (0x2 for LE, sometimes 0x0)
        if len(data) < 4:
            return None
        l2_len, cid = struct.unpack_from("<HH", data, 0)
        reasm[conn] = {"cid": cid, "need": l2_len, "data": data[4:]}
        buf = reasm[conn]
    if len(buf["data"]) >= buf["need"]:
        if buf["cid"] == ATT_CID:
            pdu = buf["data"][: buf["need"]]
        elif buf["cid"] == SMP_CID:
            pdu = b"\x00SMP:" + buf["data"][: buf["need"]]  # tag SMP so caller notes it
        else:
            pdu = None
        reasm.pop(conn, None)
        return pdu
    return None


def hx(b: bytes) -> str:
    return b.hex()


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        sys.exit("usage: parse_pklg.py capture.pklg [--all]")
    with open(args[0], "rb") as fh:
        buf = fh.read()

    reasm_tx: dict = {}
    reasm_rx: dict = {}
    types: dict[int, int] = {}
    att_count = 0
    handle_lens: dict[int, set] = {}

    for ptype, payload in records(buf):
        types[ptype] = types.get(ptype, 0) + 1
        if ptype not in (0x02, 0x03):
            continue
        direction = "→" if ptype == 0x02 else "←"  # → sent (phone->device)
        pdu = att_from_acl(payload, reasm_tx if ptype == 0x02 else reasm_rx)
        if not pdu:
            continue
        if pdu.startswith(b"\x00SMP:"):
            print(f"{direction} SMP  {hx(pdu[5:])}")
            continue
        op = pdu[0]
        name = ATT_OPS.get(op, f"0x{op:02x}")
        rest = pdu[1:]
        line = f"{direction} {name:<18}"
        if op in HANDLE_VALUE_OPS and len(rest) >= 2:
            (h,) = struct.unpack_from("<H", rest, 0)
            val = rest[2:]
            handle_lens.setdefault(h, set()).add(len(val))
            line += f" handle=0x{h:04x} len={len(val):<3} {hx(val)}"
            if len(val) <= 4:
                line += f"  (int={int.from_bytes(val, 'little')})"
        elif op in HANDLE_ONLY_OPS and len(rest) >= 2:
            (h,) = struct.unpack_from("<H", rest, 0)
            line += f" handle=0x{h:04x}"
        elif op in VALUE_ONLY_OPS:
            line += f" len={len(rest):<3} {hx(rest)}"
        elif op in (0x02, 0x03) and len(rest) >= 2:  # MTU req/rsp
            line += f" mtu={struct.unpack_from('<H', rest, 0)[0]}"
        else:
            line += f" {hx(rest)}"
        att_count += 1
        # By default only show the interesting ops; --all shows everything.
        interesting = op in (0x12, 0x52, 0x0A, 0x0B, 0x1B, 0x1D, 0xD2, 0x0C, 0x0D)
        if interesting or "--all" in flags:
            print(line)

    print("\n=== summary ===")
    print("record types:", {f"0x{k:02x}": v for k, v in sorted(types.items())})
    print("total ATT PDUs:", att_count)
    print("handles written/notified (handle: value-lengths seen):")
    for h in sorted(handle_lens):
        print(f"  0x{h:04x}: {sorted(handle_lens[h])}")


if __name__ == "__main__":
    main()
