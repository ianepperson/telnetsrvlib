"""Tests for telnetsrv.aio — the asyncio-based telnet handler."""

from __future__ import annotations

import asyncio
import curses
import pytest
from unittest import mock

from telnetsrv.aio import TelnetHandler, AsyncInputBashLike, _EOF_SENTINEL, cmd, Commands
from telnetsrv.constants import theNULL, IAC, DO, WILL, ECHO
from telnetsrv.telnetsrvlib import TelnetHandlerBase


# ===========================================================================
# Shared infrastructure
# ===========================================================================


class MockWriter:
    """asyncio.StreamWriter stand-in that records bytes written."""

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
    """asyncio.StreamReader stand-in backed by pre-loaded bytes."""

    def __init__(self, data: bytes = b""):
        self._data = data
        self._pos = 0

    async def read(self, n: int = -1) -> bytes:
        chunk = self._data[self._pos : self._pos + (n if n >= 0 else len(self._data))]
        self._pos += len(chunk)
        return chunk


def make_handler(handler_class=None, reader_data: bytes = b"") -> TelnetHandler:
    """Instantiate a handler with mock streams — no network, no lifecycle."""
    cls = handler_class or TelnetHandler
    h = cls(MockReader(reader_data), MockWriter())
    h.setterm(h.TERM)
    return h


def feed(handler: TelnetHandler, chars) -> None:
    """Pre-load cookedq with characters or key codes."""
    for c in chars:
        handler.cookedq.put_nowait(c)


def drain_cooked(handler: TelnetHandler) -> list:
    """Return all non-sentinel items from cookedq."""
    items = []
    while not handler.cookedq.empty():
        item = handler.cookedq.get_nowait()
        if item is not _EOF_SENTINEL:
            items.append(item)
    return items


# ===========================================================================
# AsyncInputBashLike
# ===========================================================================


class TestAsyncInputBashLike:
    async def _make(self, line: str, continuation: str = "") -> AsyncInputBashLike:
        h = mock.AsyncMock()
        h.CONTINUE_PROMPT = "... "
        h.readline = mock.AsyncMock(return_value=continuation)
        return await AsyncInputBashLike.create(h, line)

    async def test_empty_string(self):
        inp = await self._make("")
        assert inp.cmd == ""
        assert inp.params == []

    async def test_whitespace_only(self):
        inp = await self._make("   ")
        assert inp.cmd == ""
        assert inp.params == []

    async def test_single_word(self):
        inp = await self._make("hello")
        assert inp.cmd == "hello"
        assert inp.params == []

    async def test_multiple_words(self):
        inp = await self._make("foo bar baz")
        assert inp.cmd == "foo"
        assert inp.params == ["bar", "baz"]

    async def test_double_quoted_preserves_spaces(self):
        inp = await self._make('cmd "hello world"')
        assert inp.cmd == "cmd"
        assert inp.params == ["hello world"]

    async def test_single_quoted_preserves_spaces(self):
        inp = await self._make("cmd 'hello world'")
        assert inp.cmd == "cmd"
        assert inp.params == ["hello world"]

    async def test_escaped_space_joins_param(self):
        inp = await self._make(r"echo hello\ world")
        assert inp.params == ["hello world"]

    async def test_continuation_calls_readline(self):
        h = mock.AsyncMock()
        h.CONTINUE_PROMPT = "... "
        h.readline = mock.AsyncMock(return_value="world")
        inp = await AsyncInputBashLike.create(h, "echo hello \\")
        h.readline.assert_awaited_once()
        assert inp.cmd == "echo"

    async def test_raw_contains_original_line(self):
        inp = await self._make("hello world")
        assert "hello world" in inp.raw

    async def test_params_are_remainder(self):
        inp = await self._make("mycmd arg1 arg2")
        assert inp.params == ["arg1", "arg2"]

    async def test_complete_flag_set(self):
        inp = await self._make("done")
        assert inp.complete is True


# ===========================================================================
# TelnetHandler.__init__
# ===========================================================================


