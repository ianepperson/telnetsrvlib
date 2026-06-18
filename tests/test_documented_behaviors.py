"""Tests for documented behaviors not covered elsewhere.

Each section references the README section it validates.
"""

from unittest import mock

from telnetsrv.telnetsrvlib import cmd, Commands
from tests.conftest import ConcreteHandler, make_handler


def recv(handler) -> str:
    return handler.sock.sent.decode("latin-1")


# ---------------------------------------------------------------------------
# Old-style cmdXxx prefix registration (README: "Old Style" section)
# ---------------------------------------------------------------------------


class TestOldStyleCmdPrefix:
    def test_cmdXxx_method_registered_as_command(self):
        class MyCommands(Commands):
            def cmdECHO(self, params):
                """
                Echo params.
                """
                self.handler.writeresponse(" ".join(params))

        h = make_handler()
        commands = MyCommands(h)
        assert "ECHO" in commands._Commands__all_commands

    def test_cmdXxx_is_callable_via_commands_dict(self):
        results = []

        class MyCommands(Commands):
            def cmdGREET(self, params):
                """
                Greet.
                """
                results.append(params)

        h = make_handler()
        commands = MyCommands(h)
        commands("GREET", ["hello"])
        assert results == [["hello"]]

    def test_cmdXxx_prefix_stripped_from_name(self):
        class MyCommands(Commands):
            def cmdFOO(self, params):
                """
                Foo.
                """
                pass

        h = make_handler()
        commands = MyCommands(h)
        assert "FOO" in commands._Commands__all_commands
        assert "CMDFOO" not in commands._Commands__all_commands

    def test_cmdXxx_case_insensitive_lookup_via_dispatch(self):
        seen = []

        class MyCommands(Commands):
            def cmdPING(self, params):
                """
                Ping.
                """
                seen.append(True)

        class MyHandler(ConcreteHandler):
            commands_class = MyCommands

        h = make_handler(MyHandler)
        readline_calls = iter(["ping", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert seen == [True]


# ---------------------------------------------------------------------------
# Hidden commands still show detailed help (README: "Hidden Commands" section)
# ---------------------------------------------------------------------------


class TestHiddenCommandDetailedHelp:
    def test_hidden_command_absent_from_listing(self):
        class MyCommands(Commands):
            @cmd("secret", hidden=True)
            def secret(self, params):
                """
                Secret details.
                """

        h = make_handler()
        commands = MyCommands(h)
        commands.help([])
        assert "SECRET" not in recv(h)

    def test_hidden_command_shows_detail_when_named(self):
        class MyCommands(Commands):
            @cmd("secret", hidden=True)
            def secret(self, params):
                """
                Secret details.
                Long explanation of the secret command.
                """

        h = make_handler()
        commands = MyCommands(h)
        commands.help(["SECRET"])
        output = recv(h)
        assert "SECRET" in output
        assert "Long explanation" in output

    def test_hidden_stacked_decorator_still_shows_detail(self):
        class MyCommands(Commands):
            @cmd("pub")
            @cmd("priv", hidden=True)
            def pub_or_priv(self, params):
                """
                Details.
                Extended details here.
                """

        h = make_handler()
        commands = MyCommands(h)
        commands.help(["PRIV"])
        assert "Extended details here." in recv(h)


# ---------------------------------------------------------------------------
# session_end called after disconnect (README: "Handler Options" section)
# ---------------------------------------------------------------------------


class TestSessionEnd:
    def test_session_end_called_on_finish(self):
        calls = []

        class MyHandler(ConcreteHandler):
            def session_end(self):
                calls.append(True)

        h = make_handler(MyHandler)
        h.finish()
        assert calls == [True]

    def test_session_end_default_does_not_raise(self):
        h = make_handler()
        h.finish()  # default session_end is a no-op


# ---------------------------------------------------------------------------
# PROMPT and CONTINUE_PROMPT defaults (README: "Handler Options" section)
# ---------------------------------------------------------------------------


class TestPromptDefaults:
    def test_prompt_default(self):
        h = make_handler()
        assert h.PROMPT == "Telnet Server> "

    def test_continue_prompt_default(self):
        h = make_handler()
        assert h.CONTINUE_PROMPT == "... "

    def test_prompt_can_be_overridden(self):
        class MyHandler(ConcreteHandler):
            PROMPT = "$ "

        h = make_handler(MyHandler)
        assert h.PROMPT == "$ "

    def test_continue_prompt_can_be_overridden(self):
        class MyHandler(ConcreteHandler):
            CONTINUE_PROMPT = ">> "

        h = make_handler(MyHandler)
        assert h.CONTINUE_PROMPT == ">> "


# ---------------------------------------------------------------------------
# Overriding write methods in a subclass (README: "Handler Display Modification")
# ---------------------------------------------------------------------------


class TestWriteMethodOverrides:
    def test_writeerror_override_wraps_output(self):
        class MyHandler(ConcreteHandler):
            def writeerror(self, text):
                ConcreteHandler.writeerror(self, "[ERR] " + text)

        h = make_handler(MyHandler)
        h.writeerror("something broke")
        assert "[ERR] something broke" in recv(h)

    def test_writeresponse_override_wraps_output(self):
        class MyHandler(ConcreteHandler):
            def writeresponse(self, text):
                ConcreteHandler.writeresponse(self, "> " + text)

        h = make_handler(MyHandler)
        h.writeresponse("data line")
        assert "> data line" in recv(h)

    def test_writemessage_override_wraps_output(self):
        class MyHandler(ConcreteHandler):
            def writemessage(self, text):
                ConcreteHandler.writemessage(self, "** " + text)

        h = make_handler(MyHandler)
        h._current_prompt = ""
        h._current_line = []
        h.writemessage("async notice")
        assert "** async notice" in recv(h)

    def test_override_active_during_command_dispatch(self):
        errors_seen = []

        class MyHandler(ConcreteHandler):
            def writeerror(self, text):
                errors_seen.append(text)
                ConcreteHandler.writeerror(self, text)

        h = make_handler(MyHandler)
        readline_calls = iter(["NOSUCHCMD", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert any("NOSUCHCMD" in e for e in errors_seen)


# ---------------------------------------------------------------------------
# readline(echo=False) suppresses character echo (README: "Receive Text" section)
# ---------------------------------------------------------------------------


class TestReadlineEcho:
    def _feed(self, handler, chars):
        handler.cookedq = list(chars)

    def test_echo_true_sends_chars_to_socket(self):
        h = make_handler()
        h.DOECHO = True
        self._feed(h, list("abc") + [chr(10)])
        h.readline(echo=True)
        assert b"a" in h.sock.sent

    def test_echo_false_does_not_send_input_chars(self):
        h = make_handler()
        h.DOECHO = True
        self._feed(h, list("secret") + [chr(10)])
        h.sock.sent = b""
        h.readline(echo=False)
        for ch in b"secret":
            assert bytes([ch]) not in h.sock.sent

    def test_echo_false_still_returns_correct_value(self):
        h = make_handler()
        self._feed(h, list("mypassword") + [chr(10)])
        result = h.readline(echo=False)
        assert result == "mypassword"

    def test_echo_false_does_not_add_to_history(self):
        h = make_handler()
        self._feed(h, list("secret") + [chr(10)])
        h.readline(echo=False, use_history=False)
        assert h.history == []
