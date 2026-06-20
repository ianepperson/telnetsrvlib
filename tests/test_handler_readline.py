"""Tests for TelnetHandlerBase.readline and ansi_to_curses."""

import curses
from telnetsrv.telnetsrvlib import theNULL

# ---------------------------------------------------------------------------
# _readline_do_echo
# ---------------------------------------------------------------------------


class TestReadlineDoEcho:
    def test_true_always_echoes(self, handler):
        assert handler._readline_do_echo(True) is True

    def test_false_never_echoes(self, handler):
        assert handler._readline_do_echo(False) is False

    def test_none_follows_doecho_true(self, handler):
        handler.DOECHO = True
        assert handler._readline_do_echo(None) is True

    def test_none_follows_doecho_false(self, handler):
        handler.DOECHO = False
        assert handler._readline_do_echo(None) is False


# ---------------------------------------------------------------------------
# readline basics
# ---------------------------------------------------------------------------


class TestReadline:
    def _feed(self, handler, chars):
        """Load handler.cookedq with a sequence of characters."""
        handler.cookedq = list(chars)

    def test_simple_word(self, handler):
        self._feed(handler, list("hello") + [chr(10)])
        assert handler.readline() == "hello"

    def test_empty_input(self, handler):
        self._feed(handler, [chr(10)])
        assert handler.readline() == ""

    def test_adds_to_history(self, handler):
        self._feed(handler, list("cmd") + [chr(10)])
        handler.readline(use_history=True)
        assert handler.history[-1] == "cmd"

    def test_no_history_when_disabled(self, handler):
        self._feed(handler, list("cmd") + [chr(10)])
        handler.readline(use_history=False)
        assert handler.history == []

    def test_prompt_written_when_doecho_true(self, handler):
        handler.DOECHO = True
        self._feed(handler, [chr(10)])
        handler.readline(prompt="MYPROMPT> ")
        assert b"MYPROMPT> " in handler.sock.sent

    def test_prompt_not_written_when_doecho_false(self, handler):
        handler.DOECHO = False
        self._feed(handler, [chr(10)])
        handler.readline(prompt="MYPROMPT> ")
        assert b"MYPROMPT> " not in handler.sock.sent

    def test_ctrl_c_returns_empty(self, handler):
        self._feed(handler, [chr(3)])
        assert handler.readline() == ""

    def test_ctrl_d_on_empty_line_returns_quit(self, handler):
        self._feed(handler, [chr(4)])
        assert handler.readline() == "QUIT"

    def test_ctrl_d_on_nonempty_line_aborts(self, handler):
        self._feed(handler, list("hi") + [chr(4)])
        assert handler.readline() == ""

    def test_backspace_chr8_removes_last_char(self, handler):
        self._feed(handler, list("helo") + [chr(8)] + [chr(10)])
        assert handler.readline() == "hel"

    def test_backspace_chr127_removes_last_char(self, handler):
        self._feed(handler, list("helo") + [chr(127)] + [chr(10)])
        assert handler.readline() == "hel"

    def test_backspace_at_start_does_nothing(self, handler):
        self._feed(handler, [chr(8)] + list("ok") + [chr(10)])
        assert handler.readline() == "ok"

    def test_backspace_key_removes_last_char(self, handler):
        self._feed(handler, list("helo") + [curses.KEY_BACKSPACE] + [chr(10)])
        assert handler.readline() == "hel"

    def test_delete_key_at_end_does_nothing(self, handler):
        self._feed(handler, list("ab") + [curses.KEY_DC] + [chr(10)])
        assert handler.readline() == "ab"

    def test_left_right_navigation(self, handler):
        # type 'ab', go left, go right, then Enter → 'ab'
        self._feed(
            handler, list("ab") + [curses.KEY_LEFT, curses.KEY_RIGHT] + [chr(10)]
        )
        assert handler.readline() == "ab"

    def test_left_at_start_does_not_crash(self, handler):
        self._feed(handler, [curses.KEY_LEFT] + list("x") + [chr(10)])
        assert handler.readline() == "x"

    def test_right_at_end_does_not_crash(self, handler):
        self._feed(handler, [curses.KEY_RIGHT] + list("x") + [chr(10)])
        assert handler.readline() == "x"

    def test_up_through_history(self, handler):
        handler.history = ["older", "newer"]
        # Up once → 'newer', Enter
        self._feed(handler, [curses.KEY_UP, chr(10)])
        result = handler.readline(use_history=True)
        assert result == "newer"

    def test_up_at_beginning_of_history_does_not_crash(self, handler):
        handler.history = []
        self._feed(handler, [curses.KEY_UP] + list("x") + [chr(10)])
        assert handler.readline() == "x"

    def test_down_at_end_of_history_does_not_crash(self, handler):
        handler.history = ["a"]
        self._feed(handler, [curses.KEY_DOWN] + list("x") + [chr(10)])
        assert handler.readline() == "x"

    def test_control_chars_below_32_rendered_as_unctrl(self, handler):
        # chr(1) is ^A; it should not crash readline
        self._feed(handler, [chr(1), chr(10)])
        result = handler.readline()
        # The unctrl representation of chr(1) is '^A'
        assert "^A" in result or result == ""  # rendered or dropped


# ---------------------------------------------------------------------------
# ansi_to_curses
# ---------------------------------------------------------------------------


class TestAnsiToCurses:
    def test_regular_char_returned_unchanged(self, handler):
        assert handler.ansi_to_curses("a") == "a"

    def test_non_escape_special_char_unchanged(self, handler):
        assert handler.ansi_to_curses(chr(10)) == chr(10)

    def test_escape_up_arrow(self, handler):
        handler.cookedq = ["[", "A"]
        assert handler.ansi_to_curses(chr(27)) == curses.KEY_UP

    def test_escape_down_arrow(self, handler):
        handler.cookedq = ["[", "B"]
        assert handler.ansi_to_curses(chr(27)) == curses.KEY_DOWN

    def test_escape_right_arrow(self, handler):
        handler.cookedq = ["[", "C"]
        assert handler.ansi_to_curses(chr(27)) == curses.KEY_RIGHT

    def test_escape_left_arrow(self, handler):
        handler.cookedq = ["[", "D"]
        assert handler.ansi_to_curses(chr(27)) == curses.KEY_LEFT

    def test_escape_unknown_sequence_returns_null(self, handler):
        handler.cookedq = ["[", "Z"]
        assert handler.ansi_to_curses(chr(27)) == theNULL

    def test_escape_no_bracket_returns_null(self, handler):
        handler.cookedq = ["X"]  # first char after ESC is not '['
        assert handler.ansi_to_curses(chr(27)) == theNULL

    def test_integer_key_code_passthrough(self, handler):
        # Already-translated key codes should pass through unchanged
        assert handler.ansi_to_curses(curses.KEY_UP) == curses.KEY_UP
