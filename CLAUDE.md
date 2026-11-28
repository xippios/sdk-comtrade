# sdk-comtrade — instructions for Claude Code

`xippios-comtrade` wraps UN Comtrade as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file holds what an agent needs to work on
the package: what it wraps, its layout, its commands and what only it knows. The documents it
follows, sdk-core's conventions among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file. The
rules that no change breaks stand in `.claude/rules/never.md`, which Claude Code loads with
this file.

## What this package wraps

| | |
| --- | --- |
| Upstream | UN Comtrade, https://comtrade.un.org |
| API base URL | `https://comtradeapi.un.org` |
| Documentation | https://comtrade.un.org/en/api-docs and the five OpenAPI files it no longer names, under https://comtradeapi.un.org/files/v1/app/apim/, snapshotted in `docs/upstream/` |
| Credentials | `COMTRADE_API_KEY` from the environment, sent as the `Ocp-Apim-Subscription-Key` header; never to the public operations or the reference files |
| Rate limit | 40 requests per minute, burst 1, one call every 1.5 s; set under the limit upstream documents, 1 call per second (60 per minute), since calls spaced exactly 1.0 s apart drew HTTP 429 (sdk-core ADR-0033); 500 calls a day, which the client does not count: `policy`, a `QuotaPolicy`, holds keyed calls back once upstream answers that the quota is spent (`_client.py`, sdk-core ADR-0037) |
| Write tools | no, this package is read-only |

The snapshot listed in `docs/upstream/FETCHED.md` is the reference for names, parameters and
semantics; a wrapper is never written from memory of the API. What UN Comtrade does that the
snapshot does not state stands once in `docs/upstream/OBSERVED.md`, each note with the probe
that showed it: its date, its operation and its recording under `tests/fixtures/` or its
packaged list. The sections below hold what the package does with it and cite a note by its
heading; the package's own text, its modules and scripts among it, dates no answer
(`tests/test_observed.py`, sdk-core ADR-0044, decision 3).

## The client, the key and the quota

The limits of a Basic Individual (free) key stand in `docs/upstream/help/subscriptions.md`,
and `_client.py` treats them so:

