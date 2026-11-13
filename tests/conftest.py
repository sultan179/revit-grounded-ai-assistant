"""Shared test setup: no test may open a connection that leaves this machine."""

import socket
from collections.abc import Callable
from typing import Any

import pytest

LOOPBACK = ("127.0.0.1", "::1")


class NetworkBlockedError(RuntimeError):
    """A test tried to open a network connection."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse every connection to another machine, so no test can reach a real model.

    Connections from this machine to itself stay allowed: on Windows, Python builds
    its event loops and socket pairs on one. Name lookups (DNS) and connectionless
    sends (UDP) are not blocked; an HTTP call cannot be made with those alone.

    The error is a RuntimeError and not an OSError on purpose: HTTP libraries
    catch OSError and retry or wrap it, which would hide the attempt.
    """

    def guarded(real: Callable[..., Any]) -> Callable[..., Any]:
        def connect(self: socket.socket, address: Any, *args: Any) -> Any:
            if isinstance(address, tuple) and address[0] in LOOPBACK:
                return real(self, address, *args)
            raise NetworkBlockedError(f"tests must not use the network (tried {address!r})")

        return connect

    monkeypatch.setattr(socket.socket, "connect", guarded(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(socket.socket.connect_ex))
