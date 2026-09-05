"""Shade-side helpers + an in-memory fake shade for Tilt transport tests.

The fake implements the *peripheral* half of the same reliable, chunked,
ACK-per-frame protocol the real shade speaks, so the production
:class:`TiltShadeClient` (the central) runs unmodified against it with no radio.
The shade-side codec helpers deliberately reuse the library's own crypto/CRC
primitives so a passing test proves the two halves are byte-compatible.
"""

from __future__ import annotations

import asyncio

from smartblinds_ble.tilt import protocol as P

# --- shade-side frame builders (mirror of the library's request encoders) ---


def crypto_frame(command: int, payload: bytes = b"") -> bytes:
    header = P._CRYPTO_LAYER_FLAG.to_bytes(2, "big")
    return P._append_checksum(header, bytes([command]) + payload)


def versions_response(versions: tuple[int, ...]) -> bytes:
    body = bytes([len(versions), *versions])
    return crypto_frame(P.CryptoCommand.REQUEST_PROTOCOL_VERSIONS, body)


def selection_response(version: int) -> bytes:
    return crypto_frame(P.CryptoCommand.SELECT_PROTOCOL_VERSION, bytes([version]))


def nonce_response(nonce: bytes, key: bytes) -> bytes:
    return crypto_frame(P.CryptoCommand.REQUEST_NONCE, nonce + P.pairing_key_proof(key))


def status_payload(raw_position: int, battery: int = 80, charge: int = 0, calibrated: int = 1) -> bytes:
    return raw_position.to_bytes(2, "little") + bytes([battery, charge, calibrated])


def encode_app_response(
    command: int,
    payload: bytes,
    *,
    key: bytes,
    nonce: bytes,
    counter: int,
    message_id: int,
) -> bytes:
    """Encrypt a shade->central application response (RX high bit set in the IV)."""

    header = counter.to_bytes(2, "big")
    presentation = bytes([message_id | P._PRESENTATION_RESPONSE_FLAG, int(command)]) + payload
    plaintext = presentation + P.crc16(header + presentation).to_bytes(2, "little")
    iv = nonce + bytes([header[0] | 0x80, header[1]]) + b"\x00\x00"
    return header + P._aes_ctr(plaintext, key, iv)


def decrypt_app_request(frame: bytes, *, key: bytes, nonce: bytes):
    """Decrypt a central->shade application request into (counter, msg_id, cmd, payload)."""

    header = frame[:2]
    counter = int.from_bytes(header, "big") & P._MAX_COUNTER
    plaintext = P._aes_ctr(frame[2:], key, nonce + header + b"\x00\x00")
    presentation = P._verify_checksum(header, plaintext)
    return counter, presentation[0] & 0x0F, P.ShadeCommand(presentation[1]), presentation[2:]


# --- fake BLE client that behaves like one shade ---


class FakeShadeClient:
    """A bleak-client stand-in that answers as a single Tilt roller shade."""

    def __init__(
        self,
        key: bytes,
        *,
        nonce: bytes = bytes(range(1, 13)),
        start_position: int = 0,
        battery: int = 80,
        versions: tuple[int, ...] = (2, 1),
        proof_key: bytes | None = None,
    ) -> None:
        self._key = key
        self._proof_key = proof_key or key  # differ to simulate a wrong pairing key
        self._nonce = nonce
        self._versions = tuple(versions)
        self.position = start_position  # percent
        self.battery = battery
        self.is_connected = False
        self.set_position_calls = 0
        self._notify = None
        self._assembler = P.BleMessageAssembler()
        self._tx_seq = 1
        self._ack_waiters: dict[int, asyncio.Future] = {}

    # bleak surface used by the transport ------------------------------------

    async def connect(self) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False

    async def start_notify(self, _uuid, callback) -> None:
        self._notify = callback
        self._assembler = P.BleMessageAssembler()
        self._tx_seq = 1
        self._ack_waiters = {}

    def stop_notify(self, _uuid) -> None:  # transport tolerates sync or async
        self._notify = None

    async def write_gatt_char(self, _uuid, data, *_, **__) -> None:
        chunk = P.parse_ble_chunk(bytes(data))
        if chunk.for_bluetooth_layer:
            seq = P.parse_ble_ack(bytes(data))
            waiter = self._ack_waiters.get(seq)
            if waiter is not None and not waiter.done():
                waiter.set_result(None)
            return
        self._emit(P.make_ble_ack(chunk.sequence))
        _, message = self._assembler.add(bytes(data))
        if message is not None:
            asyncio.create_task(self._handle_request(message))

    # peripheral behaviour ----------------------------------------------------

    def _emit(self, data: bytes) -> None:
        assert self._notify is not None, "shade emitted before start_notify"
        self._notify(None, bytearray(data))

    async def _send_frame(self, frame: bytes) -> None:
        for chunk in P.chunk_for_ble(frame, start_sequence=self._tx_seq):
            seq = chunk[1] & 0x3F
            waiter = asyncio.get_running_loop().create_future()
            self._ack_waiters[seq] = waiter
            self._emit(chunk)
            await asyncio.wait_for(waiter, timeout=2.0)
            self._tx_seq = P.next_sequence(seq)

    async def _handle_request(self, frame: bytes) -> None:
        if int.from_bytes(frame[:2], "big") & P._CRYPTO_LAYER_FLAG:
            response = self._handle_crypto(frame)
        else:
            response = self._handle_app(frame)
        await self._send_frame(response)

    def _handle_crypto(self, frame: bytes) -> bytes:
        request = P.parse_crypto_response(frame)
        if request.command is P.CryptoCommand.REQUEST_PROTOCOL_VERSIONS:
            return versions_response(self._versions)
        if request.command is P.CryptoCommand.SELECT_PROTOCOL_VERSION:
            return selection_response(request.payload[0])
        if request.command is P.CryptoCommand.REQUEST_NONCE:
            return nonce_response(self._nonce, self._proof_key)
        raise AssertionError(f"unexpected crypto command {request.command!r}")

    def _handle_app(self, frame: bytes) -> bytes:
        counter, message_id, command, payload = decrypt_app_request(
            frame, key=self._key, nonce=self._nonce
        )
        if command is P.ShadeCommand.SET_POSITION:
            self.position = int.from_bytes(payload[:2], "little") // 10
            self.set_position_calls += 1
            body = b""
        elif command is P.ShadeCommand.GET_STATUS:
            body = status_payload(self.position * 10, self.battery)
        elif command is P.ShadeCommand.GET_BATTERY:
            body = bytes([self.battery, 0])
        else:
            raise AssertionError(f"unexpected shade command {command!r}")
        return encode_app_response(
            command, body, key=self._key, nonce=self._nonce, counter=counter, message_id=message_id
        )
