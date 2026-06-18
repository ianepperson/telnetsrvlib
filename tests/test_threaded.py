"""Integration tests: real threaded server + raw socket client."""

import socket
import socketserver
import threading
import time
import pytest
from unittest import mock

from telnetsrv.threaded import TelnetHandler, cmd, Commands


# ---------------------------------------------------------------------------
# Server / handler fixtures
# ---------------------------------------------------------------------------


class EchoCommands(Commands):
    @cmd("echo")
    def cmd_echo(self, params):
        """<text>
        Echo parameters back.
        """
        self.handler.writeresponse(" ".join(params))

    @cmd("secret", hidden=True)
    def cmd_secret(self, params):
        """
        Hidden command.
        """
        self.handler.writeresponse("shh")


class EchoHandler(TelnetHandler):
    WELCOME = "READY"
    PROMPT = "$ "
    authNeedUser = False
    authNeedPass = False
    commands_class = EchoCommands


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@pytest.fixture(scope="module")
def server_addr():
    srv = _Server(("127.0.0.1", 0), EchoHandler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()
    yield srv.server_address
    srv.shutdown()


# ---------------------------------------------------------------------------
# Minimal raw-socket telnet client
# ---------------------------------------------------------------------------


class _TelnetClient:
    """Thin raw-socket client that strips IAC negotiation bytes."""

    IAC = 255
    DONT = 254
    DO = 253
    WONT = 252
    WILL = 251
    SB = 250
    SE = 240

    def __init__(self, host, port, timeout=5):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.buf = b""

    def _strip_iac(self, data: bytes) -> bytes:
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b == self.IAC and i + 1 < len(data):
                cmd = data[i + 1]
                if cmd in (self.WILL, self.WONT, self.DO, self.DONT) and i + 2 < len(
                    data
                ):
                    opt = data[i + 2]
                    # Accept server offers (WILL→DO, DO→WILL) so echo stays on
                    if cmd == self.WILL:
                        reply = self.DO
                    elif cmd == self.DO:
                        reply = self.WILL
                    elif cmd == self.WONT:
                        reply = self.DONT
                    else:
                        reply = self.WONT
                    try:
                        self.sock.sendall(bytes([self.IAC, reply, opt]))
                    except OSError:
                        pass
                    i += 3
                    continue
                elif cmd == self.SB:
                    while i < len(data) and data[i] != self.SE:
                        i += 1
                    i += 1
                    continue
                else:
                    i += 2
                    continue
            else:
                out.append(b)
            i += 1
        return bytes(out)

    def read_until(self, marker: bytes, timeout: float = 5) -> bytes:
        self.sock.settimeout(timeout)
        deadline = time.monotonic() + timeout
        while marker not in self.buf:
            if time.monotonic() > deadline:
                break
            try:
                chunk = self.sock.recv(4096)
            except (socket.timeout, BlockingIOError):
                break
            if not chunk:
                break
            self.buf += self._strip_iac(chunk)
        idx = self.buf.find(marker)
        if idx == -1:
            return self.buf
        end = idx + len(marker)
        result, self.buf = self.buf[:end], self.buf[end:]
        return result

    def send(self, text: str) -> None:
        self.sock.sendall(text.encode("latin-1"))

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def _client(server_addr) -> _TelnetClient:
    return _TelnetClient(*server_addr)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThreadedIntegration:
    def test_welcome_message(self, server_addr):
        c = _client(server_addr)
        data = c.read_until(b"READY")
        assert b"READY" in data
        c.close()

    def test_prompt_appears(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"READY")
        data = c.read_until(b"$ ")
        assert b"$ " in data
        c.close()

    def test_help_lists_commands(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send("help\n")
        data = c.read_until(b"$ ")
        assert b"ECHO" in data or b"EXIT" in data
        c.close()

    def test_help_hides_hidden_command(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send("help\n")
        data = c.read_until(b"$ ")
        assert b"SECRET" not in data
        c.close()

    def test_echo_command(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send("echo hello world\n")
        data = c.read_until(b"$ ")
        assert b"hello world" in data
        c.close()

    def test_echo_quoted_param(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send('echo "one two"\n')
        data = c.read_until(b"$ ")
        assert b"one two" in data
        c.close()

    def test_unknown_command_reports_error(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send("NOSUCHCOMMAND\n")
        data = c.read_until(b"$ ")
        assert b"Unknown" in data or b"NOSUCHCOMMAND" in data
        c.close()

    def test_exit_sends_goodbye(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send("exit\n")
        data = c.read_until(b"Goodbye")
        assert b"Goodbye" in data
        c.close()

    def test_quit_alias_works(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send("quit\n")
        data = c.read_until(b"Goodbye")
        assert b"Goodbye" in data
        c.close()

    def test_history_shows_prior_commands(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send("echo marker_cmd\n")
        c.read_until(b"$ ")
        c.send("history\n")
        data = c.read_until(b"$ ")
        assert b"marker_cmd" in data
        c.close()

    def test_question_mark_alias_for_help(self, server_addr):
        c = _client(server_addr)
        c.read_until(b"$ ")
        c.send("?\n")
        data = c.read_until(b"$ ")
        assert b"EXIT" in data or b"ECHO" in data
        c.close()


# ---------------------------------------------------------------------------
# Issue #16: abrupt disconnect must not leave the handler thread spinning
# ---------------------------------------------------------------------------


class _DisconnectServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class TestAbruptDisconnect:
    """When the client closes the TCP connection without sending EXIT, the
    server-side handler thread must terminate on its own rather than spin
    forever in getc() waiting for input that will never arrive."""

    def test_abrupt_disconnect_terminates_session(self):
        handler_finished = threading.Event()

        class TrackingHandler(EchoHandler):
            def finish(self):
                super().finish()
                handler_finished.set()

        srv = _DisconnectServer(("127.0.0.1", 0), TrackingHandler)
        t = threading.Thread(target=srv.serve_forever)
        t.daemon = True
        t.start()

        try:
            c = _TelnetClient(*srv.server_address)
            c.read_until(b"$ ")  # wait for the shell prompt so handle() is in getc()
            c.close()  # abrupt disconnect — no EXIT command
            assert handler_finished.wait(timeout=3), (
                "Handler thread did not terminate after abrupt disconnect "
                "(getc() is probably spinning forever)"
            )
        finally:
            srv.shutdown()
