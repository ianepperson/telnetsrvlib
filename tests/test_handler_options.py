"""Tests for telnet options negotiation: sendcommand and options_handler."""

from unittest import mock

from telnetsrv.constants import (
    IAC,
    DO,
    DONT,
    WILL,
    WONT,
    NOP,
    SE,
    SB,
    TTYPE,
    IS,
    ECHO,
    SGA,
    NOOPT,
)


def recv(handler) -> str:
    return handler.sock.sent.decode("latin-1")


# ---------------------------------------------------------------------------
# sendcommand
# ---------------------------------------------------------------------------


class TestSendCommand:
    def test_do_sends_iac_do_opt(self, handler):
        handler.sendcommand(DO, ECHO)
        assert recv(handler) == IAC + DO + ECHO

    def test_dont_after_do_sends_dont(self, handler):
        handler.DOOPTS[ECHO] = True
        handler.sendcommand(DONT, ECHO)
        assert recv(handler) == IAC + DONT + ECHO

    def test_will_sends_iac_will_opt(self, handler):
        handler.sendcommand(WILL, SGA)
        assert recv(handler) == IAC + WILL + SGA

    def test_wont_after_will_sends_wont(self, handler):
        handler.WILLOPTS[SGA] = True
        handler.sendcommand(WONT, SGA)
        assert recv(handler) == IAC + WONT + SGA

    def test_bare_command_sends_iac_cmd(self, handler):
        handler.sendcommand(NOP)
        assert recv(handler) == IAC + NOP

    def test_do_deduplication_no_resend(self, handler):
        handler.sendcommand(DO, ECHO)
        handler.sock.sent = b""
        handler.sendcommand(DO, ECHO)
        assert handler.sock.sent == b""

    def test_dont_deduplication_no_resend(self, handler):
        handler.DOOPTS[ECHO] = False  # already sent DONT
        handler.sendcommand(DONT, ECHO)
        assert handler.sock.sent == b""

    def test_will_deduplication_no_resend(self, handler):
        handler.sendcommand(WILL, SGA)
        handler.sock.sent = b""
        handler.sendcommand(WILL, SGA)
        assert handler.sock.sent == b""

    def test_wont_deduplication_no_resend(self, handler):
        handler.WILLOPTS[SGA] = False  # already sent WONT
        handler.sendcommand(WONT, SGA)
        assert handler.sock.sent == b""

    def test_do_sets_doopts(self, handler):
        handler.sendcommand(DO, ECHO)
        assert handler.DOOPTS[ECHO] is True

    def test_dont_sets_doopts(self, handler):
        handler.DOOPTS[ECHO] = True
        handler.sendcommand(DONT, ECHO)
        assert handler.DOOPTS[ECHO] is False

    def test_will_sets_willopts(self, handler):
        handler.sendcommand(WILL, SGA)
        assert handler.WILLOPTS[SGA] is True

    def test_wont_sets_willopts(self, handler):
        handler.WILLOPTS[SGA] = True
        handler.sendcommand(WONT, SGA)
        assert handler.WILLOPTS[SGA] is False


# ---------------------------------------------------------------------------
# options_handler
# ---------------------------------------------------------------------------


class TestOptionsHandler:
    def test_nop_echoes_nop(self, handler):
        handler.options_handler(handler.sock, NOP, NOOPT)
        assert recv(handler) == IAC + NOP

    def test_will_known_option_gets_response(self, handler):
        handler.options_handler(handler.sock, WILL, SGA)
        # SGA is in WILLACK → respond with DO
        assert IAC in recv(handler)

    def test_will_unknown_option_sends_dont(self, handler):
        unknown = chr(99)
        handler.options_handler(handler.sock, WILL, unknown)
        assert recv(handler) == IAC + DONT + unknown

    def test_wont_unknown_option_sends_dont(self, handler):
        unknown = chr(98)
        handler.options_handler(handler.sock, WONT, unknown)
        assert recv(handler) == IAC + DONT + unknown

    def test_do_known_option_gets_response(self, handler):
        handler.options_handler(handler.sock, DO, ECHO)
        assert IAC in recv(handler)

    def test_do_unknown_option_sends_wont(self, handler):
        unknown = chr(99)
        handler.options_handler(handler.sock, DO, unknown)
        assert recv(handler) == IAC + WONT + unknown

    def test_dont_unknown_option_sends_wont(self, handler):
        unknown = chr(98)
        handler.options_handler(handler.sock, DONT, unknown)
        assert recv(handler) == IAC + WONT + unknown

    def test_do_echo_sets_doecho_true(self, handler):
        handler.DOECHO = False
        handler.options_handler(handler.sock, DO, ECHO)
        assert handler.DOECHO is True

    def test_dont_echo_sets_doecho_false(self, handler):
        handler.DOECHO = True
        handler.options_handler(handler.sock, DONT, ECHO)
        assert handler.DOECHO is False

    def test_will_ttype_sends_subnegotiation_request(self, handler):
        handler.options_handler(handler.sock, WILL, TTYPE)
        # Should send IAC SB TTYPE SEND IAC SE
        sent_bytes = handler.sock.sent
        assert b"\xff" in sent_bytes  # IAC present

    def test_se_with_ttype_calls_setterm(self, handler):
        handler.sbdataq = TTYPE + IS + "ansi"
        with mock.patch.object(handler, "setterm") as mock_setterm:
            handler.options_handler(handler.sock, SE, NOOPT)
        mock_setterm.assert_called_once_with("ansi")

    def test_se_with_bad_ttype_silently_ignored(self, handler):
        handler.sbdataq = TTYPE + IS + "not-a-real-terminal-xyz"
        # Should not raise; bad terminals are caught internally
        handler.options_handler(handler.sock, SE, NOOPT)

    def test_sb_is_a_noop(self, handler):
        handler.options_handler(handler.sock, SB, NOOPT)
        assert handler.sock.sent == b""

    def test_unknown_command_logged_not_raised(self, handler):
        # Should not raise; unrecognised commands are just logged
        handler.options_handler(handler.sock, chr(200), chr(201))


# ---------------------------------------------------------------------------
# read_sb_data
# ---------------------------------------------------------------------------


class TestReadSbData:
    def test_returns_and_clears_queue(self, handler):
        handler.sbdataq = "somedata"
        assert handler.read_sb_data() == "somedata"
        assert handler.sbdataq == ""

    def test_empty_queue(self, handler):
        handler.sbdataq = ""
        assert handler.read_sb_data() == ""

    def test_subsequent_call_is_empty(self, handler):
        handler.sbdataq = "x"
        handler.read_sb_data()
        assert handler.read_sb_data() == ""
