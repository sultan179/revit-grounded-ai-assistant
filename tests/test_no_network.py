"""The network guard in conftest.py is itself tested here."""

import asyncio
import socket

import pytest

# 192.0.2.1 is reserved for documentation (RFC 5737): no real machine answers there.
NOWHERE = ("192.0.2.1", 443)


def test_a_direct_connection_is_refused() -> None:
    with socket.socket() as sock, pytest.raises(RuntimeError, match="must not use the network"):
        sock.connect(NOWHERE)


def test_the_helper_most_libraries_use_is_refused() -> None:
    with pytest.raises(RuntimeError, match="must not use the network"):
        socket.create_connection(NOWHERE, timeout=1)


def test_this_machine_can_still_talk_to_itself() -> None:
    # Both of these connect to 127.0.0.1 on Windows; a guard that refused them would
    # break every async test there and pass on Linux.
    left, right = socket.socketpair()
    left.close()
    right.close()
    asyncio.run(asyncio.sleep(0))
