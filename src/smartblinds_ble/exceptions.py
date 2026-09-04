"""Exceptions for smartblinds-ble."""

from __future__ import annotations


class SmartBlindsError(Exception):
    """Base class for all library errors."""


class ConnectionFailed(SmartBlindsError):
    """Could not establish a BLE connection to the motor."""


class KeyNotFound(SmartBlindsError):
    """A working key could not be discovered for the motor."""


class InvalidPosition(SmartBlindsError):
    """Requested tilt position was outside the accepted range."""
