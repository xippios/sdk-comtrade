# sdk-comtrade — instructions for Claude Code

`xippios-comtrade` wraps UN Comtrade as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file is the contract for every session
that works here; the family rules it points to apply as well.

## What this package wraps

| | |
| --- | --- |
| Upstream | UN Comtrade, https://comtradeplus.un.org |
| API base URL | `https://comtradeapi.un.org` |
| Documentation | https://comtradeplus.un.org/ApiDocs, snapshotted in `docs/upstream/` |
| Credentials | `COMTRADE_API_KEY` from the environment, sent as the `Ocp-Apim-Subscription-Key` header |
| Rate limit | 1 per second documented; the client spaces calls 1.5 s apart, no burst (`_client.py`) |
| Write tools | no, this package is read-only |

The snapshot in `docs/upstream/` is the reference for names, parameters and semantics.
If it is empty or stale, run `/refresh-upstream` first and review the diff. Never write a
wrapper from memory of the API.

## The client, the key and the quota

The limits of a Basic Individual (free) key, from `docs/upstream/help/subscriptions.md`,
and how `_client.py` treats them:

- **1 call per second.** Documented, and upstream's headers agree (`x-ratelimit-limit: 1`,
  `x-ratelimit-operation-limit: 60`), but the gateway's window is not exact: with calls
  spaced exactly 1.0 s apart, 9 of 18 drew HTTP 429 "Rate limit is exceeded. Try again in
  1 seconds." (`Retry-After: 1`, `count_rate_limited.json`); at 1.5 s 2 of 39, at 2.0 s
  none of 10 (2026-10-23). So `RATE_LIMIT = RateLimit(per_minute=40, burst=1)`: one call
  every 1.5 s, never a burst. Core retries a 429 after `Retry-After`, each retry a call.
  Replay tests pay the 1.5 s too.
- **500 calls per day.** Not enforced client-side. `countOnly` calls count against it,
  so `get_data` costs two calls (count, then data) and `get_counts` one. Over the quota
  API Management answers 403 "Out of call volume quota. Quota will be replenished in
  HH:MM:SS"; `classify` maps a 403 that mentions a quota to `RateLimitError` with
  `retry_after`. That answer has not been observed; never provoke it.
- **100,000 records per call.** Above it upstream answers HTTP 200 with the first
  100,000 rows, `count` 100000 and an empty `error`: it truncates silently (observed
  2026-10-23 for a query counted at 5,006,385). `get_data` counts first and raises
  `QueryTooLarge` before any data call.
- **12 periods per call.** A 13th gets HTTP 400 "Maximum number of periods is 12";
  `params.validate_get` refuses it before the call.
- **Slow counts.** A broad count can take over a minute, so the read timeout is 180 s
  (`TIMEOUTS`), and a timed-out attempt that core retries counts against the quota each
  time; so does each retry of a 5xx.