- **1 call per second.** The gateway's window is not exact ("Calls spaced 1.0 s apart draw
  HTTP 429"), so `RATE_LIMIT = RateLimit(per_minute=40, burst=1)`: one call every 1.5 s,
  never a burst, under the limit upstream documents (sdk-core ADR-0033 decision 1: 1 a
  second and 60 a minute documented, 40 a minute chosen after the recorded 429s, as
  https://github.com/xippios/sdk-comtrade/pull/4 decided). Core retries a 429 after
  `Retry-After`, each retry a call, and `policy` holds the next keyed call back until then.
  Offline tests skip the wait (core's plugin); a test marked `rate_limited` keeps it.
- **500 calls per day.** Every keyed request counts against it, a `countOnly` count among
  them, so `get_data` costs two calls, its count and its data, and `count_data` one; a
  `get_data` within 300 s of `count_data` of the same query sends its data request alone,
  since the cache answers its count. The client does not count calls. Over the quota API
  Management answers 403 "Out of call volume quota. Quota will be replenished in HH:MM:SS";
  `classify` maps a 403 that mentions a quota to `RateLimitError` with `retry_after`, and
  `policy`, `QuotaPolicy(limit_header=None, remaining_header=None, window=86400,
  spent=...)` installed on `config`, marks the quota spent until then: the next keyed call
  is refused with `RateLimitError` before it is sent (a wait within 30 s is waited out). It
  reads no `x-ratelimit-*` header, since those describe the per-second pace. Its `spent`
  hook reads two answers, this 403, whose time `window` caps at a day, and a 429 without
  `Retry-After`, for the "Try again in N seconds" of its body or else 1 s, so a pace refusal
  never holds calls back for the day-long `window`. The 403 has not been observed; never
  provoke it.
- **100,000 records per call.** Above it upstream cuts the answer without saying so ("Over
  100,000 records the answer is cut without a word"). `get_data` counts first by core's
  `fetch_counted`, raises core's `QueryTooLarge` before any data call and sets the count as
  `meta.total`.
- **12 periods per call.** `data/v1/get` and `tools/v1/getTradeBalance` refuse a 13th ("A
  thirteenth period: HTTP 400"), so `params.validate_get` and `validate_trade_balance`
  refuse it before the call; `validate_datasets`, of `data/v1/getDa` and
  `data/v1/getMetadata`, and `validate_bilateral_data` take more, as `getDa` and
  `getBilateralData` answer them.
- **Slow counts.** A broad count can outlast a minute ("A broad count can outlast a
  minute"), so the read timeout is 180 s (`READ_TIMEOUT`), and a timed-out attempt that core
  retries counts against the quota each time; so does each retry of a 5xx.
- **Keys may be periodically regenerated** on Basic accounts. A sudden 401 ("An unknown key:
  HTTP 401", `AuthError`) means re-copying the key from My API Portal,
  https://comtrade.un.org/en/api-portal, as `docs/upstream/help/subscriptions.md` links it,
  into the environment.

The reference files under `files/v1/app/reference/` are public: the one client fetches them
with `auth=None`, without the key, and its cache keeps each for the life of the process, by
the prefixes of `CACHE_LIFETIMES`, which keep the keyed reads under `data/v1` and `tools/v1`
for 300 s (core's plugin clears every `MemoryCache` around each offline test); a task's
`meta.retrieved_at` is the time its answer was stored. So `scripts/refresh_reference.py` and
`list_commodities` need no key and cost no quota; a reference fetch takes the 1.5 s pace
alone, since `policy` neither holds back nor reads a request sent with `auth=None`.

The public operations under `public/v1`, `getComtradeReleases` and `getWorldShare`
(`docs/upstream/apidocs/public.json`, whose `security` is `[{}, apiKeyHeader, apiKeyQuery]`,
a key optional, and whose `info` says "No subscription key required"), go through the same
client with `auth=None` too: `get_comtrade_releases` and `get_world_share` send no key and
spend no daily quota, and they take `RATE_LIMIT`'s pace (the Public tier allows 1 call per
second) alone: a spent key quota does not hold them back, nor the reference files. No prefix
of `CACHE_LIFETIMES` matches `public/v1`, so their answers stay out of the cache and a
release calendar always comes from upstream. Their operationIds are opaque hex ids, so the
wrappers are named after the paths (conventions §2). What they answer stands under "The
public operations" of `docs/upstream/OBSERVED.md`, and the package follows it so:

- The release list fits the default MCP cap, so `get_comtrade_releases` has no cap of its
  own, and its rows stay in upstream's order, which the spec does not state
  ("`getComtradeReleases`: the recent releases, newest first").
- `MCP_CAPS` gives `get_world_share` 400 rows or 100 KB, so one period for every reporter
  reaches an agent whole, where the default cap cut it at 157 rows and dropped the USA
  ("`getWorldShare` answers one row for each reporter and period").
- `world_share` and the placeholder `0001-01-01T00:00:00` of an unavailable dataset are kept
  as sent, a `Decimal` and a naive datetime ("The shares and the placeholder of an
  unavailable dataset").
- `period=recent` stays accepted, as the spec lists it and as `H6` stays, though upstream
  answered it with HTTP 500 ("`period=recent` answers HTTP 500"): the client makes 4
  attempts and raises `UpstreamError`.
- `classify` reads a refusal's detail in both spellings, `ErrorMessage` and `errorMessage`,
  with a `Content-Type` and without ("A malformed period: HTTP 400 without a
  `Content-Type`").
- Every release time is printed without a UTC offset ("The release times carry no zone"):
  the models keep them naive, none attached, and the tasks leave `meta.published_at` `None`.

Reporter and partner codes are UN Comtrade's, not ISO numeric: Switzerland is 757 in
`Reporters.json`. A code that upstream does not have counts 0 ("A code that upstream does
not have counts 0"), so the tasks refuse it before the call with core's `UnknownCode`
(conventions §5), naming the packaged `Reporters` list, its fetch date and the closest area,
757 for 756, because they check `reporter_code` against `reference/Reporters.json` and
partner codes against `reference/partnerAreas.json`, the package's copies of upstream's
`Reporters.json` and `partnerAreas.json`. The closest area is the code of the same ISO
alpha-3 in `country_area_code_iso.json`, else core's `nearest` by number, and a code of the
other table alone is named as such, since the two tables share one code space and differ
("The reporter and partner tables share one code space"). Every coded argument is checked so,
against the declaration of its list in `codes.py` by core's `check`: the areas,
`customs_code` and `mot_code`, where upstream's answer to an unknown code is not recorded,
`cl_code` and `flow_code`, which upstream refuses with HTTP 400, the spec's `type_code`,
`breakdown_mode` and `aggregate_by`, and `freq_code`, the spec's values with the words of
`Frequency.json`. A list of codes is checked in its order,
the arguments in theirs, and the first problem found is the refusal, which says that nothing
was sent; the validators gather no list of problems
(https://github.com/xippios/sdk-comtrade/issues/34).

The packaged lists carry upstream's words beside each value, under upstream's names, as
`scripts/refresh_reference.py` fetched them, keyless, each list's `fetched` giving the time:
`text` from `tradeRegimes.json` (`flowCode`), `CustomsCodes.json`,
`ModeOfTransportCodes.json`, `ModeOfSupply.json` (`mosCode`) and `Frequency.json`
(`freqCode`); `qtyAbbr` and
`qtyDescription` from `QuantityUnits.json` (`qtyUnitCode`), which has no `text`; `variable`
and `description` from the `cmd:<clCode>` entries of `ListofReferences.json` (`clCode`),
which has no `id` or `text` either. `freqCode` keeps the rows of `Frequency.json` whose id the
spec's enum lists, `A` and `M`, and its `note` names the file's row `Q`, which
`freq_code` refuses before the call ("`Frequency.json` holds `Q`, which `getDA` refuses"), by
the maintainer's decision of 2026-11-27. A value the package adds from
the spec stands alone (`MIF`, `XIF`, `BE`, `TM`, accepted upstream: "`BE`, `TM`, `MIF` and
`XIF`: values of the spec that the reference files lack"), and so do `typeCode`,
`breakdownMode` and `aggregateBy`, which no reference file lists. `ListofReferences.json`, the
index of the
reference files, is packaged as a table too. `list_codes(param)` returns a list's records as
the model `params.PACKAGED_LISTS` names for it (`MotCodeValue`: `mot_code`, `text`), and
`list_classifications(*, category=None)` the index's rows (`Reference`), both without a
call, without `search` and without a cap of their own, since each list fits the default cap
("The lengths of the lists"). An unknown `customs_code` or `mot_code` names the closest codes
with their text (core's `closest`, by code and then by text).

`MCP_CAPS` in `tasks.py` gives four tasks result caps of their own (sdk-core ADR-0038),
each 400 rows or 100 KB: three list tasks and `get_world_share`. `list_reporters` (256
rows, 69 KB) and `list_partners` (310, 83 KB) reach an agent whole, past Switzerland and the
USA, where the default cap of 200 rows cut them in upstream's alphabetical order. A
classification does not fit (8,262 HS codes); the cap's note tells the agent to search.
Those three take `search`, a case-insensitive substring of the code, the ISO alpha-3
(reporters, partners) or the text. One period of `get_world_share` for every reporter
reaches an agent whole; its note says to narrow by `reporter_code` or `period`.

When recording fixtures, budget the calls. The package client retries 429, 5xx and
transport errors up to four attempts, each a keyed call ("The classification `H6` answers
HTTP 500"), and a broad count outlasted the family's 60 s read timeout ("A broad count can
outlast a minute"). Record with a one-attempt copy of the client, spaced at least 1.5 s
apart, and never keep a body of many megabytes: narrow the query or use `maxRecords`. Replay
tests always send a placeholder key, whatever the shell holds: core's plugin pins it, for
each secret variable of `_client.ENV_VARS`. A new recording that shows what the snapshot
does not state brings its note to `docs/upstream/OBSERVED.md`, which ends with its probe.

What the recorded answers of trade data and of the datasets established stands under "Trade
data" and "Availability, metadata and the release pipeline" of `docs/upstream/OBSERVED.md`;
`reference/clCode.json` and `flowCode.json` name the fixtures of their values. The package
follows it so:

- `breakdown_mode` is sent only as given: without it upstream answers every breakdown, and
  the row with `partner2_code` 0, `customs_code` `C00` and `mot_code` 0 is the total
  ("`breakdownMode` `plus` is the default"). The `-2` and `GG` of `aggregate_by` are kept as
  sent ("`aggregateBy` answers `-2` and `GG`").
- `mosCode` is no parameter of the tasks: it filters, but not by the codes of
  `ModeOfSupply.json` ("`mosCode` filters, though no spec lists it";
  https://github.com/xippios/sdk-comtrade/issues/26).
- `H6` stays a valid `cl_code`, as `ListofReferences.json` lists it, though the spec's enum
  on `data/v1/get` lacks it ("The classification `H6` answers HTTP 500"), and a count of 0
  proves no code: `get_data` answers it with an empty list and a note ("A code that upstream
  does not have counts 0").
- `get_metadata` takes `reporter_code` and `period`, which the spec omits ("`getMetadata`
  honours `reporterCode` and `period`"), and `get_data_availability` more than 12 periods
  ("`getDa` answers one dataset for each reporter and period").
- `get_live_update` returns no `meta.total`, since upstream's `count` is not its rows'
  number, and reads its four times strictly in their three formats ("`getLiveUpdate`: 50
  rows and a `count` of 174", "`getLiveUpdate`: four times in three formats").

The two Tools operations (`docs/upstream/apidocs/comtradeTools.json`, both marked
"EXPERIMENTAL - USE SPARINGLY") are `get_trade_balance` and `get_bilateral_data`. What they
answered stands under "The Tools" of `docs/upstream/OBSERVED.md`. `countOnly` counts nothing
there ("`countOnly` counts nothing on the Tools"), so the tasks count nothing first and refuse
a query that names neither `reporter_code` nor `partner_code`, or no `cmd_code`, before it is
sent, by the maintainer's decision of 2026-11-26; the README's Scope names that requirement
with https://github.com/xippios/sdk-comtrade/issues/72.
`get_trade_balance` sends `breakdown_mode` only as given, since upstream's default answers
every breakdown ("`getTradeBalance` answers every breakdown by default"), and refuses a 13th
period. `get_bilateral_data` takes more periods and one `flow_code` of `TOOLS_FLOW_CODES`
("`getBilateralData`: one flow, thirteen periods and the total row"). Its mirror columns are,
per the Help Center, the partners' reported imports for a reporter's exports, and "depend on
the availability of other reporters rather than no-trade", and the note that qualifies them
counts the partners with a data gap and names none ("The mirror and the note on a data gap").
So the task returns the note and `timestamp_requested`, read as UTC ("`timestampRequested`
reads as UTC"), with the rows as one `BilateralData` (`note`, `timestamp_requested`, `data`),
not a list, as https://github.com/xippios/sdk-comtrade/pull/11 decided, and keeps
`primary_value_disc` and the `mirror2*` fields as sent ("`primaryValueDisc` and the `mirror2*`
fields"). Over MCP, core's result cap cuts its rows: an answer above 64 KB (about 40 rows)
keeps its `note` and `timestamp_requested` whole beside the rows that fit, with the cap's
note.

No MCP tool is paged. The client keeps core's bound of 8 MiB a body, `cache_max_bytes`,
and an answer of `get_data` can pass it, 100,000 rows of about 900 bytes; about 15,600 rows
of `getDa` and 6,000 of `getBilateralData` pass it too ("The size of a row"), and the
package bounds neither answer under that. A continuation past the bound would send its data
request again, a keyed call of the daily 500, while the cache answers `get_data`'s count
within its 300 s, so `get_data`, `get_data_availability` and `get_bilateral_data` stay
unpaged, as conventions §8 leave a tool whose answer can pass the bound (sdk-core ADR-0061,
decision 9).

## Layout

What this package adds to the family's tree, and its import path, stand in `docs/layout.md`,
imported here:

@docs/layout.md

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays the fixtures
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 -I scripts/adr_index.py --check   # the index matches the records in docs/adr/
uv run pytest -m live --tb=short --assert=plain   # needs XIPPIOS_LIVE_TESTS=1, COMTRADE_API_KEY

uv run xippios-comtrade-mcp   # stdio; add --http for streamable HTTP
```

`.github/workflows/live.yml` runs the live tests nightly at 05:31 UTC, a time derived from
the slug so that sources sharing a key never start together, and on demand; a pull request
never runs them. Only its `uv run pytest -m live --tb=short --assert=plain` step sees the
key, from the org secret `COMTRADE_API_KEY`. Every live run takes `--tb=short
--assert=plain`, since the log of `live.yml` is public: the first keeps a failing test's
frame arguments out of it, a raw upstream payload among them, and the second the values a
failed `assert` compares. A live test asserts on shapes and counts, never on a raw payload.

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15). The
update never overwrites a file this package fills, those that `_skip_if_exists` lists in
sdk-template's [`copier.yml`](https://github.com/xippios/sdk-template/blob/main/copier.yml),
and sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

The update writes every other file it renders again, since they are the template's,
`.claude/rules/never.md` among them. This package keeps no text of its own in them, the
docstring of `mcp.py` included: its own words go into a file it fills. A line it has to
add to one, such as a dependency in `pyproject.toml`, the update carries into the new
render, silently where the release leaves the lines around it alone and as a conflict
where it changes them.

## UN Comtrade specifics

Core's testing plugin counts the live run's requests and prints them in the log of
`live.yml` as `requests sent by the live run: <n>`, the count a release cites, and
`tests/test_live.py` states none. Its keyed tasks spend calls of the key's daily quota; the
public operations, `list_commodities` and core's nightly comparison of the nine packaged
lists and tables of `LIVE_LISTS` send no key, and the other list tasks answer from the
packaged lists without a request. A Basic Individual key allows 500 calls a day.

`docs/upstream/OBSERVED.md` is the one file under `docs/upstream/` written by hand. Each note
is a `###` section that ends with its probe, `Probe: <date>`, the operation by its path and
its sample, or, for the documentation's own address, the page it leads to and that page's row
in `docs/upstream/FETCHED.md`, and `tests/test_observed.py` holds that each sample was taken on a date the probe
gives and that the package's own text dates no answer but a decision's or an amendment's.
