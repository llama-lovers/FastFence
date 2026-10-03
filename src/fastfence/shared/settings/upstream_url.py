"""Validate trusted model origins without accepting inline credentials."""

import ipaddress
from urllib.parse import urlsplit


def validate_openai_base_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
        try:
            loopback = (
                host == "localhost"
                or ipaddress.ip_address(host or "").is_loopback
            )
        except ValueError:
            loopback = False
        if (
            not host
            or parts.scheme not in {"http", "https"}
            or (parts.scheme == "http" and not loopback)
            or parts.username is not None
            or parts.password is not None
            or "?" in value
            or "#" in value
            or "\\" in value
            or any(
                ord(character) <= 32 or ord(character) == 127
                for character in value
            )
            or port == 0
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "OpenAI base URL requires HTTPS or loopback HTTP without credentials, query or fragment"
        ) from None
    return value.rstrip("/")
