"""Explicit proxy trust and bounded, per-process HTTP resource policy."""

from __future__ import annotations

import io
import ipaddress
import math
import re
import socket
import time
from dataclasses import dataclass, field
from email.message import Message
from typing import Any

from .contracts import ProductError


class DeadlineReader(io.RawIOBase):
    """A trickling peer cannot extend the total header/body reading deadline."""

    def __init__(self, connection: socket.socket, timeout: float) -> None:
        self.connection = connection
        self.reset(timeout)

    def reset(self, timeout: float, *, deadline: float | None = None) -> None:
        self.deadline = time.monotonic() + timeout if deadline is None else deadline

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTP read deadline exceeded")
        self.connection.settimeout(remaining)
        return self.connection.recv_into(buffer)


@dataclass(frozen=True)
class TransportPolicy:
    trusted_proxies: tuple[str, ...] = ()
    real_ip_header: str = "X-Real-IP"
    max_connections: int = 384
    max_readers: int = 16
    read_wait_timeout: float = 10.0
    max_uploads: int = 4
    max_pending_uploads: int = 300
    upload_wait_timeout: float = 10.0
    header_timeout: float = 10.0
    body_timeout: float = 60.0
    _networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = field(
        init=False, repr=False
    )

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", self.real_ip_header):
            raise ValueError("Real IP header must be an HTTP field name")
        if (
            type(self.max_connections) is not int
            or type(self.max_readers) is not int
            or not 1 <= self.max_readers <= 4096
            or type(self.read_wait_timeout) not in (int, float)
            or not math.isfinite(self.read_wait_timeout)
            or not 0 <= self.read_wait_timeout <= 120
            or type(self.max_uploads) is not int
            or type(self.max_pending_uploads) is not int
            or not 0 <= self.max_pending_uploads <= 4096
            or type(self.upload_wait_timeout) not in (int, float)
            or not math.isfinite(self.upload_wait_timeout)
            or not 0 <= self.upload_wait_timeout <= 120
            or not 1 <= self.max_uploads < self.max_connections <= 4096
            or any(
                not math.isfinite(value) or value <= 0
                for value in (
                    self.header_timeout,
                    self.body_timeout,
                )
            )
        ):
            raise ValueError("HTTP limits must be finite and leave non-upload capacity")
        object.__setattr__(
            self,
            "_networks",
            tuple(ipaddress.ip_network(value, strict=True) for value in self.trusted_proxies),
        )

    @property
    def effective_pending_uploads(self) -> int:
        # Pending waits do not consume the reserved fifth. An explicit legacy
        # processing cap may already leave less headroom, so preserve its validity.
        headroom = (self.max_connections + 4) // 5
        return min(
            self.max_pending_uploads,
            max(0, self.max_connections - self.max_uploads - headroom),
        )

    def client_ip(self, peer: str, headers: Message) -> str:
        address = ipaddress.ip_address(peer)
        if not any(address in network for network in self._networks):
            return str(address)
        values = headers.get_all(self.real_ip_header, [])
        if not values:
            return str(address)
        try:
            if len(values) != 1 or "%" in values[0]:
                raise ValueError("Ambiguous IP")
            forwarded = ipaddress.ip_address(values[0].strip())
            if forwarded.is_unspecified or forwarded.is_multicast:
                raise ValueError("Not a client IP")
        except ValueError as error:
            raise ProductError("invalid_client_ip", "代理来源地址无效", 400) from error
        return str(forwarded)
