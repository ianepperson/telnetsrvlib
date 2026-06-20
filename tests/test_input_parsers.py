from unittest import mock
from telnetsrv.telnetsrvlib import InputSimple, InputBashLike

# ---------------------------------------------------------------------------
# InputSimple
# ---------------------------------------------------------------------------


class TestInputSimple:
    def test_empty_string(self):
        inp = InputSimple(None, "")
        assert inp.cmd == ""
        assert inp.params == []

    def test_whitespace_only(self):
        inp = InputSimple(None, "   ")
        assert inp.cmd == ""
        assert inp.params == []

    def test_single_word_is_cmd(self):
        inp = InputSimple(None, "hello")
        assert inp.cmd == "hello"
        assert inp.params == []

    def test_multiple_words(self):
        inp = InputSimple(None, "foo bar baz")
        assert inp.cmd == "foo"
        assert inp.params == ["bar", "baz"]

    def test_double_quoted_param_preserves_spaces(self):
        inp = InputSimple(None, 'cmd "hello world"')
        assert inp.cmd == "cmd"
        assert inp.params == ["hello world"]

    def test_single_quoted_param_preserves_spaces(self):
        inp = InputSimple(None, "cmd 'hello world'")
        assert inp.cmd == "cmd"
        assert inp.params == ["hello world"]

    def test_extra_spaces_collapse(self):
        inp = InputSimple(None, "  foo   bar  ")
        assert inp.cmd == "foo"
        assert inp.params == ["bar"]

    def test_raw_is_stripped_line(self):
        inp = InputSimple(None, "  hello world  ")
        assert inp.raw == "hello world"

    def test_params_are_parts_after_cmd(self):
        inp = InputSimple(None, "a b c d")
        assert inp.params == ["b", "c", "d"]


# ---------------------------------------------------------------------------
# InputBashLike
# ---------------------------------------------------------------------------


def _mock_handler(continuation: str = "") -> mock.MagicMock:
    """Handler mock whose readline() returns a completion line."""
    h = mock.MagicMock()
    h.CONTINUE_PROMPT = "... "
    h.readline.return_value = continuation
    return h


class TestInputBashLike:
    def test_empty_string(self):
        inp = InputBashLike(_mock_handler(), "")
        assert inp.cmd == ""
        assert inp.params == []

    def test_whitespace_only(self):
        inp = InputBashLike(_mock_handler(), "   ")
        assert inp.cmd == ""
        assert inp.params == []

    def test_single_word(self):
        inp = InputBashLike(_mock_handler(), "hello")
        assert inp.cmd == "hello"
        assert inp.params == []

    def test_multiple_words(self):
        inp = InputBashLike(_mock_handler(), "foo bar baz")
        assert inp.cmd == "foo"
        assert inp.params == ["bar", "baz"]

    def test_double_quoted_preserves_spaces(self):
        inp = InputBashLike(_mock_handler(), 'cmd "hello world"')
        assert inp.cmd == "cmd"
        assert inp.params == ["hello world"]

    def test_single_quoted_preserves_spaces(self):
        inp = InputBashLike(_mock_handler(), "cmd 'hello world'")
        assert inp.cmd == "cmd"
        assert inp.params == ["hello world"]

    def test_escaped_space_in_param(self):
        inp = InputBashLike(_mock_handler(), r"echo hello\ world")
        assert inp.cmd == "echo"
        assert inp.params == ["hello world"]

    def test_escaped_newline_continues(self):
        # '\' at end of line triggers a readline call for more input
        h = _mock_handler(continuation="world")
        inp = InputBashLike(h, "echo hello \\")
        h.readline.assert_called_once()
        assert inp.cmd == "echo"

    def test_raw_contains_original_input(self):
        line = "hello world"
        inp = InputBashLike(_mock_handler(), line)
        assert line in inp.raw

    def test_complete_flag_set_on_finish(self):
        inp = InputBashLike(_mock_handler(), "done")
        assert inp.complete is True

    def test_params_empty_for_bare_command(self):
        inp = InputBashLike(_mock_handler(), "ls")
        assert inp.params == []

    def test_quoted_then_unquoted(self):
        inp = InputBashLike(_mock_handler(), '"hello world" foo')
        assert inp.cmd == "hello world"
        assert inp.params == ["foo"]

    def test_escape_tab(self):
        inp = InputBashLike(_mock_handler(), "echo a\\tb")
        assert inp.cmd == "echo"
        assert inp.params == ["a\tb"]

    def test_escape_n_sequence(self):
        # \n inside a quoted param → literal newline character in the result
        inp = InputBashLike(_mock_handler(), "echo a\\nb")
        assert inp.cmd == "echo"
        assert inp.params == ["a\nb"]