class TestAsyncHandlerInit:
    def test_cookedq_is_asyncio_queue(self):
        assert isinstance(make_handler().cookedq, asyncio.Queue)

    def test_reader_and_writer_assigned(self):
        r, w = MockReader(), MockWriter()
        h = TelnetHandler(r, w)
        assert h.reader is r
        assert h.writer is w

    def test_eof_starts_false(self):
        assert make_handler().eof == 0

    def test_runshell_starts_true(self):
        assert make_handler().RUNSHELL is True

    def test_history_starts_empty(self):
        assert make_handler().history == []

    def test_doecho_starts_true(self):
        assert make_handler().DOECHO is True

    def test_client_address_from_writer_peername(self):
        w = MockWriter()
        w.get_extra_info = lambda name, default=None: ("1.2.3.4", 9999) if name == "peername" else default
        h = TelnetHandler(MockReader(), w)
        assert h.client_address == ("1.2.3.4", 9999)

    def test_inherits_class_constants(self):
        h = make_handler()
        assert h.DOACK == TelnetHandlerBase.DOACK
        assert h.WILLACK == TelnetHandlerBase.WILLACK


# ===========================================================================
# getc
# ===========================================================================


class TestAsyncGetc:
    async def test_returns_item_from_queue(self):
        h = make_handler()
        h.cookedq.put_nowait("x")
        assert await h.getc() == "x"

    async def test_nonblocking_empty_queue_returns_empty_string(self):
        assert await make_handler().getc(block=False) == ""

    async def test_nonblocking_returns_item_when_present(self):
        h = make_handler()
        h.cookedq.put_nowait("y")
        assert await h.getc(block=False) == "y"

    async def test_eof_sentinel_raises_eoferror(self):
        h = make_handler()
        h.cookedq.put_nowait(_EOF_SENTINEL)
        with pytest.raises(EOFError):
            await h.getc()

    async def test_eof_sentinel_is_requeued_after_raise(self):
        h = make_handler()
        h.cookedq.put_nowait(_EOF_SENTINEL)
        with pytest.raises(EOFError):
            await h.getc()
        assert h.cookedq.get_nowait() is _EOF_SENTINEL

    async def test_nonblocking_eof_sentinel_raises(self):
        h = make_handler()
        h.cookedq.put_nowait(_EOF_SENTINEL)
        with pytest.raises(EOFError):
            await h.getc(block=False)


# ===========================================================================
# inputcooker_store_queue
# ===========================================================================


class TestInputcookerStore:
    def test_single_char(self):
        h = make_handler()
        h.inputcooker_store_queue("a")
        assert h.cookedq.get_nowait() == "a"

    def test_string_stores_each_char_in_order(self):
        h = make_handler()
        h.inputcooker_store_queue("abc")
        assert [h.cookedq.get_nowait() for _ in range(3)] == list("abc")

    def test_list_stores_each_item(self):
        h = make_handler()
        h.inputcooker_store_queue(["x", "y"])
        assert h.cookedq.get_nowait() == "x"
        assert h.cookedq.get_nowait() == "y"

    def test_integer_stored_directly(self):
        h = make_handler()
        h.inputcooker_store_queue(42)
        assert h.cookedq.get_nowait() == 42


# ===========================================================================
# writecooked
# ===========================================================================


class TestAsyncWritecooked:
    def test_sends_bytes_to_writer(self):
        h = make_handler()
        h.writecooked("hello")
        assert h.writer.written == b"hello"

    def test_encodes_latin1_high_byte(self):
        h = make_handler()
        h.writecooked(chr(0xFF))
        assert h.writer.written == b"\xff"

    def test_multiple_calls_accumulate(self):
        h = make_handler()
        h.writecooked("ab")
        h.writecooked("cd")
        assert h.writer.written == b"abcd"


# ===========================================================================
# _inputcooker_getc (async)
# ===========================================================================


class TestAsyncInputcookerGetc:
    async def test_reads_from_rawq_first(self):
        h = make_handler()
        h.rawq = "abc"
        assert await h._inputcooker_getc() == "a"
        assert h.rawq == "bc"

    async def test_nonblocking_returns_empty_when_rawq_empty(self):
        h = make_handler()
        assert await h._inputcooker_getc(block=False) == ""

    async def test_reads_from_reader_when_rawq_empty(self):
        h = make_handler(reader_data=b"x")
        assert await h._inputcooker_getc() == "x"

    async def test_eof_raises_eoferror(self):
        h = make_handler(reader_data=b"")
        with pytest.raises(EOFError):
            await h._inputcooker_getc()

    async def test_eof_sets_eof_flag(self):
        h = make_handler(reader_data=b"")
        with pytest.raises(EOFError):
            await h._inputcooker_getc()
        assert h.eof


# ===========================================================================
# inputcooker (async task)
# ===========================================================================


