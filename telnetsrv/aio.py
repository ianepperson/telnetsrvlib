#!/usr/bin/python
# Async Telnet handler using Python's asyncio

from __future__ import annotations

import asyncio
import curses
import curses.ascii
import logging
import sys
from typing import Any

from .constants import (
    ANSI_KEY_TO_CURSES,
    ANSI_START_SEQ,
    BELL,
    DO,
    DONT,
    ESC,
    IAC,
    NOOPT,
    SB,
    SE,
    WILL,
    WONT,
    theNULL,
)
from .telnetsrvlib import (
    TelnetHandlerBase,
    cmd,
    Commands,
)

__all__ = ["TelnetHandler", "cmd", "Commands"]

log = logging.getLogger(__name__)

# Sentinel placed in the cooked queue when the connection closes.
_EOF_SENTINEL = object()


class AsyncInputBashLike:
    """Async version of InputBashLike.

    Because InputBashLike.process() may call handler.readline() to gather
    continuation lines, and readline() is now a coroutine, the entire
    input-reader must be async.  Use the ``create`` classmethod instead of
    the constructor.
    """

    quote_chars = ['"', "'"]
    whitespace = [" ", "\t"]
    escape_char = "\\"
    escape_results = {
        "\\": "\\",
        "t": "\t",
        "n": "\n",
        " ": " ",
        '"': '"',
        "'": "'",
    }
    eol_char = "\n"

    @classmethod
    async def create(cls, handler: "TelnetHandler", line: str) -> "AsyncInputBashLike":
        """Async factory — create and fully process one input line."""
        instance = cls.__new__(cls)
        instance.raw = ""
        instance.handler = handler
        instance.complete = False
        instance.inquote: str | bool = False
        instance.parts: list[str] = []
        instance.part: list[str] = []
        instance.process_char = instance.process_delimiter
        await instance._process(line)
        return instance

    @property
    def cmd(self) -> str:
        try:
            return self.parts[0]
        except IndexError:
            return ""

    @property
    def params(self) -> list[str]:
        return self.parts[1:]

    # -- character-state machine (identical to InputBashLike) --

    def process_delimiter(self, char: str) -> None:
        if char in self.whitespace:
            return
        if char in self.quote_chars:
            self.inquote = char
            self.process_char = self.process_quote
            return
        if char == self.eol_char:
            self.complete = True
            return
        self.process_char = self.process_part
        self.process_char(char)

    def process_part(self, char: str) -> None:
        if char in self.whitespace or char == self.eol_char:
            self.parts.append("".join(self.part))
            self.part = []
            self.process_char = self.process_delimiter
            if char == self.eol_char:
                self.complete = True
            return
        if char in self.quote_chars:
            self.inquote = char
            self.process_char = self.process_quote
            return
        self.part.append(char)

    def process_quote(self, char: str) -> None:
        if char == self.inquote:
            self.process_char = self.process_part
            return
        self.part.append(char)

    def process_escape(self, char: str) -> None:
        self.process_char = self.last_process_char
        if self.part == [] and char in self.whitespace:
            self.parts.append(self.escape_char)
            return
        if char == self.eol_char:
            return
        unescaped = self.escape_results.get(char, self.escape_char + char)
        self.part.append(unescaped)

    async def _process(self, line: str) -> None:
        """Step through the line; await handler.readline() for continuation."""
        self.raw = self.raw + line
        try:
            if not line[-1] == self.eol_char:
                line = line + self.eol_char
        except IndexError:
            line = self.eol_char

        for char in line:
            if char == self.escape_char:
                self.last_process_char = self.process_char
                self.process_char = self.process_escape
                continue
            self.process_char(char)

        if not self.complete:
            continuation = await self.handler.readline(
                prompt=self.handler.CONTINUE_PROMPT
            )
            await self._process(continuation)


