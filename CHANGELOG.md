# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [0.4.0] - 2026-11-28

### Added

- The README's `## Scope` names each of the 29 operations of UN Comtrade's five API
  products, the twenty-one that no task wraps yet each with its public issue, and each
  documented choice that a caller cannot make. What UN Comtrade was observed to answer
  stands once in `docs/upstream/OBSERVED.md`, each note with its probe, its date and its
  recording. (https://github.com/xippios/sdk-comtrade/issues/33,
  https://github.com/xippios/sdk-comtrade/issues/63)
- Every answer names in `meta.names` the reporter, partner, flow, customs, transport and
  frequency codes that the call asked for, by the packaged lists, so an answer without rows
  names what the call asked for. The rows' flow codes are named too, `MIF` and `XIF`, which
  the package adds from the spec without upstream's words, by their own code.
  (sdk-core ADR-0067, https://github.com/xippios/sdk-comtrade/issues/66)
- An answer of `get_data` after a count of 0 says in `meta.notes` that UN Comtrade counted no
  record for the query and that no data request was sent, since a code that UN Comtrade does
  not have counts 0 too. (https://github.com/xippios/sdk-usda-esr/issues/88)
- Every answer whose rows carry a reporter, partner, customs, transport, supply, quantity
  unit or frequency code names those codes in `meta.names` by the packaged lists. A code
  that its list lacks is left out of the names and said in `meta.notes`, so no answer is
  withheld for it. (sdk-core ADR-0067, https://github.com/xippios/sdk-core/issues/478)

### Changed

- Every list and table packaged from UN Comtrade's reference files is the one fetched on
  2026-11-27, the day that `meta.retrieved_at` of the list tasks and the fetch date of an
  `UnknownCode` refusal give, while the three lists read from the spec carry the time of its
  snapshot. No code left or joined any list or table, and no record changed but the words of
  `freqCode` and `typeCode`. (https://github.com/xippios/sdk-comtrade/issues/68)
- A refusal of a call as given names the first problem that it finds, in the order of the
  arguments, where it named every problem found. Core's check judges every packaged list, so
  an unknown `type_code`, `freq_code`, `cl_code`, `flow_code`, `aggregate_by`,
  `breakdown_mode` or `category` raises `UnknownCode`, an `InvalidRequestError` that names
  the closest codes by core's `closest`. An area code without the same area in the other
  table names the nearest codes by number, by core's `nearest`.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-comtrade/issues/34)
- The description of `get_data` and of its tool states the most that one call sends: two
  requests, the count and the data, each tried at most 4 times, so at most 8.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-comtrade/issues/66)
- The client keeps the keyed answers under `data/v1` and `tools/v1` for 300 s beside the
  reference files, which it keeps for the life of the process, each by the longest path
  prefix that its path starts with. A call repeated within five minutes is answered from the
  cache and spends no call of the daily quota, while the public operations under
  `public/v1` stay out of it. (https://github.com/xippios/sdk-core/issues/479)
- A decimal without fractional digits is a JSON integer in the answers of the MCP tools and
  the routes, `16217` where it read `16217.0`.
  (https://github.com/xippios/sdk-core/issues/478)
- `get_data` refuses a query over UN Comtrade's limit of 100,000 records per call with
  core's `QueryTooLarge`, whose message gives the count, the limit, that the count was sent
  and no data fetched, and what narrows the query. It still answers a count of 0 with an
  empty list and no data request, and its answer carries the count as `meta.total`.
  (https://github.com/xippios/sdk-comtrade/issues/38)
- Every refusal of a call as given says `Nothing was sent.` after its first sentence, the MCP
  adapter's refusal of an argument among them, while a refusal after a request says what
  was sent. An area, customs or transport code is checked by one call of core's check, and
  the refusal of an area names the integer, `756` where it read `'756'`, with the classes
  unchanged. (https://github.com/xippios/sdk-core/issues/481)
- `meta.retrieved_at` of each task that reads UN Comtrade is the client's time of the answer,
  the time it was stored where the cache answers. `get_data` takes the older of its count
  and its data request. (sdk-core ADR-0037, https://github.com/xippios/sdk-core/issues/479)
- The descriptions of `comtrade_get_data`, `comtrade_get_trade_balance`,
  `comtrade_get_bilateral_data`, `comtrade_get_comtrade_releases`, `comtrade_get_world_share`
  and `comtrade_list_codes` are each task's docstring before `Args:`, under 1,000
  characters. The text of each argument stands in the tool's input schema.
  (https://github.com/xippios/sdk-core/issues/485)

### Fixed

- The package's links to UN Comtrade, the `Upstream` URL of its PyPI page and the README's,
  name the site on its new host, `comtrade.un.org`, in place of `comtradeplus.un.org`.
  (https://github.com/xippios/sdk-comtrade/issues/77)
- `docs/upstream/FETCHED.md` lists under `Not fetched` the document that the documentation
  page's console loads, the data availability API and My API Portal, each with the reason
  that the snapshot does not request it. (https://github.com/xippios/sdk-comtrade/issues/80)

### Breaking

- `TypeCodeValue` loses `text`, and `list_codes("typeCode")` answers `C` and `S` without
  words, since UN Comtrade lists no reference file of `typeCode` and a label comes from
  upstream's own list. The words of `freqCode`, in `list_codes("freqCode")` and in
  `meta.names`, are those of UN Comtrade's `Frequency.json`, `Annual` and `Monthly`, in place
  of `annual` and `monthly` cut from the spec's description, and `FreqCodeValue.text` is
  always set. The file's row `Q` Quarterly, which the `freqCode` of no API document
  takes, stays refused before any request.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-comtrade/issues/68)
- `get_counts` becomes `count_data`, its MCP tool `comtrade_count_data` and its route
  `/comtrade/count_data`, with no alias: `count_` is the family's verb for upstream's own
  count. `list_codes(param)` keeps its name.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-comtrade/issues/66)
- `get_live_update` reads its four times strictly: an answer with a time that none of its
  four forms reads fails with core's `ValidationError`, which names `data/v1/getLiveUpdate`,
  where that time read as `None`. A time that UN Comtrade sends as null stays `None`.
  (https://github.com/xippios/sdk-usda-esr/issues/60)
- `search` of `list_reporters`, `list_partners` and `list_commodities` and `category` of
  `list_classifications` are keyword-only, so `list_classifications("cmd:HS")` becomes
  `list_classifications(category="cmd:HS")`. The keyword-only arguments of every task stand
  in the spec's one order, `reporter_code`, `period`, `partner_code`, `partner2_code`,
  `cmd_code`, `flow_code`, `customs_code` and `mot_code` before the rest, which orders the
  tools' input schemas so and breaks no call by name.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-usda-esr/issues/60)
- Several values of a filter are one argument that takes one code or a list of codes,
  `reporter_code=[757, 842]`, which the package sends as UN Comtrade's comma-separated text,
  and a comma-separated text such as `"757,842"` or a set is refused before any request. It
  holds for `reporter_code`, `period`, `partner_code`, `partner2_code`, `cmd_code`,
  `flow_code`, `customs_code`, `mot_code` and `aggregate_by`, while `flow_code` of
  `get_bilateral_data` stays one value. Over MCP each takes a JSON array, and over HTTP the
  routes of `count_data`, `get_data`, `get_data_availability`, `get_metadata`,
  `get_trade_balance`, `get_bilateral_data` and `get_world_share` take a `POST` with a JSON
  body, where a `GET` with a query now gets HTTP 405.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-comtrade/issues/66)
- The package depends on `xippios-core~=0.5.0`, its extras likewise, is updated to
  sdk-template v0.5.0 and applies conventions 1.30.
  (https://github.com/xippios/sdk-comtrade/issues/63)
- `xippios.comtrade.errors` holds no `QueryTooLarge` of its own any more, so an import of it
  fails. A caller catches core's `xippios.core.QueryTooLarge`, which `get_data` raises, an
  `InvalidRequestError` with the count and the limit as before.
  (https://github.com/xippios/sdk-comtrade/issues/38)
- The endpoint wrappers of `xippios.comtrade.api` return core's `Answer`, the model of
  upstream's answer as its `payload` beside its `retrieved_at`, where they returned the
  model itself. A caller of a wrapper reads `.payload`.
  (sdk-core ADR-0037, https://github.com/xippios/sdk-core/issues/479)
- `xippios.comtrade.enums`, the ten `StrEnum` classes generated from the packaged lists,
  leaves the package, and `scripts/refresh_reference.py` no longer renders it: its
  `--render-only` writes the provenance rows alone. No module of the package imported it, and
  a task takes a code as a plain text all the same. `list_codes` returns each packaged list
  with upstream's words where upstream's list gives them.
  (https://github.com/xippios/sdk-comtrade/issues/64)
- `get_bilateral_flows`, its MCP tool `comtrade_get_bilateral_flows` and its route leave the
  package: the task fixed goods, the total row and the descriptions for the caller, which a
  task of a source does not. `get_data` answers the same rows, in upstream's order, with
  `type_code` `"C"`, `breakdown_mode="classic"` and `include_desc=True`, the reporter and the
  partner as UN Comtrade's codes. (sdk-core ADR-0060,
  https://github.com/xippios/sdk-core/issues/474)
- `get_commodity_series`, its MCP tool `comtrade_get_commodity_series` and its route leave
  the package: the task fixed goods, partner 0 and the total row for the caller and sent at
  most 120 periods, 12 a call. `get_data` answers each 12 periods with `type_code` `"C"`,
  `partner_code="0"`, `breakdown_mode="classic"` and `include_desc=True`, and a series of
  `get_data` over more than 12 periods waits for a later release. (sdk-core ADR-0060,
  https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-comtrade/issues/36)
- `get_mirror_flows`, its MCP tool `comtrade_get_mirror_flows` and its route leave the
  package: the task fixed goods for the caller and cut `getBilateralData` to single product
  codes and 12 periods. `get_bilateral_data` answers the same operation with every argument
  that the caller sets, its rows with every field upstream sends beside upstream's note.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474)
- `get_top_partners`, its MCP tool `comtrade_get_top_partners` and its route leave the
  package: the task ranked a reporter's partners by `primary_value`, dropped partner 0, the
  World, and kept the first `n`, a ranking that a task of a source does not make.
  `get_data` without `partner_code` answers every partner's row, the World's among them,
  with `type_code` `"C"`, `breakdown_mode="classic"` and `include_desc=True`.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474)
- `get_world_trade`, its MCP tool `comtrade_get_world_trade` and its route leave the
  package: the task fixed goods, partner 0 and the total row for the caller and sorted the
  reporters by `primary_value`. `get_data` without `reporter_code` answers the same rows, in
  upstream's order, with `type_code` `"C"`, `partner_code="0"`, `breakdown_mode="classic"`
  and `include_desc=True`. (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474)
- `models.TradeFlowRecord`, `MirrorFlowRecord` and `MirrorFlows` leave with the tasks that
  returned them, and `params.SLICE_PINS`, `MAX_SERIES_PERIODS`, `validate_slice` and
  `validate_mirror_flows` with the tasks that read them. `TradeDataRecord` and
  `BilateralData` hold the rows of the two operations. No task resolves an ISO alpha-3 code
  any more: every area argument takes UN Comtrade's code, which `list_reporters` and
  `list_partners` find by its alpha-3 code. (sdk-core ADR-0060,
  https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-comtrade/issues/37)

## [0.3.0] - 2026-11-20

### Added

- `xippios.comtrade.mcp` exports `build()`, which returns the tool set of xippios-core's
  package contract, `server`, built from it, and `ENV_VARS`, the variables the package
  reads: `COMTRADE_API_KEY`, a secret the data operations need. So a host serves the
  nineteen tools as `xippios-comtrade-mcp` does.
  (https://github.com/xippios/sdk-core/issues/245)

### Changed

- Every list and table packaged from UN Comtrade's reference files is the one fetched on
  2026-11-20: `meta.retrieved_at` of `list_reporters`, `list_partners`, `list_classifications`
  and of `list_codes` for the six lists drawn from those files gives that day, and so does the
  fetch date an `UnknownCode` refusal names, while the four lists read from the spec keep
  theirs. `Reporters.json` adds `238` Falkland Isds (Malvinas): `list_reporters` answers 256
  reporters, where it answered 255, `reporter_code` takes `238`, and the slices' `reporter`
  takes `238` or `FLK`, where both refused the area as a partner code only. `list_partners`
  gives `756` Switzerland without the trailing space upstream had sent in `text` and
  `partner_desc`, so an exact comparison or a `search` with that space no longer finds it; no
  code left any list or table, and every other record is unchanged.
  (https://github.com/xippios/sdk-comtrade/issues/54)
- `CLAUDE.md`, the comment above `RATE_LIMIT` in `_client.py` and the docstring of
  `_MIRROR_TOO_MANY` in `params.py` cite the pace of 40 calls a minute, the shape of
  `BilateralData` and the mirror slice's 12 periods by the pull requests that took them,
  where they gave internal decision numbers or a first name and a date. `CLAUDE.md` names
  the pull request whose description lists the fixtures of `data/v1/get`, and calls the
  slices by that name alone. (https://github.com/xippios/sdk-comtrade/issues/19)
- `xippios-comtrade-mcp` names itself in the usage line of `--help` and in the prefix of
  an option error, `xippios-comtrade-mcp: error: unrecognized arguments: --nope`, where both
  read `xippios-comtrade`, and the help of `--allow-remote` says that it changes nothing on
  this read server. (https://github.com/xippios/sdk-core/issues/167)
- `get_comtrade_releases`, `get_world_share` and `list_commodities` go out once the key's
  daily quota is spent, at the 1.5 s pace, where the client held them back with the keyed
  calls until upstream's replenish time: they send no key and spend none of the quota, and
  their answers no longer mark it spent. (https://github.com/xippios/sdk-core/issues/163)
- A tool's error answer sets `isError` on its result beside the text
  `error: <ErrorClass>: <message>`, the refusal of reporter `756` or of an unknown
  `list_codes` list among them, so a client tells a refusal from data without reading the
  text. (https://github.com/xippios/sdk-core/issues/168)
- Over MCP, an answer of `comtrade_get_bilateral_data` or `comtrade_get_mirror_flows` above
  its 64 KB cap keeps its `note` on the data gap and its `timestamp_requested` whole beside
  the rows that fit, with the cap's note, where the whole answer became a note and a text
  preview. (https://github.com/xippios/sdk-core/issues/131)
- A refusal that names another task, the one to call instead or the list task of the known
  codes, names that task's MCP tool too: `list_reporters lists every code (over MCP, the
  tool comtrade_list_reporters).`, and so for `list_partners`, `list_codes`, `get_counts` in
  `QueryTooLarge`'s advice, `get_data`, `get_commodity_series` and `get_bilateral_data`.
  (https://github.com/xippios/sdk-core/issues/111)
- A route answers an argument that its schema refuses, an `n` of `get_top_partners` that is
  no integer say, or one that is missing, as problem details before the task runs: HTTP 422,
  `application/problem+json`, the title `InvalidRequestError` and the detail
  `n: Input should be a valid integer, unable to parse string as an integer`, where
  FastAPI's own 422 listed its error details with the value sent.
  (https://github.com/xippios/sdk-core/issues/66)
- The refusal of an area, customs or transport code that the packaged list lacks, such as
  reporter `756`, ends with `If upstream added it since, the packaged list is out of date.`,
  where it named the maintainers' `/refresh-reference-data`, which an agent cannot run.
  (https://github.com/xippios/sdk-core/issues/111)
- Adopts sdk-template v0.3.4, from v0.3.1, with conventions 1.27 and no new core minor: the
  floor stays `xippios-core~=0.3.0`. The README lists the package's documents under
  `## Documents`, and `CLAUDE.md` holds the rules that `.claude/family.md` carried, which
  leaves with `/adopt-release`. Changelog entries are fragments under `changelog/`, the
  package's own decisions go into `docs/adr/` with the index `scripts/adr_index.py` writes,
  and a pull request runs the organization's checks from `organization.yml`, where
  `gates.yml` was, on its opening, a push, a reopening and an edit.
  (https://github.com/xippios/sdk-template/releases/tag/v0.3.4,
  https://github.com/xippios/sdk-comtrade/issues/18)
- Adopted sdk-template v0.3.1 (conventions §15), with no new core minor: the floor stays
  `xippios-core~=0.3.0`. `.github/CODEOWNERS` is rendered from the template's answers and
  names the code owner whom GitHub asks to review a change to `.github/`, `CLAUDE.md`,
  `.claude/`, `pyproject.toml` or `.copier-answers.yml`; `.gitignore` leaves copier's
  `*.rej` and `*.orig` out; `.claude/family.md`, `/adopt-release`, `/release-prep` and the
  PR template no longer have the author of a pull request merge it.

### Fixed

- The call of `list_commodities` that fetches a classification file reports the
  `meta.retrieved_at` that every later call answered from the cache reports, one reading
  of the clock, where the two were read apart and differed slightly.
  (https://github.com/xippios/sdk-core/issues/79)
- `list_commodities` asks upstream again for a classification file whose answer is no JSON
  or holds no `results`, where the cache kept that answer and the task failed with it for
  the life of the process. (https://github.com/xippios/sdk-core/issues/122)

### Breaking

- `xippios.comtrade.api.reference_rows` and `api.reference` return xippios-core's `Answer`:
  the rows are its `payload` and the time its `retrieved_at`, where they returned
  `api.ReferenceFile`, which is gone, with `rows` and unpacked as a pair.
  (https://github.com/xippios/sdk-core/issues/123)
- A tool refuses an argument that it does not declare before it runs, naming the ones it
  takes: `comtrade_list_codes` with `{"param": "motCode", "paramm": "x"}` answers
  `error: InvalidRequestError: paramm: Not an argument of this tool; it takes param`, where
  it dropped `paramm` and answered the transport codes.
  (https://github.com/xippios/sdk-core/issues/84)
- Adopts sdk-template v0.4.0, from v0.3.4, with `core_version=0.4.0`. The package depends
  on `xippios-core~=0.4.0`, its extras likewise, and follows conventions 1.28.
  (https://github.com/xippios/sdk-template/releases/tag/v0.4.0,
  https://github.com/xippios/sdk-comtrade/issues/50)

## [0.2.0] - 2026-10-28

xippios-comtrade 0.2.0 is released on xippios-core 0.3.0 and sdk-template v0.3.0, its new
floor: it depends on `xippios-core~=0.3.0`, and its `mcp`, `http` and `testing` extras
likewise. It adds seven tasks to the twelve of 0.1.0, each with its MCP tool and FastAPI
route: `get_trade_balance` and `get_bilateral_data` on UN Comtrade's two Tools
operations, which upstream marks experimental, and `get_mirror_flows`, a slice over the
second that puts a reporter's trade with one partner beside the partner's mirror of it;
`get_comtrade_releases` and `get_world_share` on the two public operations, which send no
key and spend no daily quota; and `list_codes` and `list_classifications`, two lookups
over the packaged lists that answer without a call and give each value with upstream's
words for it. The upstream documentation snapshot is refreshed with eight more Help
Center articles, among them the two that state the data's terms, and
`docs/upstream/FETCHED.md` quotes upstream's copyright and licence-agreement lines as the
attribution. The packaged lists and tables are all core's packaged lists now, JSON files
whose code lists carry upstream's words beside each value where upstream gives any, and
every one was refreshed on 2026-10-28, from upstream's reference files and the spec,
without a value or row changing. An unknown area, customs or transport code raises
`UnknownCode`, naming the packaged list, its fetch date and the closest code. The
client's quota policy reads upstream's answer that the day's 500 calls are spent and
refuses every further call with `RateLimitError`, unsent, until the time upstream names.
The area lists and `get_world_share` have an MCP result cap of their own, 400 rows or
100 KB, so a whole list, or one period for every reporter, reaches an agent;
`list_commodities` has the same cap and a note that says to search.

A minor release, since before 1.0 a breaking change bumps the minor: the new core bound
breaks, as core keeps no compatibility across minors while it is 0.x, and the public
surface grew. Code written against 0.1.0 meets more changes below, among them: the
packaged CSV tables and the `params` helpers that read them are gone, so is the separate
reference client, and the area lists' `meta.vintage` is `None` where it carried the
fetch date.

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
- `get_mirror_flows(reporter, partner, commodities, periods, flow, *, cl_code="HS")`,
  MCP tool `comtrade_get_mirror_flows`: a reporter's reported trade with one partner
  beside the partner's reported mirror of it, per product code and period, in one
  `tools/v1/getBilateralData` call for goods. Areas as codes or ISO alpha-3, single
  product codes, at most 12 periods of one format (the slices' bound; upstream answered
  13), flow `X` or `M`, checked before the call (`params.validate_mirror_flows`), the
  rows bounded by product codes times periods. It returns one `MirrorFlows`: upstream's
  `note` and `timestamp_requested` with the rows as `MirrorFlowRecord`, in upstream's
  order, the reported and mirror columns under upstream's names, nothing reordered or
  computed (`primary_value_disc` and `mirror2_primary_value` as sent). `includeDesc` is
  not sent: it filled no description. Recorded on 2026-10-28, Switzerland's chapter 27
  exports to the USA in 2022 and 2023 and in January 2023
  (`tests/fixtures/get_bilateral_data/ch_us_27_2022_2023_x.json`, `ch_us_27_202301_x.json`):
  chapter-level rows and `freqCode` M are answered, and the reported values equal
  `data/v1/get`'s for the pair.
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
- The two public operations, MCP tools `comtrade_get_comtrade_releases` and
  `comtrade_get_world_share`: `get_comtrade_releases()`, upstream's recent releases from
  `public/v1/getComtradeReleases` (38 from 2026-10-22 to 2026-10-28, newest first, when
  recorded), and `get_world_share(type_code, freq_code, *, period=None,
  reporter_code=None)`, each reporter's share of world trade per period from
  `public/v1/getWorldShare/{typeCode}/{freqCode}`, with its release times. Both are
  keyless, sending no key and spending no daily quota, while the client's pace and quota
  policy apply to them as to every call, and never cached. Rows are `ComtradeRelease` and
  `WorldShare`, every field under its upstream name; their times are naive datetimes, as
  upstream prints them without a zone, and `world_share` is a `Decimal`. `meta.total` is
  upstream's count and `meta.published_at` stays `None`. `params.validate_world_share`
  checks the arguments before the call: `period` as years, months or `recent`, which
  upstream answered with HTTP 500 when recorded, and `reporter_code` against
  `Reporters.json`, an unknown code raising `UnknownCode`. MCP: `get_world_share` has a
  result cap of its own, 400 rows or 100 KB, so one period for every reporter reaches an
  agent whole (`MCP_CAPS`).
- `classify`'s reading of `ErrorMessage` (above) covers getWorldShare's HTTP 400 as well
  (`get_world_share/period_malformed.json`), so its refusal names the field too.
- Two lookup tasks over the packaged lists, MCP tools `comtrade_list_codes` and
  `comtrade_list_classifications`, both answering without a call: `list_codes(param)`
  returns one list's records, the value under the parameter's name in snake_case with
  upstream's words for it (`TypeCodeValue`, `FreqCodeValue`, `ClCodeValue`,
  `FlowCodeValue`, `CustomsCodeValue`, `MotCodeValue`, `AggregateByValue`,
  `BreakdownModeValue`, `MosCodeValue`, `QtyUnitCodeValue`; the union `CodeValue`), a
  list the package does not carry raising `InvalidRequestError` naming the closest; and
  `list_classifications(category=None)` returns upstream's index of its reference files,
  `ListofReferences.json`, as `Reference` rows (`category`, `variable`, `description`,
  `fileuri`), filtered by category, an unknown one raising `InvalidRequestError` naming
  every category. `meta.retrieved_at` is the list's fetch time and `meta.vintage` `None`;
  both keep the default result cap (41 and 28 rows at most). `params.validate_code_list`
  and `params.validate_reference_category` check their arguments.

### Changed

- **BREAKING**: depends on `xippios-core~=0.3.0` and its `mcp`, `http` and `testing`
  extras likewise, from `>=0.1.0`.
- `list_reporters` and `list_partners`: `meta.retrieved_at` is when the package fetched
  the list and `meta.vintage` is `None`, where `vintage` carried the fetch date;
  `list_commodities`' `meta.retrieved_at` is when its file was fetched, the first fetch
  of the process on a later call.
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
- The packaged lists carry upstream's words beside each value, under upstream's names:
  `text` in `flowCode`, `customsCode`, `motCode` and `mosCode` from their reference
  files, `qtyAbbr` and `qtyDescription` in `qtyUnitCode`, `variable` and `description` in
  `clCode` from `ListofReferences.json`, and in `typeCode` and `freqCode` the spec's
  wording as `text`; a value added from the spec stands alone. `ListofReferences.json`
  is packaged as a table. `params.PACKAGED_LISTS` maps each list to the model of its
  records. `scripts/refresh_reference.py` refreshed every list and table on 2026-10-28,
  keyless: no value or row was added, removed or changed; `fetched` is each fetch's UTC
  time to the second, the answer's `retrieved_at` (2026-10-28T22:02:01Z to 22:02:14Z),
  the spec lists' the snapshot's time in `docs/upstream/FETCHED.md`
  (2026-10-28T14:38:34Z), and `enums.py`'s class docstrings name the new day.
- An unknown `customs_code` or `mot_code` names the closest codes with upstream's text
  (`C16`: `C15 (Relief consignments)`; `air`: `1000 (Air)`) and `list_codes` as the list
  of every code, where it named one closest code and every valid value.

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