async def run_cooker(h: TelnetHandler) -> None:
    task = asyncio.create_task(h.inputcooker())
    await asyncio.wait_for(task, timeout=2.0)


class TestAsyncInputcooker:
    async def test_plain_text_stored(self):
        h = make_handler()
        h.rawq = "hello"
        await run_cooker(h)
        assert drain_cooked(h)[:5] == list("hello")

    async def test_cr_lf_becomes_lf(self):
        h = make_handler()
        h.rawq = "\r\n"
        await run_cooker(h)
        items = drain_cooked(h)
        assert chr(10) in items
        assert chr(13) not in items

    async def test_cr_null_becomes_lf(self):
        h = make_handler()
        h.rawq = "\r" + theNULL
        await run_cooker(h)
        assert chr(10) in drain_cooked(h)

    async def test_eof_puts_sentinel_in_queue(self):
        h = make_handler()
        h.rawq = ""
        await run_cooker(h)
        assert h.cookedq.get_nowait() is _EOF_SENTINEL

    async def test_eof_sets_eof_flag(self):
        h = make_handler()
        h.rawq = ""
        await run_cooker(h)
        assert h.eof == 1

    async def test_iac_iac_stores_single_iac(self):
        h = make_handler()
        h.rawq = IAC + IAC
        await run_cooker(h)
        assert IAC in drain_cooked(h)

    async def test_iac_do_calls_options_handler(self):
        h = make_handler()
        h.rawq = IAC + DO + ECHO
        with mock.patch.object(h, "options_handler") as mock_oh:
            await run_cooker(h)
        mock_oh.assert_called_once_with(h.sock, DO, ECHO)

    async def test_iac_will_calls_options_handler(self):
        h = make_handler()
        h.rawq = IAC + WILL + ECHO
        with mock.patch.object(h, "options_handler") as mock_oh:
            await run_cooker(h)
        mock_oh.assert_called_once_with(h.sock, WILL, ECHO)

    async def test_exits_cleanly_on_empty_input(self):
        h = make_handler()
        h.rawq = ""
        await run_cooker(h)  # must not raise


# ===========================================================================
# ansi_to_curses (async)
# ===========================================================================


class TestAsyncAnsiToCurses:
    async def test_regular_char_unchanged(self):
        assert await make_handler().ansi_to_curses("a") == "a"

    async def test_non_escape_unchanged(self):
        assert await make_handler().ansi_to_curses(chr(10)) == chr(10)

    async def test_up_arrow(self):
        h = make_handler()
        feed(h, ["[", "A"])
        assert await h.ansi_to_curses(chr(27)) == curses.KEY_UP

    async def test_down_arrow(self):
        h = make_handler()
        feed(h, ["[", "B"])
        assert await h.ansi_to_curses(chr(27)) == curses.KEY_DOWN

    async def test_right_arrow(self):
        h = make_handler()
        feed(h, ["[", "C"])
        assert await h.ansi_to_curses(chr(27)) == curses.KEY_RIGHT

    async def test_left_arrow(self):
        h = make_handler()
        feed(h, ["[", "D"])
        assert await h.ansi_to_curses(chr(27)) == curses.KEY_LEFT

    async def test_unknown_sequence_returns_null(self):
        h = make_handler()
        feed(h, ["[", "Z"])
        assert await h.ansi_to_curses(chr(27)) == theNULL

    async def test_no_bracket_returns_null(self):
        h = make_handler()
        feed(h, ["X"])
        assert await h.ansi_to_curses(chr(27)) == theNULL

    async def test_integer_key_code_passes_through(self):
        assert await make_handler().ansi_to_curses(curses.KEY_UP) == curses.KEY_UP


# ===========================================================================
# readline (async)
# ===========================================================================


