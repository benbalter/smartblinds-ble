"""Unit tests for the vendored Tilt codec (transport-free, no radio)."""

from __future__ import annotations

import pytest
import tilt_helpers as H

from smartblinds_ble.tilt import protocol as P

KEY = bytes(range(32))
NONCE = bytes(range(1, 13))


# --- CRC16 -----------------------------------------------------------------


def test_crc16_matches_ccitt_false_check_vector():
    # 0x29B1 is the canonical CRC-16/CCITT-FALSE check value for "123456789".
    assert P.crc16(b"123456789") == 0x29B1


def test_crc16_is_deterministic_and_bounded():
    assert P.crc16(b"") == 0xFFFF
    assert 0 <= P.crc16(b"tilt") <= 0xFFFF
    assert P.crc16(b"abc") == P.crc16(b"abc")


# --- BLE chunk / reassembly layer ------------------------------------------


def test_chunk_and_reassemble_multichunk_roundtrip():
    frame = bytes(range(40))  # 40 > 18*2 -> three chunks (18, 18, 4)
    chunks = P.chunk_for_ble(frame, start_sequence=1)
    assert len(chunks) == 3
    assembler = P.BleMessageAssembler()
    message = None
    for index, raw in enumerate(chunks):
        chunk = P.parse_ble_chunk(raw)
        assert chunk.sequence == index + 1
        assert chunk.end_of_message is (index == len(chunks) - 1)
        assert not chunk.for_bluetooth_layer
        acknowledged, message = assembler.add(raw)
        assert acknowledged == index + 1
    assert message == frame


def test_single_chunk_sets_end_of_message():
    (only,) = P.chunk_for_ble(b"hi", start_sequence=1)
    chunk = P.parse_ble_chunk(only)
    assert chunk.end_of_message and chunk.sequence == 1 and chunk.payload == b"hi"


def test_ble_ack_roundtrip_and_rejects_data_chunk():
    assert P.parse_ble_ack(P.make_ble_ack(5)) == 5
    (data_chunk,) = P.chunk_for_ble(b"x", start_sequence=1)
    with pytest.raises(P.TiltProtocolError):
        P.parse_ble_ack(data_chunk)


def test_next_sequence_wraps_at_63():
    assert P.next_sequence(1) == 2
    assert P.next_sequence(63) == 1
    for bad in (0, 64):
        with pytest.raises(P.TiltProtocolError):
            P.next_sequence(bad)


@pytest.mark.parametrize(
    "raw",
    [
        b"\x01\x41",              # first byte must be 0
        b"\x00\x40",              # sequence 0 on a non-bluetooth chunk
        b"\x00\x41" + bytes(19),  # payload exceeds the 18-byte limit
    ],
)
def test_parse_ble_chunk_rejects_malformed(raw):
    with pytest.raises(P.TiltProtocolError):
        P.parse_ble_chunk(raw)


def test_assembler_rejects_noncontiguous_sequence():
    assembler = P.BleMessageAssembler()
    chunks = P.chunk_for_ble(bytes(range(40)), start_sequence=1)
    assembler.add(chunks[0])
    with pytest.raises(P.TiltProtocolError):
        assembler.add(chunks[2])  # skipped chunk 2


# --- crypto handshake layer ------------------------------------------------


def test_protocol_versions_response_parses():
    response = P.parse_crypto_response(H.versions_response((2, 1)))
    assert response.command is P.CryptoCommand.REQUEST_PROTOCOL_VERSIONS
    assert P.parse_protocol_versions(response) == (2, 1)


def test_protocol_selection_rejects_unsupported_version():
    with pytest.raises(P.UnsafeCommandError):
        P.encode_protocol_selection(9)


def test_nonce_response_parses_and_authenticates():
    response = P.parse_crypto_response(H.nonce_response(NONCE, KEY))
    parsed = P.parse_nonce_response(response)
    assert parsed.nonce == NONCE
    assert P.pairing_key_matches_proof(KEY, parsed.key_proof)


def test_nonce_response_wrong_length_rejected():
    bad = H.crypto_frame(P.CryptoCommand.REQUEST_NONCE, bytes(43))
    with pytest.raises(P.TiltProtocolError):
        P.parse_nonce_response(P.parse_crypto_response(bad))


def test_checksum_mismatch_raises_authentication_error():
    frame = bytearray(H.versions_response((2, 1)))
    frame[3] ^= 0xFF  # corrupt a payload byte, leave the trailing checksum intact
    with pytest.raises(P.AuthenticationError):
        P.parse_crypto_response(bytes(frame))


# --- pairing-key proof -----------------------------------------------------


def test_pairing_key_proof_matches_only_correct_key():
    proof = P.pairing_key_proof(KEY)
    assert P.pairing_key_matches_proof(KEY, proof)
    assert not P.pairing_key_matches_proof(bytes(range(1, 33)), proof)


def test_pairing_key_proof_requires_32_bytes():
    with pytest.raises(P.TiltProtocolError):
        P.pairing_key_proof(bytes(16))


# --- application request encoders -------------------------------------------


def test_read_request_roundtrips_through_decrypt():
    frame = P.encode_read_request(
        P.ShadeCommand.GET_STATUS, key=KEY, nonce=NONCE, counter=7, message_id=3
    )
    counter, message_id, command, payload = H.decrypt_app_request(frame, key=KEY, nonce=NONCE)
    assert (counter, message_id, command, payload) == (7, 3, P.ShadeCommand.GET_STATUS, b"")


