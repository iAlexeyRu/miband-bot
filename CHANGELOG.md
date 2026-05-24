# Changelog

All notable changes to this project are documented here.

The format follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project is licensed under GNU GPL v3.0 or later.

## Unreleased

### Added

- Human-first Russian and English README files.
- Security, contributing, vendored dependency and authorship documentation.
- Example `secrets.env.example` for safe setup.
- Root GitHub Actions CI workflow for tests, linting, packaging checks and Docker build.

### Changed

- Root project metadata is now described in `pyproject.toml`.
- Ruff configuration covers a broader set of checks while allowing intentional Cyrillic UI text.

### Security

- Documented secret storage, token rotation and Telegram CSV export privacy expectations.
