# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

Adopted xippios-core 0.3.0, sdk-template v0.3.0 and conventions 1.22 (conventions §15).

### Added

- Two tasks on UN Comtrade's Tools operations, which the spec marks "EXPERIMENTAL - USE
  SPARINGLY", MCP tools `comtrade_get_trade_balance` and `comtrade_get_bilateral_data`:
  `get_trade_balance(type_code, freq_code, cl_code, *, reporter_code=, period=,
  partner_code=, partner2_code=, cmd_code=, customs_code=, mot_code=, aggregate_by=,
  breakdown_mode=, include_desc=)` on `tools/v1/getTradeBalance`, a reporter's exports
  and imports side by side (`TradeBalanceRecord`, `primary_value_bal` as upstream sends
  it), and `get_bilateral_data(type_code, freq_code, cl_code, *, reporter_code=, period=,
  partner_code=, cmd_code=, flow_code=, include_desc=)` on `tools/v1/getBilateralData`,
  its figures beside its partners' mirror figures (`BilateralDataRecord`), returned as
  one `BilateralData`, not a list: upstream's data-gap `note`, which qualifies the mirror
  values, `timestamp_requested` (UTC) and the rows as `data`; wrappers
  `api.get_trade_balance` and `api.get_bilateral_data`, `meta.total` upstream's `count`.
  Both need `reporter_code` or `partner_code`, and `cmd_code`, checked before the call
  with the other arguments (`params.validate_trade_balance`,
  `params.validate_bilateral_data`).
