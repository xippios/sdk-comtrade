# sdk-comtrade — instructions for Claude Code

`xippios-comtrade` wraps UN Comtrade as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds what an agent needs to work on
the package: what it wraps, its layout, its commands and its code rules. The documents it
follows, sdk-core's conventions among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file.

## What this package wraps

| | |
| --- | --- |
| Upstream | UN Comtrade, https://comtradeplus.un.org |
| API base URL | `https://comtradeapi.un.org` |
| Documentation | https://comtradeplus.un.org/ApiDocs, snapshotted in `docs/upstream/` |
| Credentials | `COMTRADE_API_KEY` from the environment, sent as the `Ocp-Apim-Subscription-Key` header; never to the public operations or the reference files |
| Rate limit | 1 per second documented; the client spaces calls 1.5 s apart (40 per minute), no burst; 500 calls a day, which the client does not count: `policy`, a `QuotaPolicy`, holds calls back once upstream answers that the quota is spent (`_client.py`, sdk-core ADR-0015) |
| Write tools | no, this package is read-only |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and
semantics; a wrapper is never written from memory of the API.

## The client, the key and the quota

The limits of a Basic Individual (free) key, from `docs/upstream/help/subscriptions.md`,
and how `_client.py` treats them:

- **1 call per second.** Documented, and upstream's headers agree (`x-ratelimit-limit: 1`,
  `x-ratelimit-operation-limit: 60`), but the gateway's window is not exact: with calls
  spaced exactly 1.0 s apart, 9 of 18 drew HTTP 429 "Rate limit is exceeded. Try again in
  1 seconds." (`Retry-After: 1`, `count_rate_limited.json`); at 1.5 s 2 of 39, at 2.0 s
  none of 10 (2026-10-23). So `RATE_LIMIT = RateLimit(per_minute=40, burst=1)`: one call
  every 1.5 s, never a burst, within the limit upstream documents (sdk-core ADR-0010
  decision 1: 1 a second and 60 a minute documented, 40 a minute chosen after the recorded
  429s, D41). Core retries a 429 after `Retry-After`, each retry a call, and `policy` holds
  the next call back until then. Offline tests skip the wait (core's plugin); a test marked
  `rate_limited` keeps it.
- **500 calls per day.** `countOnly` calls count against it, so `get_data` costs two
  calls (count, then data) and `get_counts` one. The client does not count calls. Over
  the quota API Management answers 403 "Out of call volume quota. Quota will be
  replenished in HH:MM:SS"; `classify` maps a 403 that mentions a quota to
  `RateLimitError` with `retry_after`, and `policy`, `QuotaPolicy(limit_header=None,
  remaining_header=None, window=86400, spent=...)` installed on `config`, marks the quota
  spent until then: the next call is refused with `RateLimitError` before it is sent
  (a wait within 30 s is waited out). It reads no `x-ratelimit-*` header, since those
  describe the per-second pace. Its `spent` hook reads two answers, this 403, whose time
  `window` caps at a day, and a 429 without `Retry-After`, for the "Try again in N
  seconds" of its body or else 1 s, so a pace refusal never holds calls back for the
  day-long `window`. The 403 has not been observed; never provoke it.
- **100,000 records per call.** Above it upstream answers HTTP 200 with the first
  100,000 rows, `count` 100000 and an empty `error`: it truncates silently (observed
  2026-10-23 for a query counted at 5,006,385). `get_data` counts first and raises
  `QueryTooLarge` before any data call.
- **12 periods per call.** A 13th gets HTTP 400 "Maximum number of periods is 12";
  `params.validate_get` refuses it before the call. `tools/v1/getTradeBalance` answers the
  same; `data/v1/getDa` and `tools/v1/getBilateralData` take more.
- **Slow counts.** A broad count can take over a minute, so the read timeout is 180 s
  (`TIMEOUTS`), and a timed-out attempt that core retries counts against the quota each
  time; so does each retry of a 5xx.
- **Keys may be periodically regenerated** on Basic accounts. A sudden 401 ("Access
  denied due to invalid subscription key", `AuthError`) means re-copying the key from
  https://comtradeplus.un.org/MyComtrade/APIPortal into the environment.

The reference files under `files/v1/app/reference/` are public: the one client fetches
them with `auth=None`, without the key, and its cache, narrowed to those paths by
`cache_filter`, keeps each for the life of the process (core's plugin clears every
`MemoryCache` around each offline test); `list_commodities`' `meta.retrieved_at` is the
time its file was stored. So `scripts/refresh_reference.py` and `list_commodities` need
no key and cost no quota; a reference fetch still takes the 1.5 s pace, and a spent quota
holds it back too.

The public operations under `public/v1`, `getComtradeReleases` and `getWorldShare`
(`docs/upstream/apidocs/public.json`, whose `security` is `[{}, apiKeyHeader,
apiKeyQuery]`, a key optional, and whose `info` says "No subscription key required"), go
through the same client with `auth=None` too: `get_comtrade_releases` and
`get_world_share` send no key and spend no daily quota, but they share `RATE_LIMIT`'s pace
(the Public tier allows 1 call per second) and `policy`, so a spent key quota holds them
back too, as it does the reference files. `cache_filter` keeps their answers out of the
cache, so a release calendar always comes from upstream. Their operationIds are opaque hex
ids, so the wrappers are named after the paths (conventions §2). What the keyless
recordings of 2026-10-28 established (`tests/fixtures/get_comtrade_releases/`,
`get_world_share/`):

- `getComtradeReleases`: 38 rows, `count` 38, 4.5 KB, released from 2026-10-22 to
  2026-10-28, newest first when recorded (the spec states no order), every `dateRelease`
  a midnight and none after the recording day; `nr` `N` (12) or `R` (26) and `flagCode`
  two letters (`CH` for 757), neither meaning stated. It fits the default MCP cap, so it
  has no cap of its own.
- `getWorldShare`: one row per reporter and period. Without `period` every period
  (Switzerland: 64 annual rows, 1962 to 2025), without `reporterCode` every reporter
  (2023: 214 rows, 88.5 KB; the default MCP cap cut it at 157, dropping the USA, row
  161, so `MCP_CAPS` gives `get_world_share` 400 rows or 100 KB and the whole period
  reaches an agent). The 214 values of 2023 sum to 1.0; whether a fraction or a
  percentage, and of which trade, is not stated. 47 of them have `isAvailable` false, a
  `worldShare` all the same and `0001-01-01T00:00:00` as both release times, upstream's
  placeholder on unavailable datasets, kept as sent, a naive datetime. Switzerland 2023's
  `firstReleased`/`lastReleased` equal `getDa`'s. `period=1900` answers 200, `count` 0.
  `period=2023-01` answered HTTP 400 "Invalid parameter value" with its detail spelt
  `MemberNames`/`ErrorMessage` and no `Content-Type`; `classify` reads its
  `ErrorMessage`.
- `period=recent` stays accepted, as the spec lists it and as `H6` stayed in 0.1.0, though
  upstream answered it with HTTP 500 "Something went wrong" (`count` -1, `error` an
  object) on all three tries, with `reporterCode` and without: the client makes 4 attempts
  and raises `UpstreamError`, and what `recent` selects is unknown.
- Every time field is printed without a UTC offset and no zone is stated: the models keep
  them naive, none attached, and the tasks leave `meta.published_at` `None`.

Reporter and partner codes are UN Comtrade's, not ISO numeric: Switzerland is 757 in
`Reporters.json`. Upstream answers 756, which is no reporter, with count 0; the tasks
refuse it before the call with core's `UnknownCode` (conventions §5), naming the packaged
`Reporters` list, its fetch date and the closest area, 757, because they check
`reporter_code` against `reference/Reporters.json` and partner codes against
`reference/partnerAreas.json`, the package's copies of upstream's `Reporters.json` and
`partnerAreas.json`; an ISO alpha-3 code the slices cannot resolve is refused the same
way, and so is a `customs_code` or `mot_code` the packaged `customsCode` or `motCode`
list lacks, where upstream's answer is not recorded. The other lists (`clCode` and
`flowCode`, which upstream refuses with HTTP 400, and the spec's `typeCode`, `freqCode`,
`breakdownMode`, `aggregateBy`) keep one `InvalidRequestError` naming every problem
found; the first unknown code ends the checks, so other problems show once it is fixed.
Both tables share one code space (a code in both is the same area) but differ: 0 World
and 56 other areas are partners only, 97 European Union and 975 ASEAN reporters only.

The packaged lists carry upstream's words beside each value, under upstream's names, as
`scripts/refresh_reference.py` fetched them (2026-10-28, keyless): `text` from
`tradeRegimes.json` (`flowCode`), `CustomsCodes.json`, `ModeOfTransportCodes.json` and
`ModeOfSupply.json` (`mosCode`); `qtyAbbr` and `qtyDescription` from `QuantityUnits.json`
(`qtyUnitCode`), which has no `text`; `variable` and `description` from the `cmd:<clCode>`
entries of `ListofReferences.json` (`clCode`), which has no `id` or `text` either; and,
as `text`, the wording the spec's description gives each value of `typeCode` and
`freqCode` ("C for commodities"). A value the package adds from the spec stands alone
(`MIF`, `XIF`, `BE`, `TM`), and so do `breakdownMode` and `aggregateBy`, whose
descriptions word none. `ListofReferences.json`, the index of the reference files, is
packaged as a table too. `list_codes(param)` returns a list's records as the model
`params.PACKAGED_LISTS` names for it (`MotCodeValue`: `mot_code`, `text`), and
`list_classifications(category=None)` the index's rows (`Reference`), both without a
call, without `search` and without a cap of their own: the largest list has 41 rows
(`qtyUnitCode`, about 4 KB) and the index 28 (about 6 KB), within the default cap. An
unknown `customs_code` or `mot_code` names the closest codes with their text (core's
`closest` by code and by text, else the most similar code).

`MCP_CAPS` in `tasks.py` gives four tasks result caps of their own (sdk-core ADR-0016),
each 400 rows or 100 KB: three list tasks and `get_world_share`. `list_reporters` (255
rows, 69 KB) and `list_partners` (310, 83 KB) reach an agent whole, past Switzerland and the
USA, where the default cap of 200 rows cut them in upstream's alphabetical order. A
classification does not fit (8,262 HS codes); the cap's note tells the agent to search.
Those three take `search`, a case-insensitive substring of the code, the ISO alpha-3
(reporters, partners) or the text. One period of `get_world_share` for every
reporter (214 rows, 88.5 KB for 2023) reaches an agent whole, where the default cap cut
it at 157 rows and dropped the USA; its note says to narrow by `reporter_code` or
`period`.

When recording fixtures, budget the calls. The package client retries 429, 5xx and
transport errors up to four attempts, each a keyed call (`clCode=H6` on `data/v1/get`
answered HTTP 500 to all five tries on 2026-10-23, two reporters, two product codes), and a
count over all reporters outlasted the former 60 s read timeout (the repeat answered in
27 s). Record with a one-attempt copy of the client, spaced at least 1.5 s apart, and
never keep a body of many megabytes: narrow the query or use `maxRecords`. Replay tests
always send a placeholder key, whatever the shell holds: core's plugin pins it, for the
variable `xippios_placeholder_key_envs` names in `pyproject.toml`.

What the recorded answers established (2026-10-23). The fixtures are named in
`reference/clCode.json` and `flowCode.json`, in the docstrings of the `getDa`,
`getMetadata` and `getLiveUpdate` wrappers, and, for the `data/v1/get` behaviours, in
`tests/test_tasks.py` and the PR description of wave 1:

- `data/v1/get`: `breakdownMode` `plus` is the default (omitting it gives the same 32 rows
  for Switzerland's 2023 exports); `classic` returns only the total row, as pinning
  `partner2Code` 0, `customsCode` C00 and `motCode` 0 does. `aggregateBy` returns the
  aggregated parameters as `-2` with `classificationCode` `GG`; counts match rows.
  `includeDesc` fills the `*ISO`/`*Desc` fields. For services the classification files
  name `200` (EB, EB02, EB10) or `S` (EB10S) as the total; counts confirm `200` on EB10
  and EB02 (one row each) and `TOTAL` counting 0 on EB10. On EB and EB10S both forms
  counted 0, which cannot be told from an unknown code. `mosCode`, not in the spec, is
  accepted and filters (`0`, `1`), but `Mode 1` from `ModeOfSupply.json` is refused; it
  is not a parameter of the tasks. Malformed values get HTTP 400 naming the field; a
  product or area code upstream does not have counts 0; an unknown `flowCode` or `clCode`
  gets HTTP 400.
- `data/v1/getDa`: takes more than 12 periods; refuses the spec's `EBSDMX`.
- `data/v1/getMetadata`: honours `reporterCode` and `period`, which the spec omits and
  `comtradeapicall` sends; answers `H6` like `HS`.
- `data/v1/getLiveUpdate`: 50 rows but `count` 174; no `publishedDate` field.

The two Tools operations (`docs/upstream/apidocs/comtradeTools.json`, both marked
"EXPERIMENTAL - USE SPARINGLY") are `get_trade_balance` and `get_bilateral_data`, recorded
on 2026-10-28 under `tests/fixtures/get_trade_balance/` and `get_bilateral_data/`, Switzerland
and `TOTAL`. Both answered the package's key; the spec's 403 for a free-tier key not on
getTradeBalance's allow-list ("User not allowed", `AuthError` by core's mapping) did not
occur, and no other 403 was seen. `countOnly`, not in the spec, counts nothing:
getTradeBalance answers `count` 0 and a placeholder for a query of 48 rows, getBilateralData
ignores it; so the tasks count nothing first and require `reporter_code` or `partner_code`,
and `cmd_code`. getTradeBalance without `breakdownMode` answers every breakdown (48 rows
with the World in 2023), `classic` the total row; it refuses a 13th period. getBilateralData
takes 13 periods and one `flowCode` (only `X` was recorded, `M` is the spec's other value;
`M,X`: HTTP 400, its detail's message spelt `ErrorMessage`, which `classify` reads), fills
no description with `includeDesc`, and answers in classic mode (`customsCode` C00,
`motCode` 0). Its mirror columns are, per the Help Center, the partners' reported imports
for a reporter's exports, and "depend on the availability of other reporters rather than
no-trade": for Switzerland's 2023 exports Afghanistan's mirror is 0, and it is inferred,
not stated, to be one of the two partners the note counts with a data gap (DPRK alone: 1,
the USA alone: none). `primaryValueDisc` equals (mirror − value) / value in every recorded
row and `mirror2*` is empty or 0; upstream states neither meaning. Its envelope's
`timestampRequested` is UTC per the spec and its `note` counts the partners with a data gap
and their share of world trade, naming none, in wording that varies; the task returns both
with the rows as one `BilateralData` (`note`, `timestamp_requested`, `data`), not a list,
so the note that qualifies the mirror values reaches the agent (Johannes, 2026-10-28);
`get_mirror_flows`' `MirrorFlows` has the same shape. Over MCP, core's result cap cuts
only a top-level list: an answer above 64 KB (about 40 rows of `BilateralData`, 60 of
`MirrorFlows`) arrives as a text preview.

The task-shaped slices (wave 2: `get_bilateral_flows`, `get_commodity_series`,
`get_world_trade`, `get_top_partners`) call `data/v1/get` through `api.get` with
`params.SLICE_PINS`: `typeCode` C, `breakdownMode` classic, `partner2Code` 0, `motCode` 0,
`customsCode` C00, `includeDesc` true, so one row is reporter × partner × product code ×
period, projected into `TradeFlowRecord` with `UpstreamModel.project`. Each is bounded by
its arguments (product codes × periods; periods; 255 reporters; 310 partners), so none
counts first; `QueryTooLarge(bound, bound=True)` refuses a bound over 100,000 before the
call, which is why the slices take single product codes, not `AG2` or `27??`. A
commodity series is capped by calls instead: at most 120 periods
(`params.MAX_SERIES_PERIODS`, ten calls of 12 against 500 a day).
`params.validate_slice` resolves an area given as code or ISO alpha-3 (an expired code
gives way to the one in use; among partners the code that is also a reporter code wins,
842 not 840, as `partners_ch_total_2023.json` shows) and derives `freqCode` from the
period format (`YYYY` A, `YYYYMM` M, a mix refused). `get_commodity_series` sends the
periods 12 per call, in the order given, and sorts the joined rows by period.
`get_top_partners` drops partner 0, World, because it is the total over all partners, not a
partner, and ranks the rest by `primary_value` here; `get_world_trade` sorts the same way,
so a capped MCP result (104 of 167 rows for HS 27 imports 2023) keeps the largest.

The mirror slice, `get_mirror_flows`, calls `tools/v1/getBilateralData` through
`api.get_bilateral_data` instead, with `params.validate_mirror_flows`: `validate_slice`'s
resolution and checks, one flow of `TOOLS_FLOW_CODES`, at most 12 periods (the slices'
bound, though upstream answered 13), `typeCode` C and no `includeDesc`, which filled no
description. It is bounded by product codes × periods like `get_bilateral_flows`, keeps
its rows in upstream's order (period order in both recordings: one call, nothing to
join, unlike the series), projects them into `MirrorFlowRecord` (the identity fields,
the reported figures and their mirrors, `primary_value_disc` and `mirror2_primary_value`
as sent; the empty `mirror2*` quantities left out) and returns them with upstream's note
as one `MirrorFlows`. Recorded on 2026-10-28 for Switzerland's
chapter 27 exports to the USA (`ch_us_27_2022_2023_x.json`, `ch_us_27_202301_x.json`
under `tests/fixtures/get_bilateral_data/`): chapter rows and monthly periods are
answered, the note found no gap, and the reported values equal `data/v1/get`'s
(`get/bilateral_ch_us_2022_2023.json`) while the USA's mirror is far smaller
(`6444455.0` against `126191129.831` in 2023).

## Layout

```
src/xippios/comtrade/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the one configured AsyncClient (base URL, key, rate limit, classify),
                   its daily quota policy and the cache of the public reference files
  errors.py        RECORD_LIMIT, MAX_PERIODS and QueryTooLarge
  models.py        pydantic models mirroring upstream payloads (UpstreamModel); by the
                   family's precedent also an enumeration written by hand, for a value set
                   upstream documents and no packaged list renders
  api/             endpoint wrappers, one module per upstream operation (conventions §2)
  tasks.py         task functions; __all__ is what the adapters register, but BULK_TASKS,
                   the Python-only ones; MCP_CAPS the result caps of three list tasks
                   and get_world_share
  mcp.py           xippios-comtrade-mcp entry point
  http.py          FastAPI router
  params.py        packaged lists and tables: PACKAGED_LISTS, PACKAGED_TABLES,
                   CL_CODES_FROM_SPEC, classification_files(); checks run before a
                   call: validate_get(), validate_datasets(),
                   validate_classification_file(), for the Tools validate_trade_balance()
                   and validate_bilateral_data() (TOOLS_FLOW_CODES); for the slices
                   validate_slice()
                   (areas by code or ISO alpha-3, periods of one format), SLICE_PINS
                   and MAX_SERIES_PERIODS; for the mirror slice validate_mirror_flows()
  enums.py         StrEnums generated from the packaged lists; never edited by hand
  reference/       packaged lists and tables, reference/<name>.json, read with
                   PackagedList.load, plus README with provenance
scripts/
  refresh_reference.py   fetches the packaged lists through api/ and regenerates enums.py
  refresh_upstream.py    regenerates docs/upstream/ and its FETCHED.md from upstream
  adr_index.py           writes docs/adr.md and docs/adr.json from the records in docs/adr/;
                         --check fails while either is stale
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, <wrapper>/<case>.json, never hand-written
  test_family.py   core's family check, one line: namespace levels, py.typed, __version__,
                   the adapters serving exactly the tasks, task shapes and docstrings, the
                   README status table, the template tag, the core bound
  test_tasks.py    checks of this package's own plus per-task replay tests
  test_scripts.py  the maintenance scripts under scripts/, checked without running them
  test_live.py     @pytest.mark.live smoke tests, one per task
docs/
  upstream/        documentation snapshot and FETCHED.md
  adr/             this package's design decisions, one NNNN-<slug>.md record each, laid
                   out in its README.md
  adr.md           the index of the decisions, written by scripts/adr_index.py, never by hand
  adr.json         the same index, for machines
  reports/         dated reports, the evidence a decision cites, laid out in its README.md
changelog/         the next release's changelog entries, one fragment per change, laid out
                   in its README.md
CHANGELOG.md       the releases, each section assembled from the fragments
.github/workflows/ ci.yml (the required ci check, with the changelog and fixture-size steps),
                   publish.yml (the release train: tag, build, PyPI), live.yml (nightly live
                   tests), organization.yml (the organization's checks from xippios/.github:
                   conventions, a review of a pull request against the documents the README
                   lists, and adr-index, which runs scripts/adr_index.py --check)
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep
```

The import path is `xippios.comtrade` (sdk-core ADR-0006); `src/xippios/` is a
namespace package.
Where the API's operation ids repeat across its services, `api/` keeps one module per service
instead, named after the service, and this Layout says so (conventions §2).

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays the fixtures
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 scripts/adr_index.py --check   # the index matches the records in docs/adr/
uv run pytest -m live --tb=short --assert=plain   # needs XIPPIOS_LIVE_TESTS=1, COMTRADE_API_KEY

uv run xippios-comtrade-mcp   # stdio; add --http for streamable HTTP
```

`uv run pytest` is offline: core's plugin refuses the network and skips the rate limiter's
waits in every test not marked `live` (conventions §10, sdk-core ADR-0013). A test that
asserts a limiter wait or a quota pause is marked `rate_limited`, one that must reach the
network `network`.
It sends the key's placeholder, with `COMTRADE_API_KEY` set to it because
`pyproject.toml` names that variable under `xippios_placeholder_key_envs`; the package
keeps no placeholder fixture of its own.

`.github/workflows/live.yml` runs the live tests nightly at 05:31 UTC, a time derived from
the slug so that sources sharing a key never start together, and on demand; a pull request never runs them.
Only its `uv run pytest -m live --tb=short --assert=plain` step sees the key, from the org secret `COMTRADE_API_KEY`.
Every live run takes `--tb=short --assert=plain`, since the log of `live.yml` is public:
the first keeps a failing test's frame arguments out of it, a raw upstream payload among
them, and the second the values a failed `assert` compares. A live test asserts on shapes
and counts, never on a raw payload.

## Code rules

- Three layers (sdk-core ADR-0001, conventions §2): endpoint wrappers in `api/`, task
  functions in `tasks.py`, adapters in `mcp.py` and `http.py`. The adapters register
  `tasks.__all__` and call only tasks, the tasks call only wrappers and reference data, and
  a wrapper returns models.
- Upstream's documented error shapes go into `classify` in `_client.py`, once, and an error
  class of the package's own into `errors.py`; a wrapper never inspects a status code
  (conventions §5, §6).
- A change brings its tests, written before the code, and passes the offline checks above;
  its changelog entry is a fragment under `changelog/`, one file holding its bullet, as
  `changelog/README.md` lays it out (conventions §12). Commit subjects follow Conventional
  Commits (conventions §13): the rule binds a pull request's own commits, not the commit
  that lands the pull request on `main`, whose subject GitHub writes.
- `ruff` leaves `docs/` and `.claude/` alone (`pyproject.toml`), so the upstream snapshot
  keeps its bytes: never reformat it.
- A convention that seems wrong is followed anyway and said in the pull request; changing
  it is a change of sdk-core's `docs/conventions.md` with an ADR.

## Never

- Never hand-write a fixture, and never commit one without grepping it for key patterns
  (conventions §10).
- Never read or print `.envrc`, `.env`, the credential variable of this package,
  `COMTRADE_API_KEY`, or any variable ending in `_API_KEY`, `_REFRESH_TOKEN` or
  `_SECRET`.
- Never write a key, a token or another credential into a file or a commit.
- Never put logic in `mcp.py` or `http.py`, and never add a route or a tool by hand: the
  adapters register `tasks.__all__` (sdk-core ADR-0001).
- Never rename or re-map an upstream concept to another source's (sdk-core ADR-0003).
- Never return a documented personal identifier in a task's projection, echo one in
  `meta.request`, or commit one in a fixture (sdk-core ADR-0017).
- Never edit `docs/upstream/` by hand: `/refresh-upstream` fetches it, and the pull request
  shows its diff (conventions §3).
- Never add `src/xippios/__init__.py`, nor an `__init__.py` at a level between it and the
  package (sdk-core ADR-0006).
- Never push a tag by hand: a release's tag comes from `publish.yml` alone (conventions §12).

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15): the
update renders the template's files again and never overwrites the files this package
fills, `__init__.py`, `_client.py`, `errors.py`, `models.py`, `api/`, `parse/`, `tasks.py`,
`params.py`, `enums.py`, `reference/`, `scripts/refresh_reference.py`,
`scripts/refresh_upstream.py`, `tests/test_tasks.py`, `tests/test_live.py`,
`tests/fixtures/`, `docs/upstream/`, `docs/adr.md`, `docs/adr.json`, `README.md`,
`CHANGELOG.md` and `CLAUDE.md`. sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

## When something is unclear

Prefer the smallest change that satisfies the documents the README lists, state the
assumption in the pull request's description, and stop rather than guess at upstream
semantics or the shape of the public API.

## UN Comtrade specifics

The live run costs thirteen keyed calls and eight keyless requests (`tests/test_live.py`,
whose docstring counts them): the reachability probe sends no key, the list tasks fetch
the public reference files without it, and the two public operations send none. A Basic
Individual key allows 500 calls a day.