class TelnetHandler(TelnetHandlerBase):
    """An asyncio-based telnet server handler.

    Usage::

        import asyncio
        from telnetsrv.aio import TelnetHandler, cmd, Commands

        class MyCommands(Commands):
            @cmd('echo')
            async def echo(self, params):
                self.handler.writeresponse(' '.join(params))

        class MyHandler(TelnetHandler):
            commands_class = MyCommands

        async def main():
            server = await asyncio.start_server(
                MyHandler.asyncio_handle, host='', port=8023
            )
            async with server:
                await server.serve_forever()

        asyncio.run(main())

    Command methods may be either regular functions or coroutines; the handler
    detects and awaits coroutines automatically.

    ``session_start`` and ``session_end`` may also be defined as coroutines.
    """

    input_reader = AsyncInputBashLike
    OPTION_NEGOTIATION_DELAY: float = 0.5

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        # Do NOT call TelnetHandlerBase.__init__: that delegates to
        # socketserver.BaseRequestHandler.__init__ which synchronously invokes
        # setup() → handle() → finish().  We manage the lifecycle ourselves.
        self._task_ic: asyncio.Task | None = None
        self.DOECHO = True
        self.DOOPTS: dict[str, bool | None] = {}
        self.WILLOPTS: dict[str, bool | str] = {}
        self.COMMANDS: dict[str, Any] = {}
        self.sock = None
        self.rawq = ""
        self.sbdataq = ""
        self.eof = 0
        self.iacseq = ""
        self.sb = 0
        self.history: list[str] = []
        self.RUNSHELL = True
        self.WIDTH = 80
        self.HEIGHT = 24
        self._current_line: str | list[str] = ""
        self._current_prompt: str = ""

        self.reader = reader
        self.writer = writer
        self.client_address = writer.get_extra_info("peername", ("unknown", 0))
        self.request = None
        self.server = None

        self.cookedq: asyncio.Queue = asyncio.Queue()

    # -------------------------------------------------------------------------
    # Entry point

    @classmethod
    async def asyncio_handle(
        cls,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Entry point for ``asyncio.start_server``.

        Pass this classmethod directly to ``asyncio.start_server``::

            server = await asyncio.start_server(MyHandler.asyncio_handle, ...)
        """
        handler = cls(reader, writer)
        await handler._run()

    async def _run(self) -> None:
        """Full connection lifecycle: setup → handle → finish."""
        try:
            await self.setup()
        except BaseException:
            await self._cancel_task_ic()
            raise
        try:
            await self.handle()
        finally:
            await self.finish()

    async def _cancel_task_ic(self) -> None:
        """Cancel the inputcooker task if it was created, swallowing CancelledError."""
        if self._task_ic is not None and not self._task_ic.done():
            self._task_ic.cancel()
            try:
                await self._task_ic
            except asyncio.CancelledError:
                pass

    # -------------------------------------------------------------------------
    # Lifecycle

    async def setup(self) -> None:
        """Set up the connection and negotiate telnet options."""
        self.setterm(self.TERM)
        try:
            self.sock = self.writer.get_extra_info("socket")
        except Exception:
            self.sock = None

        for k in self.DOACK.keys():
            self.sendcommand(self.DOACK[k], k)
        for k in self.WILLACK.keys():
            self.sendcommand(self.WILLACK[k], k)
        await self.writer.drain()

        self._task_ic = asyncio.create_task(self.inputcooker())

        # Allow options negotiation to complete before the session begins.
        await asyncio.sleep(self.OPTION_NEGOTIATION_DELAY)

    async def finish(self) -> None:
        """Tear down the connection and call session_end."""
        log.debug("Session disconnected.")
        await self._cancel_task_ic()
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass
        result = self.session_end()
        if asyncio.iscoroutine(result):
            await result

    # -------------------------------------------------------------------------
    # Async input handling

    async def getc(self, block: bool = True) -> str | int:
        """Return one character from the cooked input queue."""
        if not block:
            try:
                item = self.cookedq.get_nowait()
            except asyncio.QueueEmpty:
                return ""
        else:
            item = await self.cookedq.get()

        if item is _EOF_SENTINEL:
            # Re-queue the sentinel so subsequent getc() calls also see EOF.
            self.cookedq.put_nowait(_EOF_SENTINEL)
            raise EOFError
        return item

    def inputcooker_socket_ready(self) -> bool:
        """Return True if the raw buffer already holds unprocessed bytes."""
        return bool(self.rawq)

    def inputcooker_store_queue(self, char: str | int) -> None:
        """Put cooked data into the async queue."""
        if isinstance(char, (tuple, list, str)):
            for v in char:
                self.cookedq.put_nowait(v)
        else:
            self.cookedq.put_nowait(char)

    async def _inputcooker_getc(self, block: bool = True) -> str:
        """Get one raw character, reading from the stream when necessary."""
        if self.rawq:
            ret = self.rawq[0]
            self.rawq = self.rawq[1:]
            return ret
        if not block:
            # Non-blocking peek: only return what's already buffered.
            return ""
        data = await self.reader.read(20)
        self.eof = not bool(data)
        self.rawq = self.rawq + data.decode("latin-1")
        if self.eof:
            raise EOFError
        return await self._inputcooker_getc(block)

    async def inputcooker(self) -> None:
        """Background task: translate raw bytes into cooked characters."""
        try:
            while True:
                c = await self._inputcooker_getc()
                if not self.iacseq:
                    if c == IAC:
                        self.iacseq += c
                        continue
                    elif c == chr(13) and not self.sb:
                        c2 = await self._inputcooker_getc(block=False)
                        if c2 == theNULL or c2 == "":
                            c = chr(10)
                        elif c2 == chr(10):
                            c = c2
                        else:
                            self._inputcooker_ungetc(c2)
                            c = chr(10)
                    elif c in [x[0] for x in self.ESCSEQ.keys()]:
                        codes = c
                        for keyseq in self.ESCSEQ.keys():
                            if len(keyseq) == 0:
                                continue
                            while codes == keyseq[: len(codes)] and len(codes) <= len(
                                keyseq
                            ):
                                if codes == keyseq:
                                    c = self.ESCSEQ[keyseq]
                                    break
                                codes = codes + await self._inputcooker_getc()
                            if codes == keyseq:
                                break
                            self._inputcooker_ungetc(codes[1:])
                            codes = codes[0]
                    self._inputcooker_store(c)
                elif len(self.iacseq) == 1:
                    if c in (DO, DONT, WILL, WONT):
                        self.iacseq += c
                        continue
                    self.iacseq = ""
                    if c == IAC:
                        self._inputcooker_store(c)
                    else:
                        if c == SB:
                            self.sb = 1
                            self.sbdataq = ""
                        elif c == SE:
                            self.sb = 0
                        self.options_handler(self.sock, c, NOOPT)
                elif len(self.iacseq) == 2:
                    cmd = self.iacseq[1]
                    self.iacseq = ""
                    if cmd in (DO, DONT, WILL, WONT):
                        self.options_handler(self.sock, cmd, c)
        except asyncio.CancelledError:
            raise
        except (EOFError, ConnectionError, OSError):
            self.eof = 1
            self.cookedq.put_nowait(_EOF_SENTINEL)

    # -------------------------------------------------------------------------
    # Async output

    def writecooked(self, text: str) -> None:
        """Buffer data for sending via the asyncio StreamWriter."""
        self.writer.write(text.encode("latin-1"))

    # -------------------------------------------------------------------------
    # Async readline

    async def ansi_to_curses(self, char: str | int) -> str | int:
        """Async ANSI escape-sequence handler."""
        if char != ESC:
            return char
        if await self.getc(block=True) != ANSI_START_SEQ:
            self._readline_echo(BELL, True)
            return theNULL
        key = await self.getc(block=True)
        try:
            return ANSI_KEY_TO_CURSES[key]
        except (KeyError, TypeError):
            self._readline_echo(BELL, True)
            return theNULL

    async def readline(
        self, echo: bool | None = None, prompt: str = "", use_history: bool = True
    ) -> str:
        """Async readline — wait for a complete line of user input.

        Signature matches ``TelnetHandlerBase.readline`` so that existing
        handler subclasses can call ``await self.readline(...)`` unchanged.
        """
        line: list[str] = []
        insptr = 0
        histptr = len(self.history)

        if self.DOECHO:
            self.write(prompt)
            self._current_prompt = prompt
        else:
            self._current_prompt = ""

        self._current_line = ""
        await self.writer.drain()

        while True:
            c = await self.getc(block=True)
            c = await self.ansi_to_curses(c)
            if c == theNULL:
                continue

            elif c == curses.KEY_LEFT:
                if insptr > 0:
                    insptr -= 1
                    self._readline_echo(self.CODES["CSRLEFT"], echo)
                else:
                    self._readline_echo(BELL, echo)
                continue
            elif c == curses.KEY_RIGHT:
                if insptr < len(line):
                    insptr += 1
                    self._readline_echo(self.CODES["CSRRIGHT"], echo)
                else:
                    self._readline_echo(BELL, echo)
                continue
            elif c == curses.KEY_UP or c == curses.KEY_DOWN:
                if not use_history:
                    self._readline_echo(BELL, echo)
                    continue
                if c == curses.KEY_UP:
                    if histptr > 0:
                        histptr -= 1
                    else:
                        self._readline_echo(BELL, echo)
                        continue
                elif c == curses.KEY_DOWN:
                    if histptr < len(self.history):
                        histptr += 1
                    else:
                        self._readline_echo(BELL, echo)
                        continue
                line = []
                if histptr < len(self.history):
                    line.extend(self.history[histptr])
                for _ in range(insptr):
                    self._readline_echo(self.CODES["CSRLEFT"], echo)
                self._readline_echo(self.CODES["DEOL"], echo)
                self._readline_echo("".join(line), echo)
                insptr = len(line)
                continue
            elif c == chr(3):
                self._readline_echo("\n" + curses.ascii.unctrl(c) + " ABORT\n", echo)
                return ""
            elif c == chr(4):
                if len(line) > 0:
                    self._readline_echo(
                        "\n" + curses.ascii.unctrl(c) + " ABORT (QUIT)\n", echo
                    )
                    return ""
                self._readline_echo("\n" + curses.ascii.unctrl(c) + " QUIT\n", echo)
                return "QUIT"
            elif c == chr(10):
                self._readline_echo(c, echo)
                result = "".join(line)
                if use_history:
                    self.history.append(result)
                if echo is False:
                    if prompt:
                        self.write(chr(10))
                    log.debug("readline: %s(hidden text)", prompt)
                else:
                    log.debug("readline: %s%r", prompt, result)
                return result
            elif c == curses.KEY_BACKSPACE or c == chr(127) or c == chr(8):
                if insptr > 0:
                    self._readline_echo(self.CODES["CSRLEFT"] + self.CODES["DEL"], echo)
                    insptr -= 1
                    del line[insptr]
                else:
                    self._readline_echo(BELL, echo)
                continue
            elif c == curses.KEY_DC:
                if insptr < len(line):
                    self._readline_echo(self.CODES["DEL"], echo)
                    del line[insptr]
                else:
                    self._readline_echo(BELL, echo)
                continue
            else:
                if not isinstance(c, str):
                    # Unrecognised integer key code (e.g. KEY_HOME, KEY_PPAGE).
                    self._readline_echo(BELL, echo)
                    continue
                if ord(c) < 32:
                    c = curses.ascii.unctrl(c)
                if len(line) > insptr:
                    self._readline_insert(c, echo, insptr, line)
                else:
                    self._readline_echo(c, echo)
            line[insptr:insptr] = c
            insptr += len(c)
            if self._readline_do_echo(echo):
                self._current_line = line
        return ""  # unreachable; satisfies type checkers

    # -------------------------------------------------------------------------
    # Authentication

    async def authentication_ok(self) -> bool:
        """Async version of authentication_ok."""
        username = None
        password = None
        if self.authCallback:
            if self.authNeedUser:
                username = await self.readline(
                    prompt=self.PROMPT_USER, use_history=False
                )
            if self.authNeedPass:
                password = await self.readline(
                    echo=False, prompt=self.PROMPT_PASS, use_history=False
                )
                if self.DOECHO:
                    self.write("\n")
            try:
                result = self.authCallback(username, password)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                self.username = None
                return False
            else:
                self.username = username
                return True
        else:
            self.username = None
            return True

    # -------------------------------------------------------------------------
    # Session handler

    async def handle(self) -> None:
        """The async telnet session loop."""
        if self.TELNET_ISSUE:
            self.writeline(self.TELNET_ISSUE)
        if not await self.authentication_ok():
            return
        if self.DOECHO:
            self.writeline(self.WELCOME)

        result = self.session_start()
        if asyncio.iscoroutine(result):
            await result

        commands = self.commands_class(self)
        try:
            while self.RUNSHELL:
                raw_input = (await self.readline(prompt=self.PROMPT)).strip()
                self.input = await AsyncInputBashLike.create(self, raw_input)
                self.raw_input = self.input.raw
                if self.input.cmd:
                    cmd_name = self.input.cmd.upper()
                    params = self.input.params
                    try:
                        cmd_result = commands(cmd_name, params)
                        if asyncio.iscoroutine(cmd_result):
                            await cmd_result
                    except Exception:
                        log.exception("Error calling %s.", cmd_name)
                        t, p, tb = sys.exc_info()
                        if self.handleException(t, p, tb):
                            break
                await self.writer.drain()
        except EOFError:
            log.debug("Connection closed by remote host")
        log.debug("Exiting async handler")