- What the recorded answers of 2026-10-28 established, under
  `tests/fixtures/get_trade_balance/` and `get_bilateral_data/`:
  - both operations answered the package's key; getTradeBalance's allow-list refusal
    (403 "User not allowed" in the spec) did not occur;
  - `countOnly` counts nothing: getTradeBalance answers `count` 0 with a placeholder for a
    query of 48 rows, getBilateralData ignores it;
  - getTradeBalance without `breakdownMode` answers every breakdown (48 rows), with
    `classic` the total row alone;
  - getTradeBalance refuses a 13th period with HTTP 400, getBilateralData answers 13;
  - getBilateralData takes one `flowCode` (`M,X` gets HTTP 400) and fills no description
    with `includeDesc`;
  - getBilateralData answers in classic mode; its `note` counts the partners with a data
    gap without naming them, and Afghanistan, inferred from the counts to be one of them,
    has a mirror of 0; its `primaryValueDisc` equals (mirror − value) / value in every
    recorded row, a meaning upstream does not state;
  - getBilateralData's HTTP 400 spells a detail's message `ErrorMessage`, which
    `classify` now reads as well as `errorMessage`, so the refusal names the field
    (getTradeBalance's 400 had `details` null).
- The upstream snapshot refreshed on 2026-10-28 (`docs/upstream/`), with eight more Help
  Center articles: `un-comtrade-tools` (the Trade Balance and Bilateral Data tools),
  `developer-tools`, `un-comtrade-data-pipeline` (releases and revisions),
  `bilateral-asymmetries`,
  `how-to-retrieve-data-for-world-exports-to-a-country-in-un-comtrade`,
  `how-should-i-interpret-and-use-quantity-data-in-un-comtrade`, and the two that state
  the data's terms, `policy-on-comtrade-data-use` and `read-me-first-disclaimer`. The
  five ApiDocs product files, the ten earlier articles and the two reference files are
  unchanged.
- `uv run scripts/refresh_upstream.py --check` fetches everything and compares it with
  the snapshot, writing nothing; exit 1 names the files that differ.

### Changed

- **BREAKING**: depends on `xippios-core~=0.3.0` and its `mcp`, `http` and `testing`
  extras likewise, from `>=0.1.0`.
- `list_reporters` and `list_partners`: `meta.retrieved_at` is when the package fetched
  the list (2026-10-23) and `meta.vintage` is `None`, where `vintage` carried the fetch
  date; `list_commodities`' `meta.retrieved_at` is when its file was fetched, the first
  fetch of the process on a later call.
- One client: `reference_client` and `REFERENCE_CACHE` are gone from `_client`; the
  reference files go through `client` with `auth=None`, its cache kept to those files.
  `api.reference` and `api.reference_rows` return a `ReferenceFile` of the rows and
  their `retrieved_at`.
- The daily quota: `_client.policy`, a `QuotaPolicy`, reads upstream's 403 "Quota will
  be replenished in HH:MM:SS" and refuses the next call with `RateLimitError` before it
  is sent, until then; after a 429 it holds calls back for its `Retry-After` or the
  seconds its body names, never for a day.
- MCP: `list_reporters` and `list_partners` have a result cap of their own, 400 rows or
  100 KB, and reach an agent whole; `list_commodities` the same, its note saying to
  search (`MCP_CAPS`).
- The packaged files are `reference/<name>.json` packaged lists, `{"param",
  "endpoint", "fetched", "records"}` and an optional `"note"`, the four tables included
  (the CSV files and `tables.json` are gone); `params.packaged_values`, `packaged_table`,
  `packaged_table_info`, `PackagedValues`, `PackagedTable` and `ListException` give way
  to `xippios.core.PackagedList.load("xippios.comtrade", name)`, and
  `params.CL_CODES_FROM_SPEC` names the `clCode` values without a classification file.
- An unknown reporter, partner or second-partner code (the slices' `reporter` and
  `partner` also as an ISO alpha-3 code), `customs_code` or `mot_code` raises
  `UnknownCode`, an `InvalidRequestError`, naming the packaged list (`Reporters`,
  `partnerAreas`, `customsCode`, `motCode`), its fetch date and the closest code
  (conventions §5); the first unknown code ends the checks. The other lists are refused
  as before.
- `docs/upstream/FETCHED.md` takes the form of conventions §3: `Fetched` is the UTC time
  of the run with `Z`; an Attribution section quotes the Help Center's footer line,
  `© 2026 UN Comtrade Help Center`, read from https://uncomtrade.org/, and the data's
  copyright and licence-agreement lines as the Policy on Comtrade Data Use and Read Me
  First (Disclaimer) print them; each row records the HTTP status, size, sha256, ETag and
  Last-Modified (none of the four for a body that changes on every request, as four
  articles' do) and a note. The capture script stops before writing when a page states a
  copyright line, licence or terms of use it does not record.
- README: the terms section names upstream's Policy on Comtrade Data Use and the
  license agreement it makes the use of the data subject to, and points at
  `docs/upstream/FETCHED.md` for the attribution.

## [0.1.0] - 2026-10-23

### Added

- Four task-shaped slices on `data/v1/get`, MCP tools `comtrade_get_bilateral_flows`,
  `comtrade_get_commodity_series`, `comtrade_get_world_trade` and
  `comtrade_get_top_partners`: `get_bilateral_flows(reporter, partner, commodities,
  periods, flow)`, `get_commodity_series(reporter, commodity, flow, periods)` (partner
  World, 12 periods per call, at most 120 periods, rows by period),
  `get_world_trade(commodity, period, flow)` (every reporter, partner World, largest
  first) and `get_top_partners(reporter, commodity, period, flow, n)` (every partner
  ranked by `primary_value`, World dropped as the total, `n` in `meta.request`), each
  with `cl_code="HS"` (EB*, BE and TM accepted but untested with `typeCode` C). Every
  call pins `typeCode` C, `breakdownMode` classic, `partner2Code` 0, `motCode` 0,
  `customsCode` C00 and `includeDesc` true (`params.SLICE_PINS`); rows are
  `TradeFlowRecord`, a projection of `TradeDataRecord` under upstream names with the
  `is_qty_estimated` and `is_net_wgt_estimated` flags. At TOTAL and chapter level the
  recorded rows are mostly UNSD aggregates (`is_aggregate` true, `is_reported` false)
  without a quantity. The slices are bounded by their arguments and make no count call;
  a bound over 100,000 raises `QueryTooLarge` before the call (`bound=True`, kept on the
  exception).
- `params.validate_slice`: a reporter or partner as UN Comtrade's code or ISO alpha-3
  (`"CHE"` is 757, `"USA"` as partner 842, `"W00"` World), resolved before the call;
  periods of one format set `freqCode` (`YYYY` annual, `YYYYMM` monthly); a mix, an
  unknown code, a level such as `AG2`, a wildcard or a period or product code named twice
  is refused with the closest value.
- `search` on `list_reporters`, `list_partners` and `list_commodities`: a case-insensitive
  substring of the code, the ISO alpha-3 code (reporters, partners) or the text; it goes
  into `meta.request`. The MCP result cap (200 rows or 64 KB) hides most of each list, so
  the docstrings tell agents to search.
- Six recorded fixtures under `tests/fixtures/get/` for the slices (bilateral annual and
  monthly, the two calls of a 14-year series, world trade, every partner) and four live
  smoke tests, one keyed call each.
- `get_data_availability` on `data/v1/getDa`, `get_metadata` on `data/v1/getMetadata` and
  `get_live_update` on `data/v1/getLiveUpdate`, MCP tools `comtrade_get_data_availability`,
  `comtrade_get_metadata` and `comtrade_get_live_update`. Rows mirror the spec's schemas
  under upstream names and carry their own dates (`first_released`/`last_released`,
  `publication_date`, `started_at`/`completed_at`/`last_updated`/`queued_at`), typed;
  `meta.published_at` stays `None`. `get_metadata` takes `reporter_code` and `period`,
  which the spec omits and upstream honours. getLiveUpdate has no `publishedDate`; its
  times are read without the process locale, and one that does not parse becomes `None`
  for that field (only Released/Success rows were recorded).
- Every `clCode` value and `flowCode`'s `XIF` rest on a recorded count
  (`reference/clCode.json`, `flowCode.json`); `H6` answered HTTP 500 to all five tries.
  The docstrings of `get_counts` and `get_data` say what the recorded answers established
  for `breakdownMode` (default `plus`), `aggregateBy`, `includeDesc` and services totals.
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
- `scripts/refresh_reference.py --help` prints usage and fetches nothing. A list can carry
  a `note`: `mosCode.json` and `MosCode` say they hold `ModeOfSupply.json`'s ids, not
  proven parameter values (`data/v1/get` refused `Mode 1`).
- Replay tests check the request that goes out carries the placeholder key, never the
  shell's (ported from sdk-template).
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
  Management's text, not observed). The rate limit never bursts. The read
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

### Changed

- Calls are spaced 1.5 s apart (`RATE_LIMIT = RateLimit(per_minute=40, burst=1)`): at
  exactly 1.0 s, 9 of 18 calls drew HTTP 429 "Rate limit is exceeded" (2026-10-23).
- `reporter_code` is checked against the packaged `Reporters.csv`, `partner_code` and
  `partner2_code` against `partnerAreas.csv`, each member of a comma-separated list. An
  unknown code raises `InvalidRequestError` before any call, naming the same area's code
  where `country_area_code_iso.json` knows it (`756` names `757`, Switzerland), or saying
  that a code belongs to the other table (`0` World is a partner only). Upstream itself
  answers a code that is no reporter with an empty result.
- Template updated to sdk-template v0.1.5 (`/add-endpoint` asks for
  `Field(validation_alias=...)`, not `alias=`; `/refresh-reference-data` formats the
  regenerated `enums.py`; `/refresh-upstream` runs `scripts/refresh_upstream.py` where it
  exists; `.gitignore` covers `.env.*` and `.envrc.*`; the MCP instructions name the
  `comtrade_list_*` tools; `_client.__all__` exports `auth`). `.copier-answers.yml` now
  records `rate_limit_per_minute: 40`, the limit `RATE_LIMIT` already applies.
