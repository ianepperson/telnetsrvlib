# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.2] - 2026-06-21

### Added
- Asyncio example server and tests demonstrating `telnetsrv.aio` usage.

### Security
- SSH server now logs a warning when `none` authentication is permitted, alerting developers to the insecure configuration.

## [1.0.0] - 2026-06-20

This is a major release that drops Python 2 support and modernises the library for Python 3.

### Breaking Changes
- **Python 2 dropped.** Python 3.9 or later is required.
- **Commands must be defined in a `Commands` subclass.** Previously, `do_*` methods were defined directly on the handler class, which caused name collisions with internal handler methods. Commands are now defined on a separate class that inherits from `telnetsrv.base.BaseCommands` (or the async equivalent), and that class is passed as `COMMANDS` on the handler. See the README for the updated pattern.

### Added
- `asyncio`/`await` handler classes in `telnetsrv.aio` (`TelnetHandler`) and `telnetsrv.aio_ssh` (`SSHTelnetHandler`) for non-blocking async servers.
- `_command_not_found` hook — override to customise the response when an unrecognised command is entered; may be a coroutine in async handlers.
- `telnetsrv.constants` module containing telnet protocol constants previously scattered through the code.
- `__all__` exports in all public modules.
- GitHub Actions CI running the full test suite on Python 3.9–3.14.
- Black and flake8 lint checks in CI.
- 90 % test-coverage requirement enforced in CI.

### Changed
- Modernised tooling: project managed with `uv`, code formatted with `black`.
- `paramiko` updated to 5.x; SSH key handling updated accordingly.
- Python 3.13 and 3.14 added to the CI test matrix.

### Fixed
- Abrupt client disconnect no longer leaves the handler thread spinning indefinitely (issue #16).
- NAWS (Negotiate About Window Size) negotiation restored; `self.WIDTH` and `self.HEIGHT` are now correctly populated on connect (issues #7 and #11).
- `TypeError` when processing escape key sequences in `inputcooker`.
- Three bugs in `SSHHandler` that broke the threaded SSH server with paramiko 5.x.

## [0.4] - 2012-12-01

### Added
- SSH server handler via `paramiko`, exposing the same `TelnetHandler` interface over SSH.
- Authentication callbacks mirroring the Telnet handler pattern.
- Terminal information (`TERM`, window size) passed through from the SSH session.
- Configurable login banner, username prompt, and password prompt.
- NAWS support: terminal width and height available as `self.WIDTH` and `self.HEIGHT`.
- Eventlet support for green-thread-based servers.

### Fixed
- Exception handling when a client disconnects mid-session.
- Timer command cleanup on session end.

## [0.3.1] - 2012

### Changed
- README converted from Markdown to reStructuredText.
- License text added to distribution.

## [0.3] - 2012

### Added
- Initial public release on GitHub.
- Telnet server base classes with full line-editing support (backspace, cursor movement, history).
- Command dispatch via `do_*` method naming convention on the handler class.
- Function-decorator syntax (`@command`) for registering commands.
- Built-in `help` command that introspects docstrings.
- Command history navigation (up/down arrow keys).
- Optional command hiding (commands prefixed with `_` are not listed in `help`).
- Readline-style prompt with `writeline` and `readline` helpers.
- Session start/end hooks.
- Timer-based background commands.
- Null logging by default; caller supplies a logger.

## Pre-0.3 — SourceForge origin

Versions prior to 0.3 were developed and released on SourceForge as
`pytelnetsrvlib` (http://pytelnetsrvlib.sourceforge.net/). This project
is a fork of that codebase, licensed under the LGPL as per the original
SourceForge release.


[1.0.2]: https://github.com/ianepperson/telnetsrvlib/compare/v1.0...v1.0.2
[1.0.0]: https://github.com/ianepperson/telnetsrvlib/compare/v0.4...v1.0
[0.4]: https://github.com/ianepperson/telnetsrvlib/compare/v0.3.1...v0.4
[0.3.1]: https://github.com/ianepperson/telnetsrvlib/compare/v0.3...v0.3.1
[0.3]: https://github.com/ianepperson/telnetsrvlib/releases/tag/v0.3
