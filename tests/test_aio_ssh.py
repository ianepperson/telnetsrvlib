"""Tests for telnetsrv.aio_ssh — the async SSH handler bridge."""

from __future__ import annotations

import asyncio
import sys
import types
from unittest import mock
import pytest

# ---------------------------------------------------------------------------
# Install a minimal paramiko stub so aio_ssh can be imported without the
# real library. Tests that need the actual Paramiko transport are skipped.
# ---------------------------------------------------------------------------
if "paramiko" not in sys.modules:
    class _ServerInterface:
        """Minimal stand-in for paramiko.ServerInterface."""

    _stub = types.ModuleType("paramiko")
    _stub.Transport = mock.MagicMock
    _stub.ServerInterface = _ServerInterface
    _stub.RSAKey = mock.MagicMock
    _stub.SSHException = Exception
    _stub.AUTH_SUCCESSFUL = 1
    _stub.AUTH_FAILED = 0
    _stub.OPEN_SUCCEEDED = 0
    _stub.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED = 1
    sys.modules["paramiko"] = _stub

from telnetsrv.aio_ssh import (  # noqa: E402
    AsyncTelnetToPtyHandler,
    _AsyncChannelReader,
    _AsyncChannelWriter,
    AsyncSSHHandler,
)
from telnetsrv.aio import TelnetHandler, Commands, cmd  # noqa: E402


# ===========================================================================
# Helpers
# ===========================================================================


class _FakeChannel:
    """Minimal Paramiko channel stand-in."""

    def __init__(self, data: bytes = b""):
        self._data = data
        self._pos = 0
        self.sent = b""

    def recv(self, n: int) -> bytes:
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def sendall(self, data: bytes) -> None:
        self.sent += data


class _MinimalHandler(TelnetHandler):
    """TelnetHandler subclass for SSH tests: no negotiation, instant exit."""

    WELCOME = "HI"
    PROMPT = ">"
    authCallback = None
    commands_class = Commands  # empty command set

    async def setup(self):
        self.setterm(self.TERM)
        self.sock = None
        self._task_ic = asyncio.create_task(self.inputcooker())

    async def handle(self):
        pass  # return immediately


def _make_ssh_handler() -> AsyncSSHHandler:
    """Build an AsyncSSHHandler without triggering the full Paramiko lifecycle."""
    ssh = object.__new__(AsyncSSHHandler)
    ssh.username = "testuser"
    ssh.client_address = ("127.0.0.1", 12345)
    return ssh


# ===========================================================================
# AsyncTelnetToPtyHandler
# ===========================================================================


class TestAsyncTelnetToPtyHandler:
    def test_doack_is_empty_dict(self):
        assert AsyncTelnetToPtyHandler.DOACK == {}

    def test_willack_is_empty_dict(self):
        assert AsyncTelnetToPtyHandler.WILLACK == {}

    async def test_authentication_ok_returns_true(self):
        obj = object.__new__(AsyncTelnetToPtyHandler)
        obj._ssh_username = "alice"
        assert await obj.authentication_ok() is True

    async def test_authentication_ok_sets_username(self):
        obj = object.__new__(AsyncTelnetToPtyHandler)
        obj._ssh_username = "bob"
        await obj.authentication_ok()
        assert obj.username == "bob"

    async def test_authentication_ok_with_no_ssh_username_sets_none(self):
        obj = object.__new__(AsyncTelnetToPtyHandler)
        await obj.authentication_ok()
        assert obj.username is None

    def test_mixin_doack_wins_in_mro(self):
        class Mixed(AsyncTelnetToPtyHandler, TelnetHandler):
            def __init__(self, r, w):
                TelnetHandler.__init__(self, r, w)

        assert Mixed.DOACK == {}
        assert Mixed.WILLACK == {}

    def test_mixin_does_not_expose_telnet_options(self):
        assert AsyncTelnetToPtyHandler.DOACK == {}
        assert "ECHO" not in AsyncTelnetToPtyHandler.DOACK


# ===========================================================================
# _AsyncChannelReader
# ===========================================================================