class TestAsyncReadline:
    async def test_simple_word(self):
        h = make_handler()
        feed(h, list("hello") + [chr(10)])
        assert await h.readline() == "hello"

    async def test_empty_input(self):
        h = make_handler()
        feed(h, [chr(10)])
        assert await h.readline() == ""

    async def test_adds_to_history(self):
        h = make_handler()
        feed(h, list("cmd") + [chr(10)])
        await h.readline(use_history=True)
        assert h.history[-1] == "cmd"

    async def test_no_history_when_disabled(self):
        h = make_handler()
        feed(h, list("cmd") + [chr(10)])
        await h.readline(use_history=False)
        assert h.history == []

    async def test_prompt_written(self):
        h = make_handler()
        feed(h, [chr(10)])
        await h.readline(prompt="TEST> ")
        assert b"TEST> " in h.writer.written

    async def test_ctrl_c_returns_empty(self):
        h = make_handler()
        feed(h, [chr(3)])
        assert await h.readline() == ""

    async def test_ctrl_d_on_empty_line_returns_quit(self):
        h = make_handler()
        feed(h, [chr(4)])
        assert await h.readline() == "QUIT"

    async def test_ctrl_d_on_nonempty_line_aborts(self):
        h = make_handler()
        feed(h, list("hi") + [chr(4)])
        assert await h.readline() == ""

    async def test_backspace_chr8_removes_last_char(self):
        h = make_handler()
        feed(h, list("helo") + [chr(8)] + [chr(10)])
        assert await h.readline() == "hel"

    async def test_backspace_chr127_removes_last_char(self):
        h = make_handler()
        feed(h, list("helo") + [chr(127)] + [chr(10)])
        assert await h.readline() == "hel"

    async def test_backspace_at_start_does_nothing(self):
        h = make_handler()
        feed(h, [chr(8)] + list("ok") + [chr(10)])
        assert await h.readline() == "ok"

    async def test_delete_key_at_end_does_nothing(self):
        h = make_handler()
        feed(h, list("ab") + [curses.KEY_DC] + [chr(10)])
        assert await h.readline() == "ab"

    async def test_left_right_navigation(self):
        h = make_handler()
        feed(h, list("ab") + [curses.KEY_LEFT, curses.KEY_RIGHT] + [chr(10)])
        assert await h.readline() == "ab"

    async def test_up_through_history(self):
        h = make_handler()
        h.history = ["older", "newer"]
        feed(h, [curses.KEY_UP, chr(10)])
        assert await h.readline(use_history=True) == "newer"

    async def test_up_beyond_history_does_not_crash(self):
        h = make_handler()
        h.history = []
        feed(h, [curses.KEY_UP] + list("x") + [chr(10)])
        assert await h.readline() == "x"

    async def test_down_at_end_does_not_crash(self):
        h = make_handler()
        h.history = ["a"]
        feed(h, [curses.KEY_DOWN] + list("x") + [chr(10)])
        assert await h.readline() == "x"

    async def test_eof_sentinel_raises_eoferror(self):
        h = make_handler()
        h.cookedq.put_nowait(_EOF_SENTINEL)
        with pytest.raises(EOFError):
            await h.readline()

    async def test_unrecognized_integer_key_is_ignored(self):
        """Bug 1: curses key codes not handled by readline (e.g. KEY_PPAGE) must be
        silently ignored, not crash with TypeError on len(c)."""
        h = make_handler()
        # KEY_PPAGE (page-up) is not handled in the readline elif chain; it should
        # ring the bell and continue, not raise TypeError at ``len(c)``.
        feed(h, [curses.KEY_PPAGE, chr(10)])
        result = await h.readline()
        assert result == ""


# ===========================================================================
# authentication_ok (async)
# ===========================================================================


class TestAsyncAuthenticationOk:
    async def test_no_callback_returns_true(self):
        h = make_handler()
        h.authCallback = None
        assert await h.authentication_ok() is True

    async def test_no_callback_sets_username_none(self):
        h = make_handler()
        h.authCallback = None
        await h.authentication_ok()
        assert h.username is None

    async def test_sync_callback_called_with_none_args(self):
        h = make_handler()
        cb = mock.MagicMock()
        h.authCallback = cb
        h.authNeedUser = False
        h.authNeedPass = False
        assert await h.authentication_ok() is True
        cb.assert_called_once_with(None, None)

    async def test_sync_callback_exception_returns_false(self):
        h = make_handler()
        h.authCallback = mock.MagicMock(side_effect=ValueError("bad password"))
        h.authNeedUser = False
        h.authNeedPass = False
        assert await h.authentication_ok() is False

    async def test_async_callback_is_awaited(self):
        h = make_handler()
        async_cb = mock.AsyncMock()
        h.authCallback = async_cb
        h.authNeedUser = False
        h.authNeedPass = False
        assert await h.authentication_ok() is True
        async_cb.assert_awaited_once()

    async def test_username_prompt_reads_from_queue(self):
        h = make_handler()
        feed(h, list("alice") + [chr(10)])
        h.authCallback = mock.MagicMock()
        h.authNeedUser = True
        h.authNeedPass = False
        await h.authentication_ok()
        h.authCallback.assert_called_once_with("alice", None)
        assert h.username == "alice"


