# AGENTS.md

Guidelines for AI agents (and human contributors) working in this repository.

## Project Overview

`telnetsrv` is a Python library for building Telnet and SSH servers. It provides
multiple handler flavors: threaded (`telnetsrv/threaded.py`), green/gevent
(`telnetsrv/green.py`), eventlet (`telnetsrv/evtlet.py`), and async/asyncio
(`telnetsrv/aio.py`). SSH wrappers live in `telnetsrv/paramiko_ssh.py` and
`telnetsrv/aio_ssh.py`. The base handler logic is in `telnetsrv/telnetsrvlib.py`.

Requires Python 3.9+.

## Documentation

`README.md` is the authoritative reference for library usage: handler flavors,
command definition patterns, SSH setup, serving examples, and all public API.

**Read `README.md` before making changes** to understand existing usage patterns.

**Update `README.md` whenever:**
- Public API is added, changed, or removed
- A new usage pattern is introduced or an existing one changes
- New handler flavors or options are added
- Default behavior changes

Treat `README.md` as part of the changeset — a feature or fix is not complete
until the docs reflect it.

## Environment Setup

```bash
uv sync --extra ssh --extra dev
```

The `dev` extras install pytest, pytest-asyncio, pytest-cov, black, and flake8.

## Running Tests

```bash
uv run pytest
```

Run with coverage:

```bash
uv run pytest --cov=telnetsrv --cov-report=term-missing
```

Tests live in `tests/` and `example-test.py`. Pytest config is in `pyproject.toml`
under `[tool.pytest.ini_options]`. Async tests use `asyncio_mode = "auto"`.

Coverage excludes the green/eventlet/paramiko wrappers (`green.py`, `evtlet.py`,
`paramiko_ssh.py`) because they require optional runtime dependencies. Coverage is
measured on the remaining source; see `[tool.coverage.run]` in `pyproject.toml`.

## Coverage Requirement

**All new code must have 90% or greater test coverage.** Verify before submitting:

```bash
pytest --cov=telnetsrv --cov-report=term-missing
```

Check the "TOTAL" line. Coverage below 90% is a blocking issue.

## Bug Fixes: Test-Driven Development

Fix bugs in TDD style:

1. **Write a failing test** that reproduces the bug. Run pytest to confirm it fails.
2. **Fix the code** so the test passes.
3. **Run the full suite** to confirm no regressions.

Do not commit a code fix without a corresponding test that was failing before the fix.

## Code Style

Format with black (line length 88):

```bash
black telnetsrv/ tests/
```

Lint with flake8:

```bash
flake8 telnetsrv/ tests/
```

Flake8 config in `.flake8`: ignores E203 and W503 (both conflict with black).

## Test Fixtures

`tests/conftest.py` provides shared fixtures:

- `MockSocket` — fake socket that records sent bytes and returns pre-loaded recv data
- `ConcreteHandler` — minimal concrete `TelnetHandlerBase` for unit testing
- `make_handler(handler_class=None)` — creates a handler bypassing the server lifecycle
- `handler` fixture — pytest fixture returning a `ConcreteHandler` via `make_handler()`

Use these instead of spinning up real sockets or servers for unit tests. For
integration-style tests, see `tests/test_aio.py` and `tests/test_threaded.py` as
examples of testing full handler flows.

## CI

GitHub Actions runs the test suite on Python 3.9, 3.10, 3.11, and 3.12 on every
pull request and push to master. See `.github/workflows/ci.yml`. CI does not run
coverage checks; that is a local/PR responsibility.

## Docstrings

Every public method and every test function must have a docstring.

- **Public methods:** one-line summary minimum; add detail when behavior is non-obvious.
- **Test functions:** describe what is being tested and what outcome is expected.

```python
def test_writeline_appends_crlf(handler):
    """writeline appends CRLF to the output sent to the socket."""
    ...

def writeresponse(self, text):
    """Write a line of expected command output to the client."""
    ...
```

Private methods (prefixed with `_`) and `__dunder__` methods are exempt, but a
docstring is still welcome when the logic is non-obvious.

## Key Patterns

- Commands are defined as methods on a `Commands` subclass, decorated with `@cmd`.
- The handler and commands are separate classes; commands reach the handler via
  `self.handler`.
- In the async handler (`aio.py`), command methods and lifecycle hooks
  (`session_start`, `session_end`, `_command_not_found`) may be coroutines; the
  handler detects and awaits them automatically.
- Write methods (`writeresponse`, `writeerror`, `writemessage`, `writeline`, `write`)
  are synchronous in all flavors — do not await them.