class TestAsyncChannelReader:
    async def test_read_returns_channel_data(self):
        chan = _FakeChannel(b"hello")
        cr = _AsyncChannelReader(chan)
        task = asyncio.create_task(cr.start_feed())
        data = await asyncio.wait_for(cr.read(5), timeout=2.0)
        assert data == b"hello"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_eof_when_channel_returns_empty(self):
        chan = _FakeChannel(b"")
        cr = _AsyncChannelReader(chan)
        await asyncio.wait_for(cr.start_feed(), timeout=2.0)
        # After start_feed exits, StreamReader is at EOF → read returns b""
        data = await asyncio.wait_for(cr.read(1024), timeout=1.0)
        assert data == b""

    async def test_multiple_chunks_read_in_order(self):
        chan = _FakeChannel(b"ab")
        cr = _AsyncChannelReader(chan)
        task = asyncio.create_task(cr.start_feed())
        d1 = await asyncio.wait_for(cr.read(1), timeout=2.0)
        d2 = await asyncio.wait_for(cr.read(1), timeout=2.0)
        assert d1 + d2 == b"ab"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_cancellation_calls_feed_eof(self):
        """Cancelling start_feed should put the inner StreamReader at EOF."""
        import time

        def slow_recv(n):
            time.sleep(5)
            return b""

        chan = _FakeChannel(b"")
        chan.recv = slow_recv  # type: ignore[method-assign]
        cr = _AsyncChannelReader(chan)
        task = asyncio.create_task(cr.start_feed())
        await asyncio.sleep(0)  # let the task start and enter run_in_executor
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Inner StreamReader should be at EOF after cancellation
        data = await asyncio.wait_for(cr.read(10), timeout=1.0)
        assert data == b""

    async def test_exception_in_recv_calls_feed_eof(self):
        """Any exception from recv should cause feed_eof and exit gracefully."""

        def exploding_recv(n):
            raise OSError("connection reset")

        chan = _FakeChannel(b"")
        chan.recv = exploding_recv  # type: ignore[method-assign]
        cr = _AsyncChannelReader(chan)
        await asyncio.wait_for(cr.start_feed(), timeout=2.0)
        data = await asyncio.wait_for(cr.read(10), timeout=1.0)
        assert data == b""


# ===========================================================================
# _AsyncChannelWriter
# ===========================================================================


class TestAsyncChannelWriter:
    def test_write_calls_sendall(self):
        chan = mock.MagicMock()
        cw = _AsyncChannelWriter(chan)
        cw.write(b"hello")
        chan.sendall.assert_called_once_with(b"hello")

    def test_write_sendall_exception_is_swallowed(self):
        chan = mock.MagicMock()
        chan.sendall.side_effect = OSError("broken pipe")
        cw = _AsyncChannelWriter(chan)
        cw.write(b"data")  # must not raise

    async def test_drain_is_noop(self):
        cw = _AsyncChannelWriter(mock.MagicMock())
        await cw.drain()  # must not raise

    def test_close_is_noop(self):
        cw = _AsyncChannelWriter(mock.MagicMock())
        cw.close()  # must not raise

    async def test_wait_closed_is_noop(self):
        cw = _AsyncChannelWriter(mock.MagicMock())
        await cw.wait_closed()  # must not raise

    def test_get_extra_info_returns_none_by_default(self):
        cw = _AsyncChannelWriter(mock.MagicMock())
        assert cw.get_extra_info("socket") is None

    def test_get_extra_info_returns_supplied_default(self):
        cw = _AsyncChannelWriter(mock.MagicMock())
        assert cw.get_extra_info("peername", "sentinel") == "sentinel"

    def test_write_multiple_calls_accumulate_on_channel(self):
        chan = _FakeChannel()
        cw = _AsyncChannelWriter(chan)
        cw.write(b"foo")
        cw.write(b"bar")
        assert chan.sent == b"foobar"


# ===========================================================================
# AsyncSSHHandler._run_pty_coro
# ===========================================================================


