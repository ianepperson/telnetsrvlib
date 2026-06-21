#!/usr/bin/python

import asyncio
import curses.ascii
import logging
import argparse

logging.getLogger("").setLevel(logging.DEBUG)

TELNET_IP_BINDING = ""  # all interfaces

parser = argparse.ArgumentParser(description="Run an asyncio telnet server.")
parser.add_argument(
    "port", metavar="PORT", type=int, help="The port on which to listen."
)
parser.add_argument(
    "-s",
    "--ssh",
    action="store_const",
    const=True,
    default=False,
    help="Run as SSH server using Paramiko library.",
)
console_args = parser.parse_args()

TELNET_PORT_BINDING = console_args.port

from telnetsrv.aio import TelnetHandler, cmd, Commands  # noqa: E402


class MyCommands(Commands):
    """Commands for the asyncio example server."""

    @cmd
    def debug(self, params):
        """
        Display some debugging data
        """
        for v, k in self.handler.ESCSEQ.items():
            line = "%-10s : " % (self.handler.KEYS[k],)
            for c in v:
                if ord(c) < 32 or ord(c) > 126:
                    line = line + curses.ascii.unctrl(c)
                else:
                    line = line + c
            self.handler.writeresponse(line)

    @cmd
    def params(self, params):
        """[<params>]*
        Echos back the raw received parameters.
        """
        self.handler.writeresponse("params == %r" % params)

    @cmd
    def info(self, params):
        """
        Provides some information about the current terminal.
        """
        self.handler.writeresponse(
            f"Username: {self.handler.username}, " f"terminal type: {self.handler.TERM}"
        )
        self.handler.writeresponse(
            f"Width: {self.handler.WIDTH}, height: {self.handler.HEIGHT}"
        )
        self.handler.writeresponse("Command history:")
        for c in self.handler.history:
            self.handler.writeresponse("  %r" % c)

    @cmd(["timer", "timeit"])
    async def timer(self, params):
        """<time> <message>
        In <time> seconds, display <message>.
        Send a message after a delay.
        <time> is in seconds.
        If <message> is more than one word, quotes are required.

        example: TIMER 5 "hello world!"
        """
        try:
            timestr, message = params[:2]
            delay = int(timestr)
        except ValueError:
            self.handler.writeerror("Need both a time and a message")
            return
        self.handler.writeresponse("Waiting %d seconds..." % delay)

        async def _fire():
            await asyncio.sleep(delay)
            self.handler.writemessage(message)

        task = asyncio.create_task(_fire())
        self.handler.timer_events.append(task)

    @cmd("passwd")
    async def set_password(self, params):
        """[<password>]
        Pretends to set a console password.
        Demonstrates how sensitive information may be handled.
        """
        try:
            password = params[0]
        except IndexError:
            password = await self.handler.readline(
                prompt="New Password: ", echo=False, use_history=False
            )
        else:
            # Strip the password from history to prevent easy snooping.
            self.handler.history[-1] = "passwd"

        password2 = await self.handler.readline(
            prompt="Retype New Password: ", echo=False, use_history=False
        )
        if password == password2:
            self.handler.writeresponse(
                "Pretending to set new password, but not really."
            )
        else:
            self.handler.writeerror("Passwords don't match.")

    def cmdECHO(self, params):
        """<text to echo>
        Echo text back to the console.

        """
        self.handler.writeresponse(" ".join(params))

    cmdECHO.aliases = ["REPEAT"]

    def cmdTERM(self, params):
        """
        Hidden command to print the current TERM
        """
        self.handler.writeresponse(self.handler.TERM)

    cmdTERM.hidden = True

    @cmd("hide-me", hidden=True)
    @cmd(["hide-me-too", "also-me"])
    def command_do_nothing(self, params):
        """
        Hidden command to perform no action
        """
        self.handler.writeresponse("Nope, did nothing.")

    @cmd
    def connections(self, params: list[str]) -> None:
        """
        Show how many logins there have been.
        """
        self.handler.writeresponse(
            f"There have been {self.handler.myserver.connection_count} connections"
        )

    @cmd(["who", "users"])
    def users(self, params: list[str]) -> None:
        """
        Show who has logged in.
        """
        for user, count in self.handler.myserver.user_connect.items():
            self.handler.writeresponse(f"{user} : {count}")


