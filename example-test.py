"""Tests for example.py — the bundled demonstration server."""

import sys
import threading
from unittest import mock

import pytest

# example.py calls argparse.parse_args() at import time; supply the required port arg.
with mock.patch("sys.argv", ["example", "8023"]):
    import example

from example import MyServer, MyCommands, ExampleTelnetHandler

from tests.conftest import make_handler


def recv(handler) -> str:
    return handler.sock.sent.decode("latin-1")


def make_example_handler():
    return make_handler(ExampleTelnetHandler)


# ---------------------------------------------------------------------------
# MyServer
# ---------------------------------------------------------------------------


class TestMyServer:
    def test_initial_connection_count_is_zero(self):
        """A freshly created server starts with no recorded connections."""
        s = MyServer()
        assert s.connection_count == 0

    def test_initial_user_connect_is_empty(self):
        """A freshly created server has no per-user history."""
        s = MyServer()
        assert s.user_connect == {}

    def test_first_connection_returns_one_one(self):
        """The first ever connection returns global count 1 and user count 1."""
        s = MyServer()
        global_count, user_count = s.new_connection("alice")
        assert global_count == 1
        assert user_count == 1

    def test_global_count_increments_across_different_users(self):
        """Each call to new_connection increments the shared global counter."""
        s = MyServer()
        s.new_connection("alice")
        global_count, _ = s.new_connection("bob")
        assert global_count == 2

    def test_per_user_count_increments_on_reconnect(self):
        """The same username connecting twice gets a user count of 2."""
        s = MyServer()
        s.new_connection("alice")
        _, user_count = s.new_connection("alice")
        assert user_count == 2

    def test_different_users_have_independent_counts(self):
        """Each username's count is tracked independently from other users."""
        s = MyServer()
        _, alice_count = s.new_connection("alice")
        _, bob_count = s.new_connection("bob")
        assert alice_count == 1
        assert bob_count == 1

    def test_global_count_tracks_all_connections(self):
        """connection_count reflects the total across all calls, not just unique users."""
        s = MyServer()
        for _ in range(5):
            s.new_connection("alice")
        assert s.connection_count == 5


# ---------------------------------------------------------------------------
# Helpers for MyCommands tests
# ---------------------------------------------------------------------------


class MockHandler:
    """Minimal handler stub for MyCommands unit tests."""

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

    def readline(self, prompt="", echo=True, use_history=True):
        return self._readline_responses.pop(0) if self._readline_responses else ""


# ---------------------------------------------------------------------------
# MyCommands
# ---------------------------------------------------------------------------


class TestMyCommands:
    def setup_method(self):
        self.handler = MockHandler()
        self.cmds = MyCommands(self.handler)

    def test_params_echoes_repr_of_params(self):
        """The params command writes the repr of its argument list back to the client."""
        self.cmds.params(["hello", "world"])
        assert any("['hello', 'world']" in r for r in self.handler.responses)

    def test_debug_writes_one_line_per_escape_sequence(self):
        """The debug command emits exactly one response line per entry in ESCSEQ."""
        self.handler.ESCSEQ = {"\x1b[A": 1}
        self.handler.KEYS = {1: "UP"}
        self.cmds.debug([])
        assert len(self.handler.responses) == 1

    def test_debug_includes_key_name(self):
        """Each debug line contains the human-readable key name from KEYS."""
        self.handler.ESCSEQ = {"\x1b[A": 1}
        self.handler.KEYS = {1: "UP"}
        self.cmds.debug([])
        assert "UP" in self.handler.responses[0]

    def test_info_contains_username(self):
        """The info command reports the currently logged-in username."""
        self.cmds.info([])
        combined = " ".join(self.handler.responses)
        assert "testuser" in combined

    def test_info_contains_term(self):
        """The info command reports the terminal type string."""
        self.cmds.info([])
        combined = " ".join(self.handler.responses)
        assert "xterm" in combined

    def test_info_contains_width_and_height(self):
        """The info command reports the terminal dimensions."""
        self.cmds.info([])
        combined = " ".join(self.handler.responses)
        assert "80" in combined
        assert "24" in combined

    def test_info_lists_history_entries(self):
        """The info command includes every entry from the command history."""
        self.cmds.info([])
        combined = " ".join(self.handler.responses)
        assert "cmd1" in combined
        assert "cmd2" in combined

    def test_echo_joins_params(self):
        """The ECHO command joins multiple words with a space before writing."""
        self.cmds.cmdECHO(["hello", "world"])
        assert "hello world" in self.handler.responses

    def test_echo_single_word(self):
        """The ECHO command works with a single word parameter."""
        self.cmds.cmdECHO(["hello"])
        assert "hello" in self.handler.responses

    def test_timer_no_params_writes_error(self):
        """The timer command writes an error when called with no arguments."""
        self.cmds.timer([])
        assert self.handler.errors

    def test_timer_non_integer_time_writes_error(self):
        """The timer command writes an error when the time argument is not an integer."""
        self.cmds.timer(["notanumber", "hello"])
        assert self.handler.errors

    def test_timer_schedules_threading_event(self):
        """A valid timer call appends a threading.Timer to handler.timer_events."""
        self.cmds.timer(["60", "hello world"])
        assert len(self.handler.timer_events) == 1
        self.handler.timer_events[0].cancel()

    def test_timer_writes_waiting_message(self):
        """A valid timer call confirms the delay to the client before firing."""
        self.cmds.timer(["60", "hello"])
        assert any("Waiting" in r for r in self.handler.responses)
        self.handler.timer_events[0].cancel()

    def test_set_password_matching_writes_success(self):
        """Entering the same password twice results in a success response."""
        self.handler._readline_responses = ["secret123", "secret123"]
        self.cmds.set_password([])
        assert any("Pretending" in r for r in self.handler.responses)

    def test_set_password_mismatch_writes_error(self):
        """Entering different passwords at the two prompts results in an error."""
        self.handler._readline_responses = ["secret123", "wrong"]
        self.cmds.set_password([])
        assert self.handler.errors

    def test_set_password_from_params_strips_history(self):
        """When the password is passed as a parameter, it is removed from history to prevent snooping."""
        self.handler.history = ["passwd mysecret"]
        self.handler._readline_responses = ["mysecret"]  # confirmation readline
        self.cmds.set_password(["mysecret"])
        assert self.handler.history[-1] == "passwd"

    def test_connections_shows_count(self):
        """The connections command displays the total connection count from myserver."""
        self.handler.myserver.connection_count = 7
        self.cmds.connections([])
        combined = " ".join(self.handler.responses)
        assert "7" in combined

    def test_users_shows_each_username(self):
        """The users command lists every username that has ever connected."""
        self.handler.myserver.user_connect = {"alice": 3, "bob": 1}
        self.cmds.users([])
        combined = " ".join(self.handler.responses)
        assert "alice" in combined
        assert "bob" in combined

    def test_users_shows_connection_counts(self):
        """The users command includes the per-user connection count alongside each name."""
        self.handler.myserver.user_connect = {"alice": 3}
        self.cmds.users([])
        combined = " ".join(self.handler.responses)
        assert "3" in combined

    def test_command_do_nothing_writes_response(self):
        """The do-nothing command still sends a confirmation message to the client."""
        self.cmds.command_do_nothing([])
        assert any("nothing" in r.lower() for r in self.handler.responses)