class TestAsyncSSHHandlerRunPtyCoro:
    def _make_mocked_handler_class(self):
        """Return a mock handler class whose _run() is an AsyncMock."""
        inst = mock.MagicMock()
        inst._run = mock.AsyncMock()
        cls = mock.MagicMock(return_value=inst)
        return cls, inst

    async def test_handler_receives_correct_term(self):
        ssh = _make_ssh_handler()
        cls, inst = self._make_mocked_handler_class()
        ssh._async_pty_handler = cls

        await ssh._run_pty_coro(_FakeChannel(b""), "xterm-256color")

        assert inst.TERM == "xterm-256color"

    async def test_handler_receives_ssh_username(self):
        ssh = _make_ssh_handler()
        cls, inst = self._make_mocked_handler_class()
        ssh._async_pty_handler = cls

        await ssh._run_pty_coro(_FakeChannel(b""), "ansi")

        assert inst._ssh_username == "testuser"

    async def test_handler_receives_client_address(self):
        ssh = _make_ssh_handler()
        cls, inst = self._make_mocked_handler_class()
        ssh._async_pty_handler = cls

        await ssh._run_pty_coro(_FakeChannel(b""), "ansi")

        assert inst.client_address == ("127.0.0.1", 12345)

    async def test_handler_run_is_awaited(self):
        ssh = _make_ssh_handler()
        cls, inst = self._make_mocked_handler_class()
        ssh._async_pty_handler = cls

        await ssh._run_pty_coro(_FakeChannel(b""), "ansi")

        inst._run.assert_awaited_once()

    async def test_handler_class_called_with_reader_and_writer(self):
        ssh = _make_ssh_handler()
        cls, inst = self._make_mocked_handler_class()
        ssh._async_pty_handler = cls

        await ssh._run_pty_coro(_FakeChannel(b""), "ansi")

        args, _ = cls.call_args
        assert isinstance(args[0], _AsyncChannelReader)
        assert isinstance(args[1], _AsyncChannelWriter)

    async def test_channel_data_flows_through_reader_to_handler(self):
        """End-to-end: channel bytes reach the handler via the StreamReader."""
        ssh = _make_ssh_handler()

        class CapturingHandler(_MinimalHandler):
            received: bytes = b""

            async def setup(self):
                self.setterm(self.TERM)
                self.sock = None
                # Use a completed task so finish() can cancel it safely,
                # but don't start inputcooker so we're the only reader.
                self._task_ic = asyncio.create_task(asyncio.sleep(0))

            async def handle(self):
                data = await self.reader.read(100)
                CapturingHandler.received = data

        class MixedHandler(AsyncTelnetToPtyHandler, CapturingHandler):
            def __init__(self, r, w):
                CapturingHandler.__init__(self, r, w)

        ssh._async_pty_handler = MixedHandler
        chan = _FakeChannel(b"test data")

        await asyncio.wait_for(ssh._run_pty_coro(chan, "ansi"), timeout=3.0)

        assert CapturingHandler.received == b"test data"

    async def test_term_string_assigned_directly_to_handler(self):
        """_run_pty_coro assigns term as-is; start_pty_request owns decoding."""
        ssh = _make_ssh_handler()
        cls, inst = self._make_mocked_handler_class()
        ssh._async_pty_handler = cls

        await ssh._run_pty_coro(_FakeChannel(b""), "vt100")

        assert inst.TERM == "vt100"

    async def test_feed_task_cancelled_after_handler_exits(self):
        """The feed background task must be cleaned up even on normal exit."""
        ssh = _make_ssh_handler()
        feed_tasks: list[asyncio.Task] = []

        original_class = _AsyncChannelReader

        class TrackingReader(original_class):
            async def start_feed(self):
                task = asyncio.current_task()
                if task:
                    feed_tasks.append(task)
                await super().start_feed()

        with mock.patch("telnetsrv.aio_ssh._AsyncChannelReader", TrackingReader):
            cls, inst = self._make_mocked_handler_class()
            ssh._async_pty_handler = cls
            await ssh._run_pty_coro(_FakeChannel(b""), "ansi")

        # All feed tasks should be done (cancelled or finished) after _run_pty_coro
        for t in feed_tasks:
            assert t.done()
