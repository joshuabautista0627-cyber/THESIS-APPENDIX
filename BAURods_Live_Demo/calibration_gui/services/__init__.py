"""Hardware-boundary service contracts and implementations."""

from .interfaces import (
    CameraConnectionInfo,
    CameraPropertyReadback,
    CameraServiceInterface,
    CapturedFrame,
    SerialConnectionInfo,
    SerialServiceInterface,
)

__all__ = [
    "CameraConnectionInfo",
    "CameraPropertyReadback",
    "CameraServiceInterface",
    "CapturedFrame",
    "SerialConnectionInfo",
    "Hx711SerialService",
    "SerialPlaybackSource",
    "SerialPortDescriptor",
    "SerialService",
    "SerialServiceInterface",
    "enumerate_serial_ports",
    "parse_data_line",
    "parse_hello_line",
]


def __getattr__(name):
    """Camera-only applications can run without loading the serial backend."""
    if name in __all__ and name not in globals():
        from . import serial_service
        return getattr(serial_service, name)
    raise AttributeError(name)
