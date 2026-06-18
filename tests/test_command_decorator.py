from telnetsrv.telnetsrvlib import cmd


class TestCommandDecorator:
    def test_single_string_name(self):
        @cmd("myname")
        def fn(params):
            pass

        assert fn.command_name == "myname"
        assert fn.aliases == []
        assert fn.hidden is False

    def test_list_of_names_first_is_primary(self):
        @cmd(["primary", "alias1", "alias2"])
        def fn(params):
            pass

        assert fn.command_name == "primary"
        assert fn.aliases == ["alias1", "alias2"]

    def test_single_item_list(self):
        @cmd(["only"])
        def fn(params):
            pass

        assert fn.command_name == "only"
        assert fn.aliases == []

    def test_hidden_false_is_default(self):
        @cmd("x")
        def fn(params):
            pass

        assert fn.hidden is False

    def test_hidden_true(self):
        @cmd("x", hidden=True)
        def fn(params):
            pass

        assert fn.hidden is True

    def test_returns_same_callable(self):
        def fn(params):
            pass

        result = cmd("x")(fn)
        assert result is fn

    def test_stacked_outermost_is_primary(self):
        @cmd("outer")
        @cmd(["inner", "inneralias"])
        def fn(params):
            pass

        assert fn.command_name == "outer"
        assert "inner" in fn.aliases
        assert "inneralias" in fn.aliases

    def test_stacked_three_deep(self):
        @cmd("top")
        @cmd("middle")
        @cmd("bottom")
        def fn(params):
            pass

        assert fn.command_name == "top"
        assert "middle" in fn.aliases
        assert "bottom" in fn.aliases

    def test_stacked_all_aliases_collected(self):
        @cmd(["a", "b"])
        @cmd(["c", "d"])
        def fn(params):
            pass

        # 'a' is primary, 'b', 'c', 'd' all aliases
        assert fn.command_name == "a"
        assert set(fn.aliases) == {"b", "c", "d"}

    def test_hidden_on_outer_propagates(self):
        @cmd("top", hidden=True)
        @cmd("bottom")
        def fn(params):
            pass

        assert fn.hidden is True

    def test_hidden_on_inner_propagates(self):
        @cmd("top")
        @cmd("bottom", hidden=True)
        def fn(params):
            pass

        assert fn.hidden is True

    def test_function_still_callable(self):
        results = []

        @cmd("test")
        def fn(params):
            results.append(params)

        fn(["a", "b"])
        assert results == [["a", "b"]]
