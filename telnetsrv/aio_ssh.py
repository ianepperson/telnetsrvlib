#!/usr/bin/python
# Async SSH handler - pairs an asyncio TelnetHandler with a Paramiko SSH transport

from __future__ import annotations

import asyncio
import logging
from socketserver import BaseRequestHandler
from threading import Thread

from paramiko import Transport

from .paramiko_ssh import (
    SSHHandler,
    getRsaKeyFile,  # noqa: F401 — re-exported for user convenience
)

log = logging.getLogger(__name__)


class AsyncTelnetToPtyHandler:
    """Mixin that adapts an ``aio.TelnetHandler`` for use as an SSH PTY.

    Splice this before the user's ``TelnetHandler`` in the MRO so that:

    * Telnet option negotiation is suppressed (SSH handles the terminal).
    * Authentication is skipped (SSH already authenticated the user).
    """

    DOACK = {}
    WILLACK = {}

    async def authentication_ok(self) -> bool:
        """Accept every connection; use the username supplied by SSH."""
        self.username = getattr(self, "_ssh_username", None)
        return True


class _AsyncChannelReader:
    """Adapts a Paramiko channel into an asyncio-compatible reader.

    Internally wraps an ``asyncio.StreamReader`` and feeds it from the
    blocking Paramiko channel using the thread-pool executor.
    """

    def __init__(self, channel) -> None:
        self._channel = channel
        self._reader: asyncio.StreamReader = asyncio.StreamReader()

    async def start_feed(self) -> None:
        """Background coroutine: pump channel bytes into the StreamReader."""
        loop = asyncio.get_running_loop()
        try:
            while True:
                data = await loop.run_in_executor(None, self._channel.recv, 1024)
                if not data:
                    self._reader.feed_eof()
                    return
                self._reader.feed_data(data)
        except asyncio.CancelledError:
            self._reader.feed_eof()
        except Exception:
            self._reader.feed_eof()

    async def read(self, n: int = -1) -> bytes:
        return await self._reader.read(n)


class _AsyncChannelWriter:
    """Adapts a Paramiko channel into a minimal asyncio writer-compatible object.

    Writes are synchronous (``channel.sendall`` flushes immediately).
    The SSH transport closes the channel, so ``close`` / ``wait_closed``
    are intentional no-ops here.
    """

    def __init__(self, channel) -> None:
        self._channel = channel

    def write(self, data: bytes) -> None:
        try:
            self._channel.sendall(data)
        except Exception:
            pass

    async def drain(self) -> None:
        """No-op: sendall() is synchronous."""

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass

    def get_extra_info(self, name, default=None):
        return default


class AsyncSSHHandler(SSHHandler):
    """SSH handler whose PTY sessions run inside an ``asyncio`` event loop.

    Point ``telnet_handler`` at a ``telnetsrv.aio.TelnetHandler`` subclass::

        from telnetsrv.aio_ssh import AsyncSSHHandler, getRsaKeyFile
        from telnetsrv.aio import TelnetHandler, cmd, Commands

        class MyCommands(Commands):
            @cmd('echo')
            async def echo(self, params):
                self.handler.writeresponse(' '.join(params))

        class MyHandler(TelnetHandler):
            commands_class = MyCommands

        class MySSHHandler(AsyncSSHHandler):
            host_key = getRsaKeyFile('server_rsa.key')
            telnet_handler = MyHandler

    Serve it with any of the usual server types::

        import socketserver

        class TelnetServer(socketserver.TCPServer):
            allow_reuse_address = True

        server = TelnetServer(('', 8022), MySSHHandler)
        server.serve_forever()

    Or with gevent (after ``monkey.patch_all()``)::

        import gevent.server
        server = gevent.server.StreamServer(('', 8022), MySSHHandler.streamserver_handle)
        server.serve_forever()

    Notes
    -----
    Paramiko's SSH transport is blocking and thread-based.  The SSH
    handshake and channel negotiation therefore still run in a thread, as
    with the sync ``SSHHandler``.  Once a PTY channel is established,
    ``asyncio.run()`` creates a fresh event loop in that thread and runs
    the async ``TelnetHandler`` inside it.  Each SSH session gets its own
    dedicated event loop.
    """

    telnet_handler = None  # set to a telnetsrv.aio.TelnetHandler subclass

    def __init__(self, request, client_address, server):
        self.request = request
        self.client_address = client_address
        self.tcp_server = server

        self.channels = {}

        self.client = getattr(request, "_sock", request)
        self.transport = Transport(self.client)

        TelnetHandlerClass = self.telnet_handler

        class AsyncMixedPtyHandler(AsyncTelnetToPtyHandler, TelnetHandlerClass):
            def __init__(self_inner, reader, writer):
                TelnetHandlerClass.__init__(self_inner, reader, writer)

        self._async_pty_handler = AsyncMixedPtyHandler
        self.pty_handler = None  # not used; kept to avoid AttributeError

        BaseRequestHandler.__init__(self, request, client_address, server)

    # ------------------------------------------------------------------
    # PTY lifecycle

    def start_pty_request(self, channel, term, modes):
        """Run the async TelnetHandler in a fresh event loop (blocks the thread)."""
        term_str = term.decode() if isinstance(term, bytes) else term
        asyncio.run(self._run_pty_coro(channel, term_str))
        self.transport.close()

    async def _run_pty_coro(self, channel, term: str) -> None:
        """Coroutine that wires the Paramiko channel to the async TelnetHandler."""
        channel_reader = _AsyncChannelReader(channel)
        channel_writer = _AsyncChannelWriter(channel)

        handler = self._async_pty_handler(channel_reader, channel_writer)
        handler.TERM = term
        handler._ssh_username = self.username
        handler.client_address = self.client_address

        feed_task = asyncio.create_task(channel_reader.start_feed())
        try:
            await handler._run()
        finally:
            feed_task.cancel()
            try:
                await feed_task
            except asyncio.CancelledError:
                pass
