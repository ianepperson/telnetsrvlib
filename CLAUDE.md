# CLAUDE.md

See [AGENTS.md](AGENTS.md) for full project guidelines including setup, testing,
coverage requirements, TDD workflow, and code style.

## Quick Reference

- **Run tests:** `pytest`
- **Run with coverage:** `pytest --cov=telnetsrv --cov-report=term-missing`
- **Format:** `black telnetsrv/ tests/`
- **Lint:** `flake8 telnetsrv/ tests/`
- **Coverage requirement:** 90% or greater for all new code
- **Bug fix workflow:** write failing test first, then fix code