def test_position_request_encodes_raw_position_and_speed():
    frame = P.encode_position_request(40, key=KEY, nonce=NONCE, counter=1, message_id=1, speed=55)
    _, _, command, payload = H.decrypt_app_request(frame, key=KEY, nonce=NONCE)
    assert command is P.ShadeCommand.SET_POSITION
    assert int.from_bytes(payload[:2], "little") == 400  # 40% * 10
    assert payload[2] == 55


def test_read_request_rejects_write_command():
    with pytest.raises(P.UnsafeCommandError):
        P.encode_read_request(P.ShadeCommand.SET_POSITION, key=KEY, nonce=NONCE)


@pytest.mark.parametrize("position", [-1, 101, True])
def test_position_request_rejects_bad_position(position):
    with pytest.raises(P.TiltProtocolError):
        P.encode_position_request(position, key=KEY, nonce=NONCE)


@pytest.mark.parametrize("speed", [0, 101])
def test_position_request_rejects_bad_speed(speed):
    with pytest.raises(P.TiltProtocolError):
        P.encode_position_request(50, key=KEY, nonce=NONCE, speed=speed)


@pytest.mark.parametrize("counter", [0, 0x8000])
def test_request_rejects_out_of_range_counter(counter):
    with pytest.raises(P.TiltProtocolError):
        P.encode_read_request(P.ShadeCommand.GET_STATUS, key=KEY, nonce=NONCE, counter=counter)


def test_request_requires_12_byte_nonce():
    with pytest.raises(P.TiltProtocolError):
        P.encode_read_request(P.ShadeCommand.GET_STATUS, key=KEY, nonce=bytes(8))


# --- application response decoding ------------------------------------------


def test_status_response_decodes_and_parses():
    response = H.encode_app_response(
        P.ShadeCommand.GET_STATUS,
        H.status_payload(500, battery=77, charge=1, calibrated=1),
        key=KEY,
        nonce=NONCE,
        counter=7,
        message_id=3,
    )
    decoded = P.decode_application_response(
        response,
        key=KEY,
        nonce=NONCE,
        expected_command=P.ShadeCommand.GET_STATUS,
        expected_message_id=3,
        expected_counter=7,
    )
    status = P.parse_status(decoded)
    assert status.position_percent == 50
    assert status.battery_percent == 77
    assert status.charge_status == 1
    assert status.calibrated is True


def test_ack_response_is_accepted_for_expected_command():
    response = H.encode_app_response(
        P.ShadeCommand.ACK,
        bytes([P.ShadeCommand.SET_POSITION]),
        key=KEY,
        nonce=NONCE,
        counter=2,
        message_id=2,
    )
    decoded = P.decode_application_response(
        response,
        key=KEY,
        nonce=NONCE,
        expected_command=P.ShadeCommand.SET_POSITION,
        expected_message_id=2,
        expected_counter=2,
    )
    assert decoded.command is P.ShadeCommand.ACK


def _status_response(**overrides):
    fields = {"counter": 7, "message_id": 3}
    fields.update(overrides)
    return H.encode_app_response(
        P.ShadeCommand.GET_STATUS,
        H.status_payload(500),
        key=KEY,
        nonce=NONCE,
        **fields,
    )


@pytest.mark.parametrize(
    "expected",
    [
        {"expected_message_id": 4},                       # message id mismatch
        {"expected_counter": 8},                          # counter mismatch
        {"expected_command": P.ShadeCommand.GET_BATTERY},  # command mismatch
    ],
)
def test_decode_rejects_mismatched_response(expected):
    response = _status_response()
    kwargs = {
        "key": KEY,
        "nonce": NONCE,
        "expected_command": P.ShadeCommand.GET_STATUS,
        "expected_message_id": 3,
        "expected_counter": 7,
    }
    kwargs.update(expected)
    with pytest.raises(P.TiltProtocolError):
        P.decode_application_response(response, **kwargs)


def test_decode_rejects_crypto_layer_frame():
    with pytest.raises(P.TiltProtocolError):
        P.decode_application_response(
            H.versions_response((2, 1)),
            key=KEY,
            nonce=NONCE,
            expected_command=P.ShadeCommand.GET_STATUS,
            expected_message_id=1,
        )


# --- status / battery / position parsing -----------------------------------


def test_parse_status_rejects_impossible_battery():
    response = P.decode_application_response(
        H.encode_app_response(
            P.ShadeCommand.GET_STATUS,
            H.status_payload(500, battery=200),
            key=KEY,
            nonce=NONCE,
            counter=1,
            message_id=1,
        ),
        key=KEY,
        nonce=NONCE,
        expected_command=P.ShadeCommand.GET_STATUS,
        expected_message_id=1,
        expected_counter=1,
    )
    with pytest.raises(P.TiltProtocolError):
        P.parse_status(response)


def test_parse_status_rejects_wrong_length():
    response = P.decode_application_response(
        H.encode_app_response(
            P.ShadeCommand.GET_STATUS,
            b"\x00\x00\x50",  # only three bytes, needs five
            key=KEY,
            nonce=NONCE,
            counter=1,
            message_id=1,
        ),
        key=KEY,
        nonce=NONCE,
        expected_command=P.ShadeCommand.GET_STATUS,
        expected_message_id=1,
        expected_counter=1,
    )
    with pytest.raises(P.TiltProtocolError):
        P.parse_status(response)


@pytest.mark.parametrize(
    ("raw", "percent"),
    [(0, 0), (504, 50), (506, 51), (1000, 100)],
)
def test_raw_position_to_percent(raw, percent):
    assert P.raw_position_to_percent(raw) == percent


@pytest.mark.parametrize("raw", [-1, 1001, True])
def test_raw_position_to_percent_rejects_out_of_range(raw):
    with pytest.raises(P.TiltProtocolError):
        P.raw_position_to_percent(raw)
