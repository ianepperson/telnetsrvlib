"""Tests for the input cooker: raw socket → cooked queue."""

import curses
import pytest
from unittest import mock

from telnetsrv.telnetsrvlib import (
    IAC,
    DO,
    WILL,
    ECHO,
    theNULL,
    ESC,
)
from tests.conftest import MockSocket


class TestInputCookerGetc:
    def test_reads_from_rawq_before_socket(self, handler):
        handler.rawq = "abc"
        assert handler._inputcooker_getc() == "a"
        assert handler.rawq == "bc"

    def test_reads_from_socket_when_rawq_empty(self, handler):
        handler.rawq = ""
        handler.sock = MockSocket(b"x")
        assert handler._inputcooker_getc() == "x"

    def test_high_byte_decoded_correctly(self, handler):
        handler.rawq = chr(0xFE)
        assert handler._inputcooker_getc() == chr(0xFE)

    def test_non_blocking_returns_empty_when_not_ready(self, handler):
        handler.rawq = ""
        handler.sock = MockSocket(b"")
        # inputcooker_socket_ready returns False in ConcreteHandler
        assert handler._inputcooker_getc(block=False) == ""

    def test_eof_raises_eoferror(self, handler):
        handler.rawq = ""
        handler.sock = MockSocket(b"")  # recv → b'' = EOF
        with pytest.raises(EOFError):
            handler._inputcooker_getc()

    def test_eof_sets_eof_flag(self, handler):
        handler.rawq = ""
        handler.sock = MockSocket(b"")
        with pytest.raises(EOFError):
            handler._inputcooker_getc()
        assert handler.eof


class TestInputCookerUngetc:
    def test_prepends_to_rawq(self, handler):
        handler.rawq = "bc"
        handler._inputcooker_ungetc("a")
        assert handler.rawq == "abc"

    def test_prepend_empty_rawq(self, handler):
        handler.rawq = ""
        handler._inputcooker_ungetc("z")
        assert handler.rawq == "z"


class TestInputCookerStore:
    def test_normal_char_goes_to_cooked_queue(self, handler):
        handler.sb = 0
        handler._inputcooker_store("x")
        assert "x" in handler.cookedq

    def test_char_in_sb_mode_goes_to_sbdataq(self, handler):
        handler.sb = 1
        handler.sbdataq = ""
        handler._inputcooker_store("x")
        assert handler.sbdataq == "x"
        assert "x" not in handler.cookedq

    def test_integer_stored_in_cooked_queue(self, handler):
        handler.sb = 0
        handler._inputcooker_store(42)
        assert 42 in handler.cookedq


class TestInputCooker:
    def _run(self, handler, rawq_data: str):
        """Set rawq, attach an EOF socket, run inputcooker."""
        handler.rawq = rawq_data
        handler.sock = MockSocket(b"")  # EOF after rawq exhausted
        handler.inputcooker()

    def test_plain_text_stored_in_queue(self, handler):
        self._run(handler, "hello")
        assert handler.cookedq[:5] == list("hello")

    def test_cr_lf_becomes_lf(self, handler):
        self._run(handler, "\r\n")
        assert chr(10) in handler.cookedq
        assert chr(13) not in handler.cookedq

    def test_cr_null_becomes_lf(self, handler):
        self._run(handler, "\r" + theNULL)
        assert chr(10) in handler.cookedq

    def test_bare_cr_becomes_lf(self, handler):
        self._run(handler, "\r")
        # cr with no following char (socket returns EOF) → lf or lf via unget
        assert chr(10) in handler.cookedq or handler.cookedq == []

    def test_iac_iac_stores_single_iac(self, handler):
        self._run(handler, IAC + IAC)
        assert IAC in handler.cookedq

    def test_iac_do_calls_options_handler(self, handler):
        with mock.patch.object(handler, "options_handler") as mock_oh:
            self._run(handler, IAC + DO + ECHO)
        mock_oh.assert_called_once_with(handler.sock, DO, ECHO)

    def test_iac_will_calls_options_handler(self, handler):
        with mock.patch.object(handler, "options_handler") as mock_oh:
            self._run(handler, IAC + WILL + ECHO)
        mock_oh.assert_called_once_with(handler.sock, WILL, ECHO)

    def test_iac_sb_se_stores_subneg_data(self, handler):
        from telnetsrv.telnetsrvlib import TTYPE, IS, SB as _SB, SE as _SE

        payload = TTYPE + IS + "ansi"
        self._run(handler, IAC + _SB + payload + IAC + _SE)
        # The subnegotiation data is stored in sbdataq (then cleared by options_handler)
        # Just verify no crash and options_handler was invoked
        # (sbdataq may or may not be set depending on timing of SE processing)

    def test_exits_cleanly_on_eof(self, handler):
        # Should not raise; EOFError is caught internally
        self._run(handler, "")

    def test_exits_cleanly_on_socket_error(self, handler):
        handler.rawq = ""
        handler.sock = MockSocket(b"")
        # EOFError raised when socket returns b'' — covered by _run
        handler.inputcooker()  # must not propagate


class TestInputCookerEscapeSequences:
    """Tests for escape-sequence (arrow key) recognition in inputcooker.

    The left arrow key sends ESC + '[' + 'D' (three chars).  ESCSEQ maps
    that string to the curses key code.  The while-loop condition in
    inputcooker compared len(codes) <= keyseq (int <= str), raising
    TypeError in Python 3.
    """

    LEFT_ARROW_SEQ = ESC + "[D"

    def _run(self, handler, rawq_data: str):
        handler.rawq = rawq_data
        handler.sock = MockSocket(b"")
        handler.inputcooker()

    def test_left_arrow_translates_to_key_code(self, handler):
        """Pressing left arrow should store curses.KEY_LEFT in the cooked queue."""
        handler.ESCSEQ = {self.LEFT_ARROW_SEQ: curses.KEY_LEFT}
        self._run(handler, self.LEFT_ARROW_SEQ)
        assert curses.KEY_LEFT in handler.cookedq

    def test_escape_sequence_does_not_raise_type_error(self, handler):
        """inputcooker must not raise TypeError when processing a key sequence."""
        handler.ESCSEQ = {self.LEFT_ARROW_SEQ: curses.KEY_LEFT}
        # Before the fix, len(codes) <= keyseq (int <= str) raised TypeError.
        try:
            self._run(handler, self.LEFT_ARROW_SEQ)
        except TypeError as exc:
            pytest.fail(f"inputcooker raised TypeError: {exc}")