# ===========================================================================
# handle (async session loop)
# ===========================================================================


class _EchoCommands(Commands):
    @cmd("echo")
    def echo(self, params):
        """<text>
        Echo params back.
        """
        self.handler.writeresponse(" ".join(params))

    @cmd("async_echo")
    async def async_echo(self, params):
        """<text>
        Echo params back asynchronously.
        """
        self.handler.writeresponse(" ".join(params))


class _BaseTestHandler(TelnetHandler):
    WELCOME = "READY"
    PROMPT = "$ "
    authCallback = None
    commands_class = _EchoCommands


class TestAsyncHandle:
    async def test_welcome_written(self):
        h = make_handler(_BaseTestHandler)
        feed(h, list("exit") + [chr(10)])
        await h.handle()
        assert b"READY" in h.writer.written

    async def test_sync_command_executed(self):
        h = make_handler(_BaseTestHandler)
        feed(h, list("echo hello world") + [chr(10)] + list("exit") + [chr(10)])
        await h.handle()
        assert b"hello world" in h.writer.written

    async def test_async_command_executed(self):
        h = make_handler(_BaseTestHandler)
        feed(h, list("async_echo hi") + [chr(10)] + list("exit") + [chr(10)])
        await h.handle()
        assert b"hi" in h.writer.written

    async def test_unknown_command_writes_error(self):
        h = make_handler(_BaseTestHandler)
        feed(h, list("NOSUCHCMD") + [chr(10)] + list("exit") + [chr(10)])
        await h.handle()
        assert b"NOSUCHCMD" in h.writer.written or b"Unknown" in h.writer.written

    async def test_async_command_not_found_is_awaited(self):
        class H(_BaseTestHandler):
            dispatched = False

            class commands_class(_EchoCommands):
                async def _command_not_found(self, cmd, params):
                    H.dispatched = True

        h = make_handler(H)
        feed(h, list("NOSUCHCMD") + [chr(10)] + list("exit") + [chr(10)])
        await h.handle()
        assert H.dispatched is True

    async def test_sync_session_start_called(self):
        class H(_BaseTestHandler):
            started = False
            def session_start(self):
                H.started = True

        h = make_handler(H)
        feed(h, list("exit") + [chr(10)])
        await h.handle()
        assert H.started is True

    async def test_async_session_start_awaited(self):
        class H(_BaseTestHandler):
            started = False
            async def session_start(self):
                H.started = True

        h = make_handler(H)
        feed(h, list("exit") + [chr(10)])
        await h.handle()
        assert H.started is True

    async def test_eof_sentinel_ends_session_cleanly(self):
        h = make_handler(_BaseTestHandler)
        h.cookedq.put_nowait(_EOF_SENTINEL)
        await h.handle()  # must not raise

    async def test_quit_alias_works(self):
        h = make_handler(_BaseTestHandler)
        feed(h, list("quit") + [chr(10)])
        await h.handle()
        assert b"Goodbye" in h.writer.written


# ===========================================================================
# finish (async)
# ===========================================================================


class TestAsyncFinish:
    async def _make_with_done_task(self, handler_class=None):
        h = make_handler(handler_class or _BaseTestHandler)
        done_task = asyncio.create_task(asyncio.sleep(0))
        await done_task
        h._task_ic = done_task
        return h

    async def test_sync_session_end_called(self):
        class H(_BaseTestHandler):
            ended = False
            def session_end(self):
                H.ended = True

        h = await self._make_with_done_task(H)
        await h.finish()
        assert H.ended is True

    async def test_async_session_end_awaited(self):
        class H(_BaseTestHandler):
            ended = False
            async def session_end(self):
                H.ended = True

        h = await self._make_with_done_task(H)
        await h.finish()
        assert H.ended is True

    async def test_writer_closed(self):
        h = await self._make_with_done_task()
        await h.finish()
        assert h.writer._closed is True

    async def test_inputcooker_task_cancelled(self):
        h = make_handler(_BaseTestHandler)
        # A task that would run indefinitely if not cancelled
        h._task_ic = asyncio.create_task(asyncio.sleep(9999))
        await h.finish()
        assert h._task_ic.cancelled()

    async def test_task_ic_cleaned_up_if_setup_raises(self):
        """Bug 4: if setup() raises after creating _task_ic, _run() must cancel
        the task rather than leaking it.

        Uses a never-returning reader so the inputcooker would run forever
        without an explicit cancellation — exposing the leak.
        """
        class _HangingReader:
            async def read(self, n=-1):
                await asyncio.sleep(9999)  # never returns during the test
                return b""

        class BrokenSetupHandler(_BaseTestHandler):
            async def setup(self):
                self.reader = _HangingReader()
                self.setterm(self.TERM)
                self.sock = None
                self._task_ic = asyncio.create_task(self.inputcooker())
                raise RuntimeError("setup failed after task creation")

        h = make_handler(BrokenSetupHandler)
        with pytest.raises(RuntimeError):
            await h._run()

        # One event-loop tick so any cancellation can propagate.
        await asyncio.sleep(0)
        # Without the fix the task keeps sleeping indefinitely (not done).
        assert h._task_ic.done()


