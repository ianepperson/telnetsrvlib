"""Tests for example-asyncio.py — the asyncio demonstration server."""

from __future__ import annotations

import asyncio
from unittest import mock

import pytest

# example-asyncio.py calls parse_args() at import time; supply required port arg.
with mock.patch("sys.argv", ["example-asyncio", "8023"]):
    import importlib  # noqa: E402
    import sys  # noqa: E402

    spec = importlib.util.spec_from_file_location(
        "example_asyncio", "example-asyncio.py"
    )
    example_asyncio = importlib.util.module_from_spec(spec)
    sys.modules["example_asyncio"] = example_asyncio
    spec.loader.exec_module(example_asyncio)

MyServer = example_asyncio.MyServer
MyCommands = example_asyncio.MyCommands
ExampleTelnetHandler = example_asyncio.ExampleTelnetHandler

from telnetsrv.aio import TelnetHandler  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers (mirror test_aio.py infrastructure)
# ---------------------------------------------------------------------------


class MockWriter:
    def __init__(self):
        self.written = b""
        self._closed = False

    def write(self, data: bytes) -> None:
        self.written += data

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        pass

    def get_extra_info(self, name, default=None):
        return default

    @property
    def sent(self) -> str:
        return self.written.decode("latin-1")


class MockReader:
    def __init__(self, data: bytes = b""):
        self._data = data
        self._pos = 0

    async def read(self, n: int = -1) -> bytes:
        chunk = self._data[self._pos : self._pos + (n if n >= 0 else len(self._data))]
        self._pos += len(chunk)
        return chunk


def make_handler(handler_class=None, reader_data: bytes = b"") -> TelnetHandler:
    cls = handler_class or ExampleTelnetHandler
    h = cls(MockReader(reader_data), MockWriter())
    h.setterm(h.TERM)
    return h


def feed(handler, chars) -> None:
    for c in chars:
        handler.cookedq.put_nowait(c)


def recv(handler) -> str:
    return handler.writer.sent


# ---------------------------------------------------------------------------
# MyServer
# ---------------------------------------------------------------------------


class TestMyServer:
    def test_initial_connection_count_is_zero(self):
        assert MyServer().connection_count == 0

    def test_initial_user_connect_is_empty(self):
        assert MyServer().user_connect == {}

    def test_first_connection_returns_one_one(self):
        s = MyServer()
        global_count, user_count = s.new_connection("alice")
        assert global_count == 1
        assert user_count == 1

    def test_global_count_increments_across_users(self):
        s = MyServer()
        s.new_connection("alice")
        global_count, _ = s.new_connection("bob")
        assert global_count == 2

    def test_per_user_count_increments_on_reconnect(self):
        s = MyServer()
        s.new_connection("alice")
        _, user_count = s.new_connection("alice")
        assert user_count == 2

    def test_different_users_have_independent_counts(self):
        s = MyServer()
        _, alice = s.new_connection("alice")
        _, bob = s.new_connection("bob")
        assert alice == 1
        assert bob == 1

    def test_global_count_tracks_all_connections(self):
        s = MyServer()
        for _ in range(5):
            s.new_connection("alice")
        assert s.connection_count == 5


# ---------------------------------------------------------------------------
# MockHandler for MyCommands unit tests
# ---------------------------------------------------------------------------


class MockHandler:
    def __init__(self):
        self.responses = []
        self.errors = []
        self.messages = []
        self.username = "testuser"
        self.TERM = "xterm"
        self.WIDTH = 80
        self.HEIGHT = 24
        self.history = ["cmd1", "cmd2"]
        self.ESCSEQ = {}
        self.KEYS = {}
        self.myserver = MyServer()
        self.timer_events = []
        self._readline_responses = []

    def writeresponse(self, text):
        self.responses.append(text)

    def writeerror(self, text):
        self.errors.append(text)

    def writemessage(self, text):
        self.messages.append(text)

    async def readline(self, prompt="", echo=True, use_history=True):
        return self._readline_responses.pop(0) if self._readline_responses else ""


# ---------------------------------------------------------------------------
# MyCommands
# ---------------------------------------------------------------------------


