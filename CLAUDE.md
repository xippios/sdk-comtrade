# sdk-comtrade — instructions for Claude Code

`xippios-comtrade` wraps UN Comtrade as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds the facts of this package;
the family rules every source shares are in `.claude/family.md`, which the next line imports.

@.claude/family.md

## What this package wraps

| | |
| --- | --- |
| Upstream | UN Comtrade, https://comtradeplus.un.org |
| API base URL | `https://comtradeapi.un.org` |
| Documentation | https://comtradeplus.un.org/ApiDocs, snapshotted in `docs/upstream/` |
| Credentials | `COMTRADE_API_KEY` from the environment, sent as the `Ocp-Apim-Subscription-Key` header |
| Rate limit | 1 per second documented; the client spaces calls 1.5 s apart (40 per minute), no burst; 500 calls a day, which the client does not count: `policy`, a `QuotaPolicy`, holds calls back once upstream answers that the quota is spent (`_client.py`, ADR-0015) |
| Write tools | no, this package is read-only |

The snapshot in `docs/upstream/` is the reference for names, parameters and semantics.

## The client, the key and the quota

The limits of a Basic Individual (free) key, from `docs/upstream/help/subscriptions.md`,
and how `_client.py` treats them:

- **1 call per second.** Documented, and upstream's headers agree (`x-ratelimit-limit: 1`,
  `x-ratelimit-operation-limit: 60`), but the gateway's window is not exact: with calls
  spaced exactly 1.0 s apart, 9 of 18 drew HTTP 429 "Rate limit is exceeded. Try again in
  1 seconds." (`Retry-After: 1`, `count_rate_limited.json`); at 1.5 s 2 of 39, at 2.0 s
  none of 10 (2026-10-23). So `RATE_LIMIT = RateLimit(per_minute=40, burst=1)`: one call
  every 1.5 s, never a burst, within the limit upstream documents (ADR-0010 decision 1:
  1 a second and 60 a minute documented, 40 a minute chosen after the recorded 429s,
  D41). Core retries a 429 after `Retry-After`, each retry a call, and `policy` holds the
  next call back until then. Offline tests skip the wait (core's plugin); a test marked
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

`MCP_CAPS` in `tasks.py` gives the three list tasks result caps of their own (ADR-0016):
400 rows or 100 KB, so `list_reporters` (255 rows, 69 KB) and `list_partners` (310,
83 KB) reach an agent whole, past Switzerland and the USA, where the default cap of 200
rows cut them in upstream's alphabetical order. A classification does not fit (8,262 HS
codes); the cap's note tells the agent to search. All three take `search`, a
case-insensitive substring of the code, the ISO alpha-3 (reporters, partners) or the
text.

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
takes 13 periods and one `flowCode` (only `X` was recorded, `M` is the spec's other
value; `M,X`: HTTP 400, its detail's message spelt `ErrorMessage`, which `classify`
reads), fills no description with `includeDesc`, and
answers in classic mode (`customsCode` C00, `motCode` 0). Its mirror columns are, per the
Help Center, the partners' reported imports for a reporter's exports, and "depend on the
availability of other reporters rather than no-trade": for Switzerland's 2023 exports
Afghanistan's mirror is 0, and it is inferred, not stated, to be one of the two partners
the note counts with a data gap (DPRK alone: 1, the USA alone: none). `primaryValueDisc` equals (mirror − value) / value in
every recorded row and `mirror2*` is empty or 0; upstream states neither meaning. Its
envelope's `timestampRequested` is UTC per the spec and its `note` counts the partners
with a data gap and their share of world trade, naming none, in wording that varies; the task returns both with the rows as one `BilateralData`
(`note`, `timestamp_requested`, `data`), the one task whose result is not a list, so the
note that qualifies the mirror values reaches the agent (Johannes, 2026-10-28). Over MCP,
core's result cap cuts only a top-level list: an answer above 64 KB (about 40 rows)
arrives as a text preview.

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

## Layout

```
src/xippios/comtrade/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the one configured AsyncClient (base URL, key, rate limit, classify),
                   its daily quota policy and the cache of the public reference files
  errors.py        RECORD_LIMIT, MAX_PERIODS and QueryTooLarge
  models.py        pydantic models mirroring upstream payloads (UpstreamModel)
  api/             endpoint wrappers, one module per upstream operation
  tasks.py         task functions; __all__ is what the adapters register, but BULK_TASKS,
                   the Python-only ones; MCP_CAPS the list tasks' result caps
  mcp.py           xippios-comtrade-mcp entry point
  http.py          FastAPI router
  params.py        packaged lists and tables: PACKAGED_LISTS, PACKAGED_TABLES,
                   CL_CODES_FROM_SPEC, classification_files(); checks run before a
                   call: validate_get(), validate_datasets(),
                   validate_classification_file(), for the Tools validate_trade_balance()
                   and validate_bilateral_data() (TOOLS_FLOW_CODES); for the slices
                   validate_slice()
                   (areas by code or ISO alpha-3, periods of one format), SLICE_PINS
                   and MAX_SERIES_PERIODS
  enums.py         StrEnums generated from the packaged lists; never edited by hand
  reference/       packaged lists and tables, reference/<name>.json, read with
                   PackagedList.load, plus README with provenance
scripts/
  refresh_reference.py   fetches the packaged lists through api/ and regenerates enums.py
  refresh_upstream.py    regenerates docs/upstream/ and its FETCHED.md from upstream
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  fixtures/        recorded responses, <endpoint>/<case>.json, never hand-written
  test_family.py   core's family check, one line: namespace levels, py.typed, __version__,
                   the adapters serving exactly the tasks, task shapes and docstrings, the
                   README status table, the template tag, the core bound
  test_tasks.py    checks of this package's own plus per-task replay tests
  test_scripts.py  the maintenance scripts under scripts/, checked without running them
  test_live.py     @pytest.mark.live smoke tests, one per task
docs/upstream/     documentation snapshot and FETCHED.md
.claude/family.md  the family rules, the template's, imported above
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data,
                   release-prep, adopt-release
```

The import path is `xippios.comtrade` (ADR-0006); `src/xippios/` is a namespace
package.

## Commands

```bash
uv run pytest -m live --tb=short   # needs XIPPIOS_LIVE_TESTS=1 and COMTRADE_API_KEY

uv run xippios-comtrade-mcp   # stdio; add --http for streamable HTTP
```

The offline run sends the key's placeholder, with `COMTRADE_API_KEY` set to it because
`pyproject.toml` names that variable under `xippios_placeholder_key_envs`; the package
keeps no placeholder fixture of its own.

`.github/workflows/live.yml` runs the live tests nightly at 05:31 UTC, a time derived from
the slug so that sources sharing a key never start together.
Only its `uv run pytest -m live --tb=short` step sees the key, from the org secret `COMTRADE_API_KEY`.

## UN Comtrade specifics

The live run costs twelve keyed calls and four keyless requests (`tests/test_live.py`, whose
docstring counts them): the reachability probe sends no key, and the list tasks fetch the
public reference files without it. A Basic Individual key allows 500 calls a day.
