"""Tests for TelnetHandlerBase write/output methods."""

from telnetsrv.constants import IAC


def sent(handler) -> str:
    """Decode what the mock socket received, as latin-1 str."""
    return handler.sock.sent.decode("latin-1")


class TestWriteCooked:
    def test_sends_raw_bytes_to_socket(self, handler):
        handler.writecooked("hello")
        assert handler.sock.sent == b"hello"

    def test_encodes_latin1_high_bytes(self, handler):
        handler.writecooked(chr(0xFF))
        assert handler.sock.sent == b"\xff"

    def test_encodes_null_byte(self, handler):
        handler.writecooked(chr(0))
        assert handler.sock.sent == b"\x00"


class TestWrite:
    def test_plain_text_passthrough(self, handler):
        handler.write("hello")
        assert handler.sock.sent == b"hello"

    def test_newline_expands_to_crlf(self, handler):
        handler.write("line\n")
        assert handler.sock.sent == b"line\r\n"

    def test_multiple_newlines_each_expanded(self, handler):
        handler.write("a\nb\n")
        assert handler.sock.sent == b"a\r\nb\r\n"

    def test_iac_byte_is_doubled(self, handler):
        handler.write(IAC)
        assert handler.sock.sent == b"\xff\xff"

    def test_iac_inside_text(self, handler):
        handler.write("a" + IAC + "b")
        assert handler.sock.sent == b"a\xff\xffb"

    def test_non_string_coerced_to_str(self, handler):
        handler.write(42)
        assert handler.sock.sent == b"42"

    def test_empty_string(self, handler):
        handler.write("")
        assert handler.sock.sent == b""


class TestWriteline:
    def test_appends_crlf(self, handler):
        handler.writeline("hello")
        assert handler.sock.sent == b"hello\r\n"

    def test_empty_string(self, handler):
        handler.writeline("")
        assert handler.sock.sent == b"\r\n"


class TestWriteresponse:
    def test_delegates_to_writeline(self, handler):
        handler.writeresponse("response text")
        assert b"response text" in handler.sock.sent
        assert handler.sock.sent.endswith(b"\r\n")


class TestWriteerror:
    def test_delegates_to_writeline(self, handler):
        handler.writeerror("error text")
        assert b"error text" in handler.sock.sent
        assert handler.sock.sent.endswith(b"\r\n")


class TestWritemessage:
    def test_message_appears_in_output(self, handler):
        handler._current_prompt = ""
        handler._current_line = []
        handler.writemessage("async message")
        assert b"async message" in handler.sock.sent

    def test_prompt_is_reconstructed(self, handler):
        handler._current_prompt = "PROMPT> "
        handler._current_line = list("partial")
        handler.writemessage("msg")
        output = sent(handler)
        assert "PROMPT> " in output
        assert "partial" in output

    def test_output_has_surrounding_newlines(self, handler):
        handler._current_prompt = ""
        handler._current_line = []
        handler.writemessage("hello")
        # writemessage writes \nhello\n then the prompt
        output = sent(handler)
        assert "hello" in output
        assert "\r\n" in output
