"""Protocol constants for MySmartBlinds/Tilt BLE motors.

Derived from dnschneid/pysmartblinds (Apache-2.0). See NOTICE.

⚠️  UNVERIFIED ON CURRENT HARDWARE.  These values come from reverse-engineering
done ~2018 against firmware 2.0, before the product was rebranded to "Tilt" with
app updates through 2025.  Milestone 0 is to confirm every value below still
holds on a live shade.  Do not treat these as facts until M0 passes.
"""

from __future__ import annotations

#: BLE advertised name used to discover shades during a scan.
DEVICE_NAME: str = "SmartBlind_DFU"

#: These motors advertise with a *random* BLE address, not public.
ADDRESS_TYPE: str = "random"

#: GATT value-attribute handle the multi-byte key is written to.
#: Characteristic UUID is known; the handle may differ under bleak's numbering,
#: so both are recorded — confirm which bleak needs during M0.
KEY_CHAR_HANDLE: int = 0x001B
KEY_CHAR_UUID: str = "00001409-1212-efde-1600-785feabcd123"

#: GATT value-attribute handle a single-byte position is written to.
#: TODO(M0): capture the characteristic UUID for this handle (unknown in the
#: original library, which wrote by raw handle only).
SET_CHAR_HANDLE: int = 0x001F
SET_CHAR_UUID: str | None = None

#: Native tilt range the motor accepts (single unsigned byte).
POSITION_MIN: int = 0
POSITION_MAX: int = 200

#: Key is a tuple of bytes; in practice only the first byte often matters, which
#: is what makes a brute-force first-byte scan (0x00..0xFF) feasible.
KEY_SCAN_FIRST: int = 0x00
KEY_SCAN_LAST: int = 0xFF

#: The library the protocol is derived from was validated only on firmware 2.0.
KNOWN_GOOD_FIRMWARE: str = "2.0"
