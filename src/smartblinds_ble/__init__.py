"""smartblinds-ble: local, hub-free async BLE control of MySmartBlinds/Tilt motors.

Not affiliated with nor endorsed by MySmartBlinds or Tilt. Protocol derived by
clean-room reverse engineering (see docs/PROTOCOL.md and NOTICE).
"""

from __future__ import annotations

from .blind import SmartBlind
from .exceptions import (
    ConnectionFailed,
    InvalidPosition,
    KeyNotFound,
    SmartBlindsError,
)
from .scanner import discover

__all__ = [
    "ConnectionFailed",
    "InvalidPosition",
    "KeyNotFound",
    "SmartBlind",
    "SmartBlindsError",
    "discover",
]

__version__ = "0.0.1"
