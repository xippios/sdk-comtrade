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
| Upstream | UN Comtrade, https://comtradeplus.un.org |
| API base URL | `https://comtradeapi.un.org` |
| Documentation | https://comtradeplus.un.org/ApiDocs, snapshotted in `docs/upstream/` |
| Credentials | `COMTRADE_API_KEY` from the environment, sent as the `Ocp-Apim-Subscription-Key` header; never to the public operations or the reference files |
| Rate limit | 40 requests per minute, burst 1, one call every 1.5 s; set under the limit upstream documents, 1 call per second (60 per minute), since calls spaced exactly 1.0 s apart drew HTTP 429 (sdk-core ADR-0033); 500 calls a day, which the client does not count: `policy`, a `QuotaPolicy`, holds keyed calls back once upstream answers that the quota is spent (`_client.py`, sdk-core ADR-0037) |
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
  every 1.5 s, never a burst, under the limit upstream documents (sdk-core ADR-0033
  decision 1: 1 a second and 60 a minute documented, 40 a minute chosen after the recorded
  429s, as https://github.com/xippios/sdk-comtrade/pull/4 decided). Core retries a 429 after
  `Retry-After`, each retry a call, and `policy` holds the next keyed call back until then.
  Offline tests skip the wait (core's plugin); a test marked `rate_limited` keeps it.
- **500 calls per day.** `countOnly` calls count against it, so `get_data` costs two
  calls (count, then data) and `get_counts` one. The client does not count calls. Over
  the quota API Management answers 403 "Out of call volume quota. Quota will be
  replenished in HH:MM:SS"; `classify` maps a 403 that mentions a quota to
  `RateLimitError` with `retry_after`, and `policy`, `QuotaPolicy(limit_header=None,
  remaining_header=None, window=86400, spent=...)` installed on `config`, marks the quota
  spent until then: the next keyed call is refused with `RateLimitError` before it is sent
  (a wait within 30 s is waited out). It reads no `x-ratelimit-*` header, since those
  describe the per-second pace. Its `spent` hook reads two answers, this 403, whose time
  `window` caps at a day, and a 429 without `Retry-After`, for the "Try again in N
  seconds" of its body or else 1 s, so a pace refusal never holds calls back for the
  day-long `window`. The 403 has not been observed; never provoke it.
- **100,000 records per call.** Above it upstream answers HTTP 200 with the first
  100,000 rows, `count` 100000 and an empty `error`: it truncates silently (observed
  2026-10-23 for a query counted at 5,006,385). `get_data` counts first by core's
  `fetch_counted`, raises core's `QueryTooLarge` before any data call and sets the count as
  `meta.total`.
- **12 periods per call.** A 13th gets HTTP 400 "Maximum number of periods is 12";
  `params.validate_get` refuses it before the call. `tools/v1/getTradeBalance` answers the
  same; `data/v1/getDa` and `tools/v1/getBilateralData` take more.
- **Slow counts.** A broad count can take over a minute, so the read timeout is 180 s
  (`READ_TIMEOUT`), and a timed-out attempt that core retries counts against the quota each
  time; so does each retry of a 5xx.
- **Keys may be periodically regenerated** on Basic accounts. A sudden 401 ("Access
  denied due to invalid subscription key", `AuthError`) means re-copying the key from
  https://comtradeplus.un.org/MyComtrade/APIPortal into the environment.

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
wrappers are named after the paths (conventions §2). What the keyless recordings of
2026-10-28 established (`tests/fixtures/get_comtrade_releases/`, `get_world_share/`):

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
`partnerAreas.json`; so is a `customs_code` or `mot_code` the packaged `customsCode` or
`motCode` list lacks, where upstream's answer is not recorded. Each is checked by core's
`check` of its list's declaration in `codes.py`, once for the codes given, and each
refusal says that nothing was sent. The other lists (`clCode` and
`flowCode`, which upstream refuses with HTTP 400, and the spec's `typeCode`, `freqCode`,
`breakdownMode`, `aggregateBy`) keep one `InvalidRequestError` naming every problem
found; the first unknown code ends the checks, so other problems show once it is fixed.
Both tables share one code space (a code in both is the same area) but differ: 0 World
and 55 other areas are partners only, 97 European Union and 975 ASEAN reporters only.

The packaged lists carry upstream's words beside each value, under upstream's names, as
`scripts/refresh_reference.py` fetched them (2026-11-20, keyless): `text` from
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

`MCP_CAPS` in `tasks.py` gives four tasks result caps of their own (sdk-core ADR-0038),
each 400 rows or 100 KB: three list tasks and `get_world_share`. `list_reporters` (256
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
always send a placeholder key, whatever the shell holds: core's plugin pins it, for each
secret variable of `_client.ENV_VARS`.

What the recorded answers established (2026-10-23). The fixtures are named in
`reference/clCode.json` and `flowCode.json`, in the docstrings of the `getDa`,
`getMetadata` and `getLiveUpdate` wrappers, and, for the `data/v1/get` behaviours, in
`tests/test_tasks.py` and the description of https://github.com/xippios/sdk-comtrade/pull/4:

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
on 2026-10-28 under `tests/fixtures/get_trade_balance/` and `get_bilateral_data/`,
Switzerland and `TOTAL`. Both answered the package's key; the spec's 403 for a free-tier key
not on getTradeBalance's allow-list ("User not allowed", `AuthError` by core's mapping) did
not occur, and no other 403 was seen. `countOnly`, not in the spec, counts nothing:
getTradeBalance answers `count` 0 and a placeholder for a query of 48 rows, getBilateralData
ignores it; so the tasks count nothing first and require `reporter_code` or `partner_code`,
and `cmd_code`. getTradeBalance without `breakdownMode` answers every breakdown (48 rows
with the World in 2023), `classic` the total row; it refuses a 13th period. getBilateralData
takes 13 periods and one `flowCode` (only `X` was recorded, `M` is the spec's other value;
`M,X`: HTTP 400, its detail's message spelt `ErrorMessage`, which `classify` reads), fills
no description with `includeDesc`, and answers in classic mode (`customsCode` C00, `motCode`
0). Its mirror columns are, per the Help Center, the partners' reported imports for a
reporter's exports, and "depend on the availability of other reporters rather than
no-trade": for Switzerland's 2023 exports Afghanistan's mirror is 0, and it is inferred, not
stated, to be one of the two partners the note counts with a data gap (DPRK alone: 1, the
USA alone: none). `primaryValueDisc` equals (mirror − value) / value in every recorded row
and `mirror2*` is empty or 0; upstream states neither meaning. Its envelope's
`timestampRequested` is UTC per the spec and its `note` counts the partners with a data gap
and their share of world trade, naming none, in wording that varies; the task returns both
with the rows as one `BilateralData` (`note`, `timestamp_requested`, `data`), not a list, so
the note that qualifies the mirror values reaches the agent, as
https://github.com/xippios/sdk-comtrade/pull/11 decided. Over MCP, core's result cap cuts
its rows: an answer above 64 KB (about 40 rows) keeps its `note` and `timestamp_requested`
whole beside the rows that fit, with the cap's note.

No MCP tool is paged. The client keeps core's bound of 8 MiB a body, `cache_max_bytes`,
and an answer of `get_data` can pass it, 100,000 rows of about 900 bytes, the size of a
recorded row; about 15,600 rows of `getDa` and 6,000 of `getBilateralData` pass it too, by
the sizes of their recorded rows, and the package bounds neither answer under that. A
continuation past the bound would fetch the whole answer again, a keyed call of the daily
500, and for `get_data` its count too, so `get_data`, `get_data_availability` and
`get_bilateral_data` stay unpaged, as conventions §8 leave a tool whose answer can pass the
bound (sdk-core ADR-0061, decision 9).

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