# ===========================================================================
# _read_until helper
# ===========================================================================


class TestReadUntil:
    async def test_does_not_use_deprecated_get_event_loop(self):
        """Bug 2: _read_until must call asyncio.get_running_loop(), not the
        deprecated asyncio.get_event_loop()."""
        reader = asyncio.StreamReader()
        reader.feed_data(b"hello")
        reader.feed_eof()

        # Patch get_event_loop to raise so we'd know immediately if it's called.
        with mock.patch("asyncio.get_event_loop", side_effect=RuntimeError("use get_running_loop")):
            result = await _read_until(reader, b"hello", timeout=1.0)

        assert b"hello" in result


# ===========================================================================
# Integration: real asyncio server
# ===========================================================================


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
            chunk = await asyncio.wait_for(reader.read(4096), timeout=min(remaining, 0.3))
        except asyncio.TimeoutError:
            break
        if not chunk:
            break
        buf += _strip_iac(chunk)
    return buf


class _IntegrationHandler(TelnetHandler):
    """Handler for integration tests: no telnet negotiation, no sleep delay."""

    WELCOME = "READY"
    PROMPT = "$ "
    authCallback = None
    commands_class = _EchoCommands
    OPTION_NEGOTIATION_DELAY = 0

    async def setup(self):
        self.setterm(self.TERM)
        self.sock = None
        # Skip option negotiation entirely (no DOACK/WILLACK sends)
        self._task_ic = asyncio.create_task(self.inputcooker())


@pytest.fixture
async def server_addr():
    server = await asyncio.start_server(
        _IntegrationHandler.asyncio_handle, "127.0.0.1", 0
    )
    addr = server.sockets[0].getsockname()
    yield addr
    server.close()
    await server.wait_closed()


class TestAsyncioIntegration:
    async def test_welcome_received(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        data = await _read_until(reader, b"READY")
        assert b"READY" in data
        writer.close()
        await writer.wait_closed()

    async def test_prompt_appears(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        data = await _read_until(reader, b"$ ")
        assert b"$ " in data
        writer.close()
        await writer.wait_closed()

    async def test_sync_echo_command(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"$ ")
        writer.write(b"echo hello world\n")
        data = await _read_until(reader, b"$ ")
        assert b"hello world" in data
        writer.close()
        await writer.wait_closed()

    async def test_async_echo_command(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"$ ")
        writer.write(b"async_echo hello\n")
        data = await _read_until(reader, b"$ ")
        assert b"hello" in data
        writer.close()
        await writer.wait_closed()

    async def test_unknown_command_writes_error(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"$ ")
        writer.write(b"NOSUCH\n")
        data = await _read_until(reader, b"$ ")
        assert b"NOSUCH" in data or b"Unknown" in data
        writer.close()
        await writer.wait_closed()

    async def test_exit_command(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"$ ")
        writer.write(b"exit\n")
        data = await _read_until(reader, b"Goodbye")
        assert b"Goodbye" in data
        writer.close()
        await writer.wait_closed()

    async def test_help_lists_commands(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"$ ")
        writer.write(b"help\n")
        data = await _read_until(reader, b"$ ")
        assert b"ECHO" in data or b"EXIT" in data
        writer.close()
        await writer.wait_closed()

    async def test_abrupt_disconnect_does_not_hang(self, server_addr):
        reader, writer = await asyncio.open_connection(*server_addr)
        await _read_until(reader, b"$ ")
        writer.close()
        await writer.wait_closed()
        # Give the server side a moment to notice the disconnect.
        await asyncio.sleep(0.1)
        # Reaching here without hanging means the handler exited cleanly.
