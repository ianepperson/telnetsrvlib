# CLAUDE.md

See [AGENTS.md](AGENTS.md) for full project guidelines including setup, testing,
coverage requirements, TDD workflow, and code style.

## Quick Reference

- **Run tests:** `uv run pytest`
- **Run with coverage:** `uv run pytest --cov=telnetsrv --cov-report=term-missing`
- **Format:** `uv run black telnetsrv/ tests/`
- **Lint:** `uv run flake8 telnetsrv/ tests/`
- **Coverage requirement:** 90% or greater for all new code
- **Bug fix workflow:** write failing test first, then fix code
