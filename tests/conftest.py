from __future__ import annotations

import pytest
from unittest import mock

from telnetsrv.telnetsrvlib import TelnetHandlerBase, Commands


class MockSocket:
    """Fake socket: records sent bytes, returns pre-loaded recv data."""

    def __init__(self, recv_data: bytes = b""):
        self.sent = b""
        self._recv_data = recv_data
        self._recv_pos = 0

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, n: int) -> bytes:
        chunk = self._recv_data[self._recv_pos : self._recv_pos + n]
        self._recv_pos += n
        return chunk

    def fileno(self) -> int:
        return -1

    def shutdown(self, *args) -> None:
        pass


class ConcreteHandler(TelnetHandlerBase):
    """Minimal concrete TelnetHandlerBase for unit testing."""

    def __init__(self, request, client_address, server):
        self.cookedq: list = []
        super().__init__(request, client_address, server)

    def getc(self, block: bool = True) -> str | int:
        if self.cookedq:
            return self.cookedq.pop(0)
        return ""

    def inputcooker_socket_ready(self) -> bool:
        return False

    def inputcooker_store_queue(self, char) -> None:
        if isinstance(char, (tuple, list, str)):
            for v in char:
                self.cookedq.append(v)
        else:
            self.cookedq.append(char)


def make_handler(handler_class=None) -> ConcreteHandler:
    """Create a handler with the server lifecycle (setup/handle/finish) bypassed."""
    cls = handler_class or ConcreteHandler
    with mock.patch("socketserver.BaseRequestHandler.__init__", return_value=None):
        h = cls(mock.MagicMock(), ("127.0.0.1", 0), None)
    h.sock = MockSocket()
    h.cookedq = []
    h.ESCSEQ = {}
    h.CODES = dict(TelnetHandlerBase.CODES)
    return h


@pytest.fixture
def handler() -> ConcreteHandler:
    return make_handler()
