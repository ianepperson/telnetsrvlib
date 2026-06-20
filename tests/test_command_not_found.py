"""Tests for command_not_found handling."""

from unittest import mock

from telnetsrv.telnetsrvlib import Commands
from tests.conftest import ConcreteHandler, make_handler


def recv(handler) -> str:
    return handler.sock.sent.decode("latin-1")


# ---------------------------------------------------------------------------
# Default behaviour
# ---------------------------------------------------------------------------


class TestCommandNotFoundDefault:
    def test_writes_error_for_unknown_command(self, handler):
        readline_calls = iter(["NOSUCHCMD", "exit"])
        with mock.patch.object(handler, "readline", side_effect=readline_calls):
            handler.handle()
        assert "NOSUCHCMD" in recv(handler)

    def test_direct_call_writes_error(self, handler):
        handler.command_not_found("FOO", [])
        assert "FOO" in recv(handler)

    def test_direct_call_uses_writeerror(self, handler):
        with mock.patch.object(handler, "writeerror") as mock_err:
            handler.command_not_found("FOO", [])
        mock_err.assert_called_once()
        assert "FOO" in mock_err.call_args[0][0]


# ---------------------------------------------------------------------------
# Override: correct arguments delivered
# ---------------------------------------------------------------------------


class TestCommandNotFoundOverride:
    def _handler_with_capture(self):
        """Return a handler plus a list that records _command_not_found calls."""
        calls = []

        class MyCommands(Commands):
            def _command_not_found(self, command, params):
                calls.append((command, params))

        class MyHandler(ConcreteHandler):
            commands_class = MyCommands

        return make_handler(MyHandler), calls

    def test_override_receives_command_name(self):
        h, calls = self._handler_with_capture()
        readline_calls = iter(["UNKNOWN", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert calls[0][0] == "UNKNOWN"

    def test_override_command_name_is_uppercased(self):
        h, calls = self._handler_with_capture()
        readline_calls = iter(["unknown", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert calls[0][0] == "UNKNOWN"

    def test_override_receives_empty_params_for_bare_command(self):
        h, calls = self._handler_with_capture()
        readline_calls = iter(["NOSUCHCMD", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert calls[0][1] == []

    def test_override_receives_single_param(self):
        h, calls = self._handler_with_capture()
        readline_calls = iter(["NOSUCHCMD arg1", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert calls[0][1] == ["arg1"]

    def test_override_receives_multiple_params(self):
        h, calls = self._handler_with_capture()
        readline_calls = iter(["NOSUCHCMD foo bar baz", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert calls[0][1] == ["foo", "bar", "baz"]

    def test_override_receives_quoted_param_as_single_token(self):
        h, calls = self._handler_with_capture()
        readline_calls = iter(['NOSUCHCMD "hello world"', "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert calls[0][1] == ["hello world"]

    def test_override_can_suppress_default_error_output(self):
        class SilentCommands(Commands):
            def _command_not_found(self, command, params):
                pass  # swallow silently

        class SilentHandler(ConcreteHandler):
            commands_class = SilentCommands

        h = make_handler(SilentHandler)
        readline_calls = iter(["NOSUCHCMD", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert "NOSUCHCMD" not in recv(h)

    def test_override_called_once_per_unknown_command(self):
        h, calls = self._handler_with_capture()
        readline_calls = iter(["FIRST", "SECOND", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert len(calls) == 2
        assert calls[0][0] == "FIRST"
        assert calls[1][0] == "SECOND"

    def test_known_command_does_not_trigger_override(self):
        h, calls = self._handler_with_capture()
        readline_calls = iter(["help", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert calls == []