- **Keys may be periodically regenerated** on Basic accounts. A sudden 401 ("Access
  denied due to invalid subscription key", `AuthError`) means re-copying the key from
  https://comtradeplus.un.org/MyComtrade/APIPortal into the environment.

The reference files under `files/v1/app/reference/` are public: `reference_client`
fetches them without the key and keeps each for the life of the process (core's GET
cache, `REFERENCE_CACHE`; tests empty it before each test), so
`scripts/refresh_reference.py` and `list_commodities` need no key and cost no quota.
Reporter and partner codes are UN Comtrade's, not ISO numeric: Switzerland is 757 in
`Reporters.json`. Upstream answers 756, which is no reporter, with count 0; the tasks
refuse it before the call, naming 757, because they check `reporter_code` against
`reference/Reporters.csv` and partner codes against `reference/partnerAreas.csv`, the
package's copies of upstream's `Reporters.json` and `partnerAreas.json`. Both tables
share one code space (a code in both is the same area) but differ: 0 World and 56 other
areas are partners only, 97 European Union and 975 ASEAN reporters only.

The MCP result cap (200 rows or 64 KB) cuts `list_reporters` (255 rows) and
`list_partners` (310) in upstream's alphabetical order, past Switzerland and the USA,
and shows only the top of a classification; so the three list tasks take `search`, a
case-insensitive substring of the code, the ISO alpha-3 (reporters, partners) or the
text, and their docstrings tell agents to search.

When recording fixtures, budget the calls. The package client retries 429, 5xx and
transport errors up to four attempts, each a keyed call (`clCode=H6` on `data/v1/get`
answered HTTP 500 to all five tries on 2026-10-23, two reporters, two product codes), and a
count over all reporters outlasted the former 60 s read timeout (the repeat answered in
27 s). Record with a one-attempt copy of the client, spaced at least 1.5 s apart, and
never keep a body of many megabytes: narrow the query or use `maxRecords`. Replay tests
always send a placeholder key, whatever the shell holds (`tests/conftest.py`).

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
  is not a parameter of the tasks. Malformed values get HTTP 400 naming the field; a code
  upstream does not have counts 0.
- `data/v1/getDa`: takes more than 12 periods; refuses the spec's `EBSDMX`.
- `data/v1/getMetadata`: honours `reporterCode` and `period`, which the spec omits and
  `comtradeapicall` sends; answers `H6` like `HS`.
- `data/v1/getLiveUpdate`: 50 rows but `count` 174; no `publishedDate` field.

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

## Read first, in this order

1. `docs/upstream/FETCHED.md` and the files it lists: what the upstream actually offers
2. The family conventions: `../sdk-core/docs/conventions.md` and `../sdk-core/docs/adr/`
   (also at https://github.com/xippios/sdk-core/tree/main/docs)
3. `../sdk-core/docs/definition-of-done.md`: what a PR must satisfy
4. The family file `../CLAUDE.md`

## The one rule: three layers (ADR-0001)

```
api/<operation>.py   one async function per upstream operation, upstream names, returns models
tasks.py             the public API: composes wrappers, returns Result[T], sync facade via sync()
mcp.py  http.py      adapters: register tasks.__all__, nothing else. Never edited to add an endpoint.
```

Adapters call only task functions. Tasks call only endpoint wrappers and reference
data. If logic appears in `mcp.py` or `http.py`, it belongs in `tasks.py`.

## Layout

```
src/xippios/comtrade/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the configured AsyncClient (base URL, key, rate limit, classify) and
                   a keyless one for the public reference files
  errors.py        RECORD_LIMIT, MAX_PERIODS and QueryTooLarge
  models.py        pydantic models mirroring upstream payloads (UpstreamModel)
  api/             endpoint wrappers, one module per upstream operation
  tasks.py         task functions; __all__ is what the adapters register
  mcp.py           xippios-comtrade-mcp entry point
  http.py          FastAPI router
  params.py        packaged lists and tables: PACKAGED_LISTS, packaged_values(),
                   PACKAGED_TABLES, packaged_table(), packaged_table_info(),
                   classification_files(); checks run before a call: validate_get(),
                   validate_datasets(), validate_classification_file(); for the
                   slices validate_slice() (areas by code or ISO alpha-3, periods of
                   one format), SLICE_PINS and MAX_SERIES_PERIODS
  enums.py         StrEnums generated from the packaged lists; never edited by hand
  reference/       packaged value lists (JSON), tables (CSV, provenance in tables.json)
                   plus README with provenance
scripts/
  refresh_reference.py   fetches the packaged lists through api/ and regenerates enums.py
  refresh_upstream.py    regenerates docs/upstream/ and its FETCHED.md from upstream
tests/
  conftest.py      enables xippios.core.testing.plugin; placeholder key for replay
  fixtures/        recorded responses, <endpoint>/<case>.json, never hand-written
  test_tasks.py    structural checks on every task plus per-task replay tests
  test_adapters.py the adapters expose exactly tasks.__all__
  test_layout.py   namespace levels stay empty; py.typed ships
  test_live.py     @pytest.mark.live smoke tests, one per task
docs/upstream/     documentation snapshot and FETCHED.md
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep
```

`src/xippios/` has **no** `__init__.py`: it is a PEP 420 namespace package shared with
`xippios-core` and every other source package.
Never add one; `tests/test_layout.py` fails if it appears. The import path is
`xippios.comtrade` (ADR-0006).

## How to add an endpoint

Run `/add-endpoint <upstream operation>`. In short:

1. Read the operation in `docs/upstream/`. Names, parameters and semantics come from
   there, snake_cased, nothing renamed, nothing normalised across sources.
2. `models.py`: an `UpstreamModel` per payload object; dates, numbers and enums typed.
3. `api/<operation>.py`: one async wrapper that calls `_client.client` and returns
   models through `xippios.core.parse`.
4. `tasks.py`: an async task that composes wrappers and returns `Result[T]` with full
   `ResultMeta` (source, endpoint, request parameters, `published_at`/`vintage` when the
   upstream gives them). Derive the sync one with `sync()`, add its name to `__all__`,
   re-export it from `__init__.py`.
5. Docstring for agents: one sentence, then `Args:` with examples of valid values for
   every parameter. The MCP tool description and the OpenAPI summary come from it.
6. `/record-fixture` for at least one case, a replay test in `test_tasks.py` that also
   calls the tool end to end with `xippios.core.testing.mcp_call`, a live smoke test in
   `test_live.py`.
7. `CHANGELOG.md` under Unreleased, README status table, then the full check suite.

Reference lookups (commodities, countries, attributes) are tasks too, named
`list_<thing>`, so agents can form valid calls. A task-shaped function that returns a
subset of an upstream record builds its model with `UpstreamModel.project`; nothing is
renamed or computed, parsing a value (`parse_decimal`) is the only override. Upstream's
documented error shapes go into `ClientConfig.classify` in `_client.py`, once; wrappers
use `client.get_json` and never inspect status codes.

## How to record a fixture

Run `/record-fixture <endpoint> <case> <parameters>`. It performs one live request
through the real client with `xippios.core.testing.record_sync` and writes
`tests/fixtures/<endpoint>/<case>.json` with credentials scrubbed. Grep the file for
key patterns before committing. Fixtures are never typed in by hand.

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays fixtures
uv run pytest -m live              # needs XIPPIOS_LIVE_TESTS=1 and COMTRADE_API_KEY; 11 keyed calls, 3 keyless
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
uv run xippios-comtrade-mcp   # stdio; add --http for streamable HTTP
```

## Workflow rules

- Branch from `main` as `feature/<topic>`, `fix/<topic>`, `chore/<topic>` or `docs/<topic>`.
  Never commit to `main`.
- Commit small, with Conventional Commits messages (`feat(tasks): add get_balance_sheet`).
- Open the PR with `gh pr create`; the body is the definition-of-done checklist from
  `.github/PULL_REQUEST_TEMPLATE.md`, ticked honestly, with assumptions listed.
- `ruff` leaves `docs/` alone; never reformat the upstream snapshot.
- Template updates: `uvx copier update` pulls the latest sdk-template tag into the
  infrastructure files (answers are in `.copier-answers.yml`; content files such as
  `tasks.py`, `api/`, `tests/` and `README.md` are never overwritten). Review the diff
  and open a `chore/template-update` PR.
- If a convention seems wrong, say so in the PR and follow it anyway; changing it is a
  PR against `sdk-core/docs/conventions.md` plus an ADR.

## Never

- Never hand-write a fixture, and never commit one without grepping for key patterns.
- Never read or print `.envrc`, `.env`, or any variable ending in `_API_KEY`.
- Never write a key into a file or a commit.
- Never put logic in `mcp.py` or `http.py`; never add a route or tool by hand.
- Never rename or re-map an upstream concept to another source's (ADR-0003).
- Never edit `docs/upstream/` by hand; `/refresh-upstream` fetches, a PR reviews.
- Never add `src/xippios/__init__.py`.
- Never tag, merge, release, force-push, or touch `gh secret`. Those are human actions.

## When something is unclear

Prefer the smallest change that satisfies the documents above, state the assumption in
the PR description, and stop rather than guess at upstream semantics or public API shape.