# ---------------------------------------------------------------------------
# ExampleTelnetHandler
# ---------------------------------------------------------------------------


class TestExampleHandler:
    def test_prompt_is_configured(self):
        """The handler uses the example-specific prompt string."""
        assert ExampleTelnetHandler.PROMPT == "TestServer> "

    def test_welcome_mentions_test_server(self):
        """The WELCOME message identifies this as the test server."""
        assert "test server" in ExampleTelnetHandler.WELCOME.lower()

    def test_auth_need_user_is_true(self):
        """The handler requires a username to be entered at login."""
        assert ExampleTelnetHandler.authNeedUser is True

    def test_auth_need_pass_is_false(self):
        """The handler does not request a password at login."""
        assert ExampleTelnetHandler.authNeedPass is False

    def test_auth_callback_accepts_nonempty_username(self):
        """Any non-empty username is accepted by authCallback."""
        h = make_example_handler()
        h.authCallback("alice", "")  # must not raise

    def test_auth_callback_rejects_empty_username(self):
        """An empty username causes authCallback to raise, denying the login."""
        h = make_example_handler()
        with pytest.raises(BaseException):
            h.authCallback("", "")

    def test_session_start_initializes_timer_events(self):
        """session_start creates an empty timer_events list for tracking async events."""
        h = make_example_handler()
        h.username = "alice"
        h.session_start()
        assert h.timer_events == []

    def test_session_start_writes_username(self):
        """session_start greets the user by name."""
        h = make_example_handler()
        h.username = "alice"
        h.session_start()
        assert "alice" in recv(h)

    def test_session_start_writes_server_type(self):
        """session_start reports which server backend (threaded/green/eventlet) is running."""
        h = make_example_handler()
        h.username = "alice"
        h.session_start()
        assert "threaded" in recv(h)

    def test_session_start_writes_connection_count(self):
        """session_start reports the incremented global connection number to the client."""
        h = make_example_handler()
        h.username = "alice"
        before = ExampleTelnetHandler.myserver.connection_count
        h.session_start()
        # myserver is a class-level singleton; verify the count incremented
        assert str(before + 1) in recv(h)

    def test_session_end_cancels_pending_timer_events(self):
        """session_end calls cancel() on any outstanding timer so it does not fire after logout."""
        h = make_example_handler()
        h.username = "alice"
        h.session_start()
        mock_timer = mock.MagicMock()
        h.timer_events = [mock_timer]
        h.session_end()
        mock_timer.cancel.assert_called_once()

    def test_session_end_cancels_multiple_timers(self):
        """session_end cancels every timer in the list, not just the first."""
        h = make_example_handler()
        h.username = "alice"
        h.session_start()
        timers = [mock.MagicMock(), mock.MagicMock()]
        h.timer_events = timers
        h.session_end()
        for t in timers:
            t.cancel.assert_called_once()

    def test_writeerror_wraps_text_in_ansi_red(self):
        """writeerror surrounds the message with ANSI red escape codes for color display."""
        h = make_example_handler()
        h.writeerror("bad input")
        output = recv(h)
        assert "\x1b[91m" in output
        assert "bad input" in output
        assert "\x1b[0m" in output

    def test_commands_class_is_my_commands(self):
        """The handler is wired to dispatch commands through MyCommands."""
        assert ExampleTelnetHandler.commands_class is MyCommands
