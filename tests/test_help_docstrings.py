"""Tests that help correctly derives output from command docstrings.

Docstring format (all three lines required):
  Line 0: parameter synopsis (may be blank)
  Line 1: short description (shown in listing)
  Line 2+: long description (shown in detailed view; falls back to line 1 if absent)
"""

from telnetsrv.telnetsrvlib import cmd, Commands
from tests.conftest import make_handler


def recv(handler) -> str:
    return handler.sock.sent.decode("latin-1")


def make_commands_for_help(handler, **fns):
    """Return a Commands instance populated with the given name→function entries.

    Each fn is a plain callable with __doc__ set and optionally command_name /
    hidden attributes (from the @cmd decorator).  Each entry is wrapped in its
    own function object so the same fn can safely be passed under multiple names
    without the entries clobbering each other's command_name attribute.
    """
    class_dict = {}
    for name, fn in fns.items():
        cmd_name = getattr(fn, "command_name", name.lower())
        hidden = getattr(fn, "hidden", False)
        doc = fn.__doc__

        def _make_wrapper(f, cname, h, d):
            def wrapper(self, params):
                return f(params)

            wrapper.__doc__ = d
            wrapper.command_name = cname
            wrapper.aliases = []
            wrapper.hidden = h
            return wrapper

        class_dict[f"_testfn_{name}"] = _make_wrapper(fn, cmd_name, hidden, doc)

    TestCommands = type("TestCommands", (Commands,), class_dict)
    return TestCommands(handler)


# ---------------------------------------------------------------------------
# Brief listing (no argument to help)
# ---------------------------------------------------------------------------


class TestBriefListing:
    def test_params_and_short_description_shown(self):
        def fn(params):
            """<arg1> <arg2>
            Do a thing.
            """

        h = make_handler()
        commands = make_commands_for_help(h, foo=fn)
        commands.help([])
        output = recv(h)
        assert "FOO" in output
        assert "<arg1> <arg2>" in output
        assert "Do a thing." in output

    def test_no_params_shows_dash_and_short_description(self):
        def fn(params):
            """
            Do another thing.
            """

        h = make_handler()
        commands = make_commands_for_help(h, bar=fn)
        commands.help([])
        output = recv(h)
        assert "BAR" in output
        assert "Do another thing." in output
        # Empty params line → "- <short>" not "<params> - <short>"
        assert "- Do another thing." in output

    def test_long_description_not_shown_in_listing(self):
        def fn(params):
            """<x>
            Short blurb.
            This is the long description that should not appear in the listing.
            """

        h = make_handler()
        commands = make_commands_for_help(h, baz=fn)
        commands.help([])
        output = recv(h)
        assert "Short blurb." in output
        assert "long description" not in output

    def test_hidden_command_excluded_from_listing(self):
        @cmd("secret", hidden=True)
        def fn(params):
            """
            Super secret.
            """

        h = make_handler()
        commands = make_commands_for_help(h, secret=fn)
        commands.help([])
        assert "SECRET" not in recv(h)

    def test_non_hidden_command_included_in_listing(self):
        @cmd("visible")
        def fn(params):
            """
            Visible command.
            """

        h = make_handler()
        commands = make_commands_for_help(h, visible=fn)
        commands.help([])
        assert "VISIBLE" in recv(h)

    def test_commands_appear_in_sorted_order(self):
        def fn(params):
            """
            A command.
            """

        h = make_handler()
        commands = make_commands_for_help(h, zebra=fn, apple=fn, mango=fn)
        commands.help([])
        output = recv(h)
        apple_pos = output.find("APPLE")
        mango_pos = output.find("MANGO")
        zebra_pos = output.find("ZEBRA")
        assert apple_pos < mango_pos < zebra_pos


# ---------------------------------------------------------------------------
# Detailed help (help called with a specific command name)
# ---------------------------------------------------------------------------


class TestDetailedHelp:
    def test_params_and_long_description_shown(self):
        def fn(params):
            """<file>
            Short blurb.
            This is the long description that explains the command in detail.
            """

        h = make_handler()
        commands = make_commands_for_help(h, mycmd=fn)
        commands.help(["MYCMD"])
        output = recv(h)
        assert "MYCMD" in output
        assert "<file>" in output
        assert "long description" in output

    def test_short_description_not_used_as_long_when_long_exists(self):
        def fn(params):
            """<x>
            Short blurb.
            This is the real long description.
            """

        h = make_handler()
        commands = make_commands_for_help(h, mycmd=fn)
        commands.help(["MYCMD"])
        output = recv(h)
        assert "real long description" in output
        assert "Short blurb." not in output

    def test_falls_back_to_short_description_when_no_long(self):
        def fn(params):
            """<x>
            Only a short description here.
            """

        h = make_handler()
        commands = make_commands_for_help(h, mycmd=fn)
        commands.help(["MYCMD"])
        output = recv(h)
        assert "Only a short description here." in output

    def test_multiline_long_description_fully_shown(self):
        def fn(params):
            """
            Short.
            Line one of long.
            Line two of long.
            Line three of long.
            """

        h = make_handler()
        commands = make_commands_for_help(h, mycmd=fn)
        commands.help(["MYCMD"])
        output = recv(h)
        assert "Line one of long." in output
        assert "Line two of long." in output
        assert "Line three of long." in output

    def test_unknown_command_reports_not_known(self):
        h = make_handler()
        commands = Commands(h)
        commands.help(["NOSUCHCMD"])
        assert "not known" in recv(h)

    def test_command_name_case_insensitive(self):
        def fn(params):
            """
            Case insensitive lookup.
            """

        h = make_handler()
        commands = make_commands_for_help(h, mycase=fn)
        commands.help(["mycase"])
        output = recv(h)
        assert "Case insensitive lookup." in output
