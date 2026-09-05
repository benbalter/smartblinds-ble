"""Local BLE control of Tilt / SmarterHome roller shades (encrypted protocol).

This is the Tilt-era protocol (32-byte pairing key, AES-128-CTR session), distinct
from the legacy MySmartBlinds 1-byte-key protocol in :mod:`smartblinds_ble.blind`.
The codec is vendored byte-for-byte from the MIT-licensed
``Sunrise-Labs-Dot-AI/tilt-local-bridge`` project (see ``NOTICE``); the transport
is adapted to take a MAC + pairing key directly so it can run under any bleak
backend, including Home Assistant's ``habluetooth`` routing over an ESP32 ESPHome
Bluetooth Proxy.
"""

from __future__ import annotations

from .ble import (
    AmbiguousPositionWrite,
    PositionVerificationPending,
    TiltBleCleanupError,
    TiltBleError,
    TiltBleTimeout,
    TiltShadeClient,
)
from .protocol import (
    AuthenticationError,
    ShadeCommand,
    ShadeStatus,
    TiltProtocolError,
    UnsafeCommandError,
    raw_position_to_percent,
)

__all__ = [
    "AmbiguousPositionWrite",
    "AuthenticationError",
    "PositionVerificationPending",
    "ShadeCommand",
    "ShadeStatus",
    "TiltBleCleanupError",
    "TiltBleError",
    "TiltBleTimeout",
    "TiltProtocolError",
    "TiltShadeClient",
    "UnsafeCommandError",
    "raw_position_to_percent",
]
