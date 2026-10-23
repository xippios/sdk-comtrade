# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- `list_reporters` and `list_partners`, MCP tools `comtrade_list_reporters` and
  `comtrade_list_partners`: UN Comtrade's `Reporters.json` (255 rows) and
  `partnerAreas.json` (310 rows) as packaged with this version, every column under its
  upstream name, without an upstream call; `meta.vintage` is the day they were fetched.
- `list_commodities(cl_code)`, MCP tool `comtrade_list_commodities`: the product codes of
  one classification from upstream's public `<clCode>.json` (no key, no quota), kept for
  the process by core's GET cache on `reference_client` (`REFERENCE_CACHE`). `cl_code` is
  checked against the 19 classifications with a file; `BE` and `TM` have none (HTTP 404).
- Packaged tables `Reporters.csv`, `partnerAreas.csv`, `country_area_code_iso.csv` (UN
  Comtrade's code to ISO alpha-3) and `TradeDataItems.csv`, written by
  `scripts/refresh_reference.py` with upstream's columns, their provenance in
  `reference/tables.json`; packaged lists `mosCode` (`ModeOfSupply.json`) and
  `qtyUnitCode` (`QuantityUnits.json`) with the StrEnums `MosCode` and `QtyUnitCode`.
- `api.reference_rows`: a reference file's rows as upstream sent them.
- Replay tests check the request that goes out carries the placeholder key, never the
  shell's (ported from sdk-template).

### Changed

- `reporter_code` is checked against the packaged `Reporters.json`, `partner_code` and
  `partner2_code` against `partnerAreas.json`, each member of a comma-separated list. An
  unknown code raises `InvalidRequestError` before any call, naming the same area's code
  where `country_area_code_iso.json` knows it (`756` names `757`, Switzerland), or saying
  that a code belongs to the other table (`0` World is a partner only). Upstream itself
  answers a code that is no reporter with an empty result.

- `get_counts` and `get_data` on `data/v1/get/{typeCode}/{freqCode}/{clCode}`, MCP tools
  `comtrade_get_counts` and `comtrade_get_data`. `get_data` counts first with
  `countOnly`: zero returns an empty result without a second call, more than 100,000
  records raises `QueryTooLarge` (an `InvalidRequestError`, HTTP 422) before any data
  call, because upstream truncates silently at 100,000 rows (observed 2026-10-23).
  Rows are `TradeDataRecord`, every field of upstream's schema, values and quantities as
  `Decimal`.
- Arguments are checked before any call (`params.validate_get`): coded parameters against
  packaged lists, periods (at most 12) and product codes by shape.
- Packaged lists `typeCode`, `freqCode`, `clCode`, `flowCode`, `customsCode`, `motCode`,
  `aggregateBy`, `breakdownMode` in `reference/` with their origin, and the matching
  StrEnums in `enums.py`, written by `scripts/refresh_reference.py` from the public
  reference files (fetched without a key through `api.reference`) and the spec snapshot.
  Where the spec documents more than a reference file, the script reconciles them and
  records each exception with its evidence: `flowCode` adds the spec's `MIF` and `XIF`;
  `clCode` adds the spec's `BE` and `TM`, which upstream accepted, and leaves out `BE5`,
  which upstream refused.
- `_client.classify`: an HTTP 400 `ErrorResponse` becomes `InvalidRequestError` with
  upstream's message; a 403 that mentions a quota becomes `RateLimitError` (API
  Management's text, not observed). The rate limit no longer bursts:
  `RateLimit(per_minute=60, burst=1)`, one call per second as documented. The read
  timeout is 180 s, since a broad count can take over a minute.
- Fifteen recorded fixtures under `tests/fixtures/get/` and live smoke tests for both
  tasks. Replay tests always send a placeholder key, whatever the shell holds.
- Scaffold from [sdk-template](https://github.com/xippios/sdk-template): configured
  client for UN Comtrade, empty task layer, MCP server and FastAPI router
  wired to it, test harness, CI and publishing.
- Upstream documentation snapshot in `docs/upstream/`: the five ApiDocs product specs
  (OpenAPI: Public, Comtrade, Comtrade Tools, Comtrade Bulk, Comtrade Async), ten Help
  Center articles as Markdown and two reference files, listed in `FETCHED.md`.
  `.gitattributes` marks `docs/upstream/**` as `-text`, so git never converts the line
  endings of the files kept byte for byte (the CRLF specs, one mixed-endings file).
- `scripts/refresh_upstream.py`: regenerates the snapshot reproducibly, discovering the
  ApiDocs products from the page's bundle (`uv run scripts/refresh_upstream.py`).
