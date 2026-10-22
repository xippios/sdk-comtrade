# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for UN Comtrade, empty task layer, MCP server and FastAPI router
  wired to it, test harness, CI and publishing.
- Upstream documentation snapshot in `docs/upstream/`: the five ApiDocs product specs
  (OpenAPI: Public, Comtrade, Comtrade Tools, Comtrade Bulk, Comtrade Async), ten Help
  Center articles as Markdown and two reference files, listed in `FETCHED.md`.
- `scripts/refresh_upstream.py`: regenerates the snapshot reproducibly, discovering the
  ApiDocs products from the page's bundle (`uv run scripts/refresh_upstream.py`).