class TestMyCommands:
    def setup_method(self):
        self.handler = MockHandler()
        self.cmds = MyCommands(self.handler)

    def test_params_echoes_repr(self):
        self.cmds.params(["hello", "world"])
        assert any("['hello', 'world']" in r for r in self.handler.responses)

    def test_debug_writes_one_line_per_escape_sequence(self):
        self.handler.ESCSEQ = {"\x1b[A": 1}
        self.handler.KEYS = {1: "UP"}
        self.cmds.debug([])
        assert len(self.handler.responses) == 1

    def test_debug_includes_key_name(self):
        self.handler.ESCSEQ = {"\x1b[A": 1}
        self.handler.KEYS = {1: "UP"}
        self.cmds.debug([])
        assert "UP" in self.handler.responses[0]

    def test_info_contains_username(self):
        self.cmds.info([])
        assert "testuser" in " ".join(self.handler.responses)

    def test_info_contains_term(self):
        self.cmds.info([])
        assert "xterm" in " ".join(self.handler.responses)

    def test_info_contains_dimensions(self):
        self.cmds.info([])
        combined = " ".join(self.handler.responses)
        assert "80" in combined and "24" in combined

    def test_info_lists_history(self):
        self.cmds.info([])
        combined = " ".join(self.handler.responses)
        assert "cmd1" in combined and "cmd2" in combined

    def test_echo_joins_params(self):
        self.cmds.cmdECHO(["hello", "world"])
        assert "hello world" in self.handler.responses

    def test_echo_single_word(self):
        self.cmds.cmdECHO(["hello"])
        assert "hello" in self.handler.responses

    async def test_timer_no_params_writes_error(self):
        await self.cmds.timer([])
        assert self.handler.errors

    async def test_timer_non_integer_writes_error(self):
        await self.cmds.timer(["notanumber", "hello"])
        assert self.handler.errors

    async def test_timer_writes_waiting_message(self):
        await self.cmds.timer(["60", "hello"])
        assert any("Waiting" in r for r in self.handler.responses)
        for t in self.handler.timer_events:
            t.cancel()

    async def test_timer_creates_asyncio_task(self):
        await self.cmds.timer(["60", "hello"])
        assert len(self.handler.timer_events) == 1
        assert isinstance(self.handler.timer_events[0], asyncio.Task)
        self.handler.timer_events[0].cancel()

    async def test_timer_fires_message_after_delay(self):
        await self.cmds.timer(["0", "ping"])
        await asyncio.sleep(0.05)
        assert "ping" in self.handler.messages

    async def test_set_password_matching_writes_success(self):
        self.handler._readline_responses = ["secret", "secret"]
        await self.cmds.set_password([])
        assert any("Pretending" in r for r in self.handler.responses)

    async def test_set_password_mismatch_writes_error(self):
        self.handler._readline_responses = ["secret", "wrong"]
        await self.cmds.set_password([])
        assert self.handler.errors

    async def test_set_password_from_params_strips_history(self):
        self.handler.history = ["passwd mysecret"]
        self.handler._readline_responses = ["mysecret"]
        await self.cmds.set_password(["mysecret"])
        assert self.handler.history[-1] == "passwd"

    def test_connections_shows_count(self):
        self.handler.myserver.connection_count = 7
        self.cmds.connections([])
        assert "7" in " ".join(self.handler.responses)

    def test_users_shows_usernames(self):
        self.handler.myserver.user_connect = {"alice": 3, "bob": 1}
        self.cmds.users([])
        combined = " ".join(self.handler.responses)
        assert "alice" in combined and "bob" in combined

    def test_users_shows_counts(self):
        self.handler.myserver.user_connect = {"alice": 3}
        self.cmds.users([])
        assert "3" in " ".join(self.handler.responses)

    def test_command_do_nothing_writes_response(self):
        self.cmds.command_do_nothing([])
        assert any("nothing" in r.lower() for r in self.handler.responses)


# ---------------------------------------------------------------------------
# ExampleTelnetHandler
# ---------------------------------------------------------------------------


class TestExampleTelnetHandler:
    def test_prompt_is_configured(self):
        assert ExampleTelnetHandler.PROMPT == "TestServer> "

    def test_welcome_mentions_server(self):
        assert "server" in ExampleTelnetHandler.WELCOME.lower()

    def test_auth_need_user_is_true(self):
        assert ExampleTelnetHandler.authNeedUser is True

    def test_auth_need_pass_is_false(self):
        assert ExampleTelnetHandler.authNeedPass is False

    def test_auth_callback_accepts_nonempty_username(self):
        h = make_handler()
        h.authCallback("alice", "")  # must not raise

    def test_auth_callback_rejects_empty_username(self):
        h = make_handler()
        with pytest.raises(BaseException):
            h.authCallback("", "")

    def test_session_start_initializes_timer_events(self):
        h = make_handler()
        h.username = "alice"
        h.session_start()
        assert h.timer_events == []

    def test_session_start_writes_username(self):
        h = make_handler()
        h.username = "alice"
        h.session_start()
        assert "alice" in recv(h)

    def test_session_start_writes_asyncio(self):
        h = make_handler()
        h.username = "alice"
        h.session_start()
        assert "asyncio" in recv(h)

    def test_session_start_writes_connection_count(self):
        # Reset to a known server state for this test.
        original_server = ExampleTelnetHandler.myserver
        ExampleTelnetHandler.myserver = MyServer()
        try:
            h = make_handler()
            h.username = "alice"
            h.session_start()
            assert "1" in recv(h)
        finally:
            ExampleTelnetHandler.myserver = original_server

    def test_session_end_cancels_pending_tasks(self):
        h = make_handler()
        h.username = "alice"
        h.session_start()
        mock_task = mock.MagicMock()
        h.timer_events = [mock_task]
        h.session_end()
        mock_task.cancel.assert_called_once()

    def test_session_end_cancels_multiple_tasks(self):
        h = make_handler()
        h.username = "alice"
        h.session_start()
        tasks = [mock.MagicMock(), mock.MagicMock()]
        h.timer_events = tasks
        h.session_end()
        for t in tasks:
            t.cancel.assert_called_once()

    def test_writeerror_wraps_in_ansi_red(self):
        h = make_handler()
        h.writeerror("bad input")
        output = recv(h)
        assert "\x1b[91m" in output
        assert "bad input" in output
        assert "\x1b[0m" in output

    def test_commands_class_is_my_commands(self):
        assert ExampleTelnetHandler.commands_class is MyCommands


