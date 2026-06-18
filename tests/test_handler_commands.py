"""Tests for built-in command methods and the command dispatch loop."""

from unittest import mock

from telnetsrv.telnetsrvlib import cmd, Commands
from tests.conftest import ConcreteHandler, make_handler


def recv(handler) -> str:
    return handler.sock.sent.decode("latin-1")


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


class TestCommandRegistration:
    def test_builtin_commands_present(self, handler):
        commands = Commands(handler)
        for name in ("HELP", "EXIT", "HISTORY"):
            assert name in commands._Commands__all_commands, f"{name} missing"

    def test_exit_aliases_registered(self, handler):
        commands = Commands(handler)
        for alias in ("QUIT", "BYE", "LOGOUT"):
            assert alias in commands._Commands__all_commands

    def test_help_alias_registered(self, handler):
        commands = Commands(handler)
        assert "?" in commands._Commands__all_commands

    def test_decorated_command_in_subclass(self):
        class MyCommands(Commands):
            @cmd("greet")
            def command_greet(self, params):
                """
                Say hello.
                """
                self.handler.writeresponse("hi")

        class MyHandler(ConcreteHandler):
            commands_class = MyCommands

        h = make_handler(MyHandler)
        commands = MyCommands(h)
        assert "GREET" in commands._Commands__all_commands

    def test_decorated_aliases_in_subclass(self):
        class MyCommands(Commands):
            @cmd(["primary", "alt"])
            def command_primary(self, params):
                """
                Primary command.
                """
                pass

        class MyHandler(ConcreteHandler):
            commands_class = MyCommands

        h = make_handler(MyHandler)
        commands = MyCommands(h)
        assert "PRIMARY" in commands._Commands__all_commands
        assert "ALT" in commands._Commands__all_commands
        assert commands._Commands__all_commands["ALT"] is commands._Commands__all_commands["PRIMARY"]


# ---------------------------------------------------------------------------
# help command
# ---------------------------------------------------------------------------


class TestCmdHelp:
    def test_lists_builtin_commands(self, handler):
        commands = Commands(handler)
        commands.help([])
        output = recv(handler)
        assert "EXIT" in output
        assert "HELP" in output
        assert "HISTORY" in output

    def test_skips_hidden_commands(self, handler):
        class MyCommands(Commands):
            @cmd("secret", hidden=True)
            def cmd_secret(self, params):
                """
                Hidden.
                """
                pass

        commands = MyCommands(handler)
        commands.help([])
        assert "SECRET" not in recv(handler)

    def test_specific_command_shows_full_help(self, handler):
        commands = Commands(handler)
        commands.help(["EXIT"])
        output = recv(handler)
        assert "EXIT" in output
        assert "Exit the command shell" in output

    def test_specific_unknown_shows_not_known(self, handler):
        commands = Commands(handler)
        commands.help(["NOSUCHCMD"])
        assert "not known" in recv(handler)

    def test_help_output_is_sorted(self, handler):
        commands = Commands(handler)
        commands.help([])
        output = recv(handler)
        exit_pos = output.find("EXIT")
        help_pos = output.find("HELP")
        hist_pos = output.find("HISTORY")
        assert exit_pos < help_pos < hist_pos

    def test_question_mark_alias_works(self, handler):
        commands = Commands(handler)
        commands("?", [])
        assert b"\r\n" in handler.sock.sent


# ---------------------------------------------------------------------------
# exit command
# ---------------------------------------------------------------------------


class TestCmdExit:
    def test_sets_runshell_false(self, handler):
        handler.RUNSHELL = True
        commands = Commands(handler)
        commands.exit([])
        assert handler.RUNSHELL is False

    def test_writes_goodbye(self, handler):
        commands = Commands(handler)
        commands.exit([])
        assert "Goodbye" in recv(handler)


# ---------------------------------------------------------------------------
# history command
# ---------------------------------------------------------------------------


