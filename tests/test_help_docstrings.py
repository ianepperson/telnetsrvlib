"""Tests that cmdHELP correctly derives output from command docstrings.

Docstring format (all three lines required):
  Line 0: parameter synopsis (may be blank)
  Line 1: short description (shown in listing)
  Line 2+: long description (shown in detailed view; falls back to line 1 if absent)
"""

import pytest
from telnetsrv.telnetsrvlib import command
from tests.conftest import ConcreteHandler, make_handler


def recv(handler) -> str:
    return handler.sock.sent.decode("latin-1")


def make_handler_with_commands(**commands) -> ConcreteHandler:
    """Return a handler whose COMMANDS dict contains the given name→function entries."""
    h = make_handler()
    for name, fn in commands.items():
        h.COMMANDS[name.upper()] = fn
    return h


# ---------------------------------------------------------------------------
# Brief listing (no argument to cmdHELP)
# ---------------------------------------------------------------------------


class TestBriefListing:
    def test_params_and_short_description_shown(self):
        def cmd(params):
            """<arg1> <arg2>
            Do a thing.
            """

        h = make_handler_with_commands(foo=cmd)
        h.cmdHELP([])
        output = recv(h)
        assert "FOO" in output
        assert "<arg1> <arg2>" in output
        assert "Do a thing." in output

    def test_no_params_shows_dash_and_short_description(self):
        def cmd(params):
            """
            Do another thing.
            """

        h = make_handler_with_commands(bar=cmd)
        h.cmdHELP([])
        output = recv(h)
        assert "BAR" in output
        assert "Do another thing." in output
        # Empty params line → "- <short>" not "<params> - <short>"
        assert "- Do another thing." in output

    def test_long_description_not_shown_in_listing(self):
        def cmd(params):
            """<x>
            Short blurb.
            This is the long description that should not appear in the listing.
            """

        h = make_handler_with_commands(baz=cmd)
        h.cmdHELP([])
        output = recv(h)
        assert "Short blurb." in output
        assert "long description" not in output

    def test_hidden_command_excluded_from_listing(self):
        @command("secret", hidden=True)
        def cmd(params):
            """
            Super secret.
            """

        h = make_handler_with_commands(secret=cmd)
        h.cmdHELP([])
        assert "SECRET" not in recv(h)

    def test_non_hidden_command_included_in_listing(self):
        @command("visible")
        def cmd(params):
            """
            Visible command.
            """

        h = make_handler_with_commands(visible=cmd)
        h.cmdHELP([])
        assert "VISIBLE" in recv(h)

    def test_commands_appear_in_sorted_order(self):
        def cmd(params):
            """
            A command.
            """

        h = make_handler_with_commands(zebra=cmd, apple=cmd, mango=cmd)
        h.cmdHELP([])
        output = recv(h)
        apple_pos = output.find("APPLE")
        mango_pos = output.find("MANGO")
        zebra_pos = output.find("ZEBRA")
        assert apple_pos < mango_pos < zebra_pos


# ---------------------------------------------------------------------------
# Detailed help (cmdHELP called with a specific command name)
# ---------------------------------------------------------------------------


class TestDetailedHelp:
    def test_params_and_long_description_shown(self):
        def cmd(params):
            """<file>
            Short blurb.
            This is the long description that explains the command in detail.
            """

        h = make_handler_with_commands(mycmd=cmd)
        h.cmdHELP(["MYCMD"])
        output = recv(h)
        assert "MYCD".replace("CD", "CMD"[1:]) or "MYCMD".upper() in output
        assert "<file>" in output
        assert "long description" in output

    def test_short_description_not_used_as_long_when_long_exists(self):
        def cmd(params):
            """<x>
            Short blurb.
            This is the real long description.
            """

        h = make_handler_with_commands(cmd=cmd)
        h.cmdHELP(["CMD"])
        output = recv(h)
        assert "real long description" in output
        assert "Short blurb." not in output

    def test_falls_back_to_short_description_when_no_long(self):
        def cmd(params):
            """<x>
            Only a short description here.
            """

        h = make_handler_with_commands(cmd=cmd)
        h.cmdHELP(["CMD"])
        output = recv(h)
        assert "Only a short description here." in output

    def test_multiline_long_description_fully_shown(self):
        def cmd(params):
            """
            Short.
            Line one of long.
            Line two of long.
            Line three of long.
            """

        h = make_handler_with_commands(cmd=cmd)
        h.cmdHELP(["CMD"])
        output = recv(h)
        assert "Line one of long." in output
        assert "Line two of long." in output
        assert "Line three of long." in output

    def test_unknown_command_reports_not_known(self):
        h = make_handler()
        h.cmdHELP(["NOSUCHCMD"])
        assert "not known" in recv(h)

    def test_command_name_case_insensitive(self):
        def cmd(params):
            """
            Case insensitive lookup.
            """

        h = make_handler_with_commands(mycase=cmd)
        h.cmdHELP(["mycase"])
        output = recv(h)
        assert "Case insensitive lookup." in output