# ---------------------------------------------------------------------------
# Integration: real asyncio server using ExampleTelnetHandler
# ---------------------------------------------------------------------------


def _strip_iac(data: bytes) -> bytes:
    IAC_B = 255
    WILL_B, WONT_B, DO_B, DONT_B = 251, 252, 253, 254
    SB_B, SE_B = 250, 240
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == IAC_B and i + 1 < len(data):
            cmd_b = data[i + 1]
            if cmd_b in (WILL_B, WONT_B, DO_B, DONT_B) and i + 2 < len(data):
                i += 3
                continue
            elif cmd_b == SB_B:
                while i < len(data) and data[i] != SE_B:
                    i += 1
                i += 1
                continue
            else:
                i += 2
                continue
        out.append(b)
        i += 1
    return bytes(out)


async def _read_until(reader, marker: bytes, timeout: float = 3.0) -> bytes:
    buf = b""
    deadline = asyncio.get_running_loop().time() + timeout
    while marker not in buf:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            chunk = await asyncio.wait_for(
                reader.read(4096), timeout=min(remaining, 0.3)
            )
        except asyncio.TimeoutError:
            break
        if not chunk:
            break
        buf += _strip_iac(chunk)
    return buf


class _IntegrationHandler(ExampleTelnetHandler):
    """No telnet negotiation or option-negotiation delay for integration tests."""

    OPTION_NEGOTIATION_DELAY = 0
    authNeedUser = False
    authNeedPass = False
    authCallback = None

    async def setup(self):
        self.setterm(self.TERM)
        self.sock = None
        self._task_ic = asyncio.create_task(self.inputcooker())

    def session_start(self):
        self.timer_events = []
        self.writeline("INTEGRATION READY")


@pytest.fixture
async def server_addr():
    server = await asyncio.start_server(
        _IntegrationHandler.asyncio_handle, "127.0.0.1", 0
    )
    addr = server.sockets[0].getsockname()
    yield addr
    server.close()
    await server.wait_closed()


class TestIntegration:
    async def test_welcome_received(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        data = await _read_until(reader, b"INTEGRATION READY")
        assert b"INTEGRATION READY" in data
        writer.close()
        await writer.wait_closed()

    async def test_prompt_appears(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        data = await _read_until(reader, b"TestServer> ")
        assert b"TestServer> " in data
        writer.close()
        await writer.wait_closed()

    async def test_echo_command(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"TestServer> ")
        writer.write(b"echo hello world\n")
        data = await _read_until(reader, b"TestServer> ")
        assert b"hello world" in data
        writer.close()
        await writer.wait_closed()

    async def test_params_command(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"TestServer> ")
        writer.write(b"params foo bar\n")
        data = await _read_until(reader, b"TestServer> ")
        assert b"foo" in data
        writer.close()
        await writer.wait_closed()

    async def test_info_command(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"TestServer> ")
        writer.write(b"info\n")
        data = await _read_until(reader, b"TestServer> ")
        assert b"terminal" in data.lower() or b"Width" in data
        writer.close()
        await writer.wait_closed()

    async def test_timer_fires_message(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"TestServer> ")
        writer.write(b'timer 0 "ping"\n')
        data = await _read_until(reader, b"ping", timeout=2.0)
        assert b"ping" in data
        writer.close()
        await writer.wait_closed()

    async def test_unknown_command_writes_error(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"TestServer> ")
        writer.write(b"NOSUCH\n")
        data = await _read_until(reader, b"TestServer> ")
        assert b"NOSUCH" in data or b"Unknown" in data
        writer.close()
        await writer.wait_closed()

    async def test_exit_command(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"TestServer> ")
        writer.write(b"exit\n")
        data = await _read_until(reader, b"Goodbye")
        assert b"Goodbye" in data
        writer.close()
        await writer.wait_closed()

    async def test_help_lists_commands(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"TestServer> ")
        writer.write(b"help\n")
        data = await _read_until(reader, b"TestServer> ")
        assert b"ECHO" in data or b"TIMER" in data or b"INFO" in data
        writer.close()
        await writer.wait_closed()

    async def test_abrupt_disconnect_does_not_hang(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"TestServer> ")
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.1)
