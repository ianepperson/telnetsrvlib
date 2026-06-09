"""Tests for setterm: curses terminal capability setup."""


class TestSetterm:
    def test_sets_term_attribute(self, handler):
        handler.setterm("ansi")
        assert handler.TERM == "ansi"

    def test_codes_are_all_strings(self, handler):
        handler.setterm("ansi")
        for key, val in handler.CODES.items():
            assert isinstance(
                val, str
            ), f"CODES[{key!r}] is {type(val).__name__}, expected str"

    def test_escseq_keys_are_strings(self, handler):
        handler.setterm("ansi")
        for key in handler.ESCSEQ:
            assert isinstance(
                key, str
            ), f"ESCSEQ key {key!r} is {type(key).__name__}, expected str"

    def test_escseq_values_are_ints(self, handler):
        handler.setterm("ansi")
        for val in handler.ESCSEQ.values():
            assert isinstance(
                val, int
            ), f"ESCSEQ value {val!r} should be int (curses key code)"

    def test_creates_copy_of_codes(self, handler):
        from telnetsrv.telnetsrvlib import TelnetHandlerBase

        handler.setterm("ansi")
        # Modifying the instance's CODES should not affect the class-level dict
        handler.CODES["DEOL"] = "MODIFIED"
        assert TelnetHandlerBase.CODES["DEOL"] == ""

    def test_invalid_terminal_raises_on_first_call(self):
        # curses.setupterm raises on the very first call with a bad name,
        # but silently reuses a cached terminal on subsequent calls.
        # Test in isolation via subprocess.
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                'import curses; curses.setupterm("not-a-real-terminal-xyz")',
            ],
            capture_output=True,
        )
        assert result.returncode != 0

    def test_vt100_terminal(self, handler):
        handler.setterm("vt100")
        assert handler.TERM == "vt100"

    def test_xterm_terminal(self, handler):
        handler.setterm("xterm")
        assert handler.TERM == "xterm"
        # xterm should provide navigation key sequences
        assert len(handler.ESCSEQ) > 0