class MyServer:
    """A simple server class that keeps track of connection counts."""

    def __init__(self):
        self.connection_count = 0
        self.user_connect = {}

    def new_connection(self, username):
        """Register a new connection by username, return the count of connections."""
        self.connection_count += 1
        try:
            self.user_connect[username] += 1
        except KeyError:
            self.user_connect[username] = 1
        return self.connection_count, self.user_connect[username]


class ExampleTelnetHandler(TelnetHandler):
    commands_class = MyCommands
    myserver = MyServer()

    WELCOME = "You have connected to the asyncio test server."
    PROMPT = "TestServer> "
    authNeedUser = True
    authNeedPass = False

    def authCallback(self, username, password):
        """Called to validate the username/password."""
        if not username:
            raise ValueError("Username required")

    def session_start(self):
        """Called after the user successfully logs in."""
        self.writeline("This server is running asyncio.")
        globalcount, usercount = self.myserver.new_connection(self.username)
        self.writeline("Hello %s!" % self.username)
        self.writeline(
            "You are connection #%d, you have logged in %s time(s)."
            % (globalcount, usercount)
        )
        self.timer_events = []

    def session_end(self):
        """Called after the user logs off."""
        for task in self.timer_events:
            task.cancel()

    def writeerror(self, text):
        """Write errors in ANSI red."""
        TelnetHandler.writeerror(self, "\x1b[91m%s\x1b[0m" % text)


if __name__ == "__main__":
    if console_args.ssh:
        # SSH transport is blocking and thread-based (Paramiko).  Each connection
        # gets its own thread; asyncio.run() is called inside that thread to drive
        # the async TelnetHandler for that session.
        import socketserver
        from telnetsrv.aio_ssh import AsyncSSHHandler, getRsaKeyFile

        # Wire ExampleTelnetHandler as the PTY session handler and load (or
        # generate) the RSA host key that identifies this server to clients.
        class TestSSHHandler(AsyncSSHHandler):
            telnet_handler = ExampleTelnetHandler
            host_key = getRsaKeyFile("server_rsa.key")

        # allow_reuse_address avoids "address already in use" on quick restarts.
        class TelnetServer(socketserver.TCPServer):
            allow_reuse_address = True

        # Bind and hand each accepted connection to TestSSHHandler.
        server = TelnetServer(
            (TELNET_IP_BINDING or "0.0.0.0", TELNET_PORT_BINDING), TestSSHHandler
        )
        logging.info(
            "Starting asyncio SSH server at port %d.  (Ctrl-C to stop)"
            % TELNET_PORT_BINDING
        )
        try:
            # Block here, dispatching connections until Ctrl-C.
            server.serve_forever()
        except KeyboardInterrupt:
            logging.info("Server shut down.")
    else:
        # Plain telnet: the handler runs entirely inside a single asyncio event loop.
        async def main():
            # Start the TCP listener; asyncio_handle is called for each new connection.
            server = await asyncio.start_server(
                ExampleTelnetHandler.asyncio_handle,
                host=TELNET_IP_BINDING or "0.0.0.0",
                port=TELNET_PORT_BINDING,
            )
            logging.info(
                "Starting asyncio telnet server at port %d.  (Ctrl-C to stop)"
                % TELNET_PORT_BINDING
            )
            # async with keeps server open; serve_forever() suspends until cancelled.
            async with server:
                await server.serve_forever()

        try:
            # Run the event loop until main() exits or KeyboardInterrupt is raised.
            asyncio.run(main())
        except KeyboardInterrupt:
            logging.info("Server shut down.")
