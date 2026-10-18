# Contributing

Thanks for your interest in LayerHop!

## Where the code lives

This repository is **exported automatically** from the LayerHop monorepo
(`sdks/python`), which is the single source of truth. Every sync commit is titled
`Sync from layerhop monorepo <sha>` and references the monorepo commit it was built from.

**Pull requests are welcome here.** A maintainer reviews your PR, applies the change upstream in the
monorepo, and the next sync brings it back into this repository with you credited in the PR. Because
of that, your PR may be closed rather than merged directly; that is expected and does not mean it was
rejected.

Issues are welcome too. For security problems, follow [SECURITY.md](SECURITY.md) instead.

## Development

See [README.md](README.md) for setup. CI (`.github/workflows/ci.yml`) runs the same checks you
should run locally before opening a PR.

## Releases

Bump `version` in `pyproject.toml`, then push a `vX.Y.Z` tag. `.github/workflows/release.yml` builds the sdist and wheel and publishes them to PyPI with the `PYPI_API_TOKEN` repository secret (or trusted publishing when no token is set); versions already on PyPI are skipped. Local dev: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && pytest`.