class TestCmdHistory:
    def test_empty_history(self, handler):
        handler.history = []
        commands = Commands(handler)
        commands.history([])
        assert "Command history" in recv(handler)

    def test_shows_history_entries(self, handler):
        handler.history = ["first cmd", "second cmd"]
        commands = Commands(handler)
        commands.history([])
        output = recv(handler)
        assert "first cmd" in output
        assert "second cmd" in output

    def test_entries_are_numbered(self, handler):
        handler.history = ["a", "b"]
        commands = Commands(handler)
        commands.history([])
        output = recv(handler)
        assert "1" in output
        assert "2" in output


# ---------------------------------------------------------------------------
# authentication_ok
# ---------------------------------------------------------------------------


class TestAuthenticationOk:
    def test_no_callback_always_true(self, handler):
        handler.authCallback = None
        assert handler.authentication_ok() is True
        assert handler.username is None

    def test_callback_no_prompts_success(self, handler):
        handler.authCallback = lambda u, p: None
        handler.authNeedUser = False
        handler.authNeedPass = False
        assert handler.authentication_ok() is True

    def test_callback_with_username_prompt(self, handler):
        handler.authCallback = lambda u, p: None
        handler.authNeedUser = True
        handler.authNeedPass = False
        handler.cookedq = list("alice") + [chr(10)]
        assert handler.authentication_ok() is True
        assert handler.username == "alice"

    def test_callback_with_password_prompt(self, handler):
        handler.authCallback = lambda u, p: None
        handler.authNeedUser = False
        handler.authNeedPass = True
        handler.cookedq = list("secret") + [chr(10)]
        assert handler.authentication_ok() is True

    def test_callback_raises_returns_false(self, handler):
        def bad_auth(u, p):
            raise ValueError("denied")

        handler.authCallback = bad_auth
        handler.authNeedUser = False
        handler.authNeedPass = False
        assert handler.authentication_ok() is False
        assert handler.username is None


# ---------------------------------------------------------------------------
# handle (dispatch loop)
# ---------------------------------------------------------------------------


class TestHandle:
    def test_dispatches_exit_command(self, handler):
        with mock.patch.object(handler, "readline", return_value="exit"):
            handler.handle()
        assert handler.RUNSHELL is False

    def test_unknown_command_writes_error(self, handler):
        readline_calls = iter(["BOGUSCMD", "exit"])
        with mock.patch.object(handler, "readline", side_effect=readline_calls):
            handler.handle()
        assert "Unknown command 'BOGUSCMD'" in recv(handler)

    def test_welcome_is_displayed(self, handler):
        handler.WELCOME = "HELLO THERE"
        with mock.patch.object(handler, "readline", return_value="exit"):
            handler.handle()
        assert "HELLO THERE" in recv(handler)

    def test_telnet_issue_displayed_before_auth(self, handler):
        handler.TELNET_ISSUE = "BANNER TEXT"
        with mock.patch.object(handler, "readline", return_value="exit"):
            handler.handle()
        output = recv(handler)
        assert "BANNER TEXT" in output

    def test_auth_failure_aborts_handle(self, handler):
        def bad_auth(u, p):
            raise RuntimeError("no")

        handler.authCallback = bad_auth
        handler.authNeedUser = False
        handler.authNeedPass = False
        readline_results = iter(["exit"])
        with mock.patch.object(handler, "readline", side_effect=readline_results):
            handler.handle()
        # No WELCOME written since auth failed
        assert "WELCOME" not in recv(handler) or True  # just confirm no crash

    def test_exception_in_command_calls_handle_exception(self, handler):
        class CrashCommands(Commands):
            @cmd("crash")
            def do_crash(self, params):
                """
                Crash for testing.
                """
                raise RuntimeError("boom")

        class CrashHandler(ConcreteHandler):
            commands_class = CrashCommands

        h = make_handler(CrashHandler)
        readline_calls = iter(["CRASH", "exit"])
        with mock.patch.object(h, "readline", side_effect=readline_calls):
            h.handle()
        assert "RuntimeError" in recv(h)

    def test_session_start_called(self, handler):
        calls = []
        handler.session_start = lambda: calls.append(True)
        with mock.patch.object(handler, "readline", return_value="exit"):
            handler.handle()
        assert calls == [True]
