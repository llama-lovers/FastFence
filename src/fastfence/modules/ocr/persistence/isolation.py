"""OCR workers cannot open outbound connections or expose inherited credentials."""

import socket
from typing import Any


def _deny(*args: Any, **kwargs: Any) -> Any:
    raise PermissionError("OCR worker network disabled")


def disable_network() -> None:
    socket.socket.connect = _deny
    socket.socket.connect_ex = _deny
    socket.create_connection = _deny
