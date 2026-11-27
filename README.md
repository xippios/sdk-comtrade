# xippios-comtrade

Typed Python client, MCP server and FastAPI routes for
[UN Comtrade](https://comtradeplus.un.org), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries its metadata (source, endpoint,
retrieved_at, request).

## Install

```bash
uv add xippios-comtrade            # client only
uv add "xippios-comtrade[mcp]"     # + MCP server
uv add "xippios-comtrade[http]"    # + FastAPI router
```

Set `COMTRADE_API_KEY` in the environment. Nothing is read from files. The public
operations (`get_comtrade_releases`, `get_world_share`) and the reference files need no
key and send none.

## 30-second example

```python
from xippios.comtrade import get_counts, get_data

# Switzerland (reporter 757) exports to the World (partner 0) in 2023, all products.
query = {
    "reporter_code": "757",
    "partner_code": "0",
    "period": "2023",
    "cmd_code": "TOTAL",
    "flow_code": "X",
}
get_counts("C", "A", "HS", **query).data  # 32: every customs procedure and mode of transport
result = get_data("C", "A", "HS", **query)
total = next(r for r in result.data if (r.customs_code, r.mot_code) == ("C00", 0))
total.primary_value  # Decimal('419922543423.509'); JSON: a number
result.meta.endpoint, result.meta.request  # 'data/v1/get', the arguments above
```

Parameters are upstream's (`typeCode`, `reporterCode`, ...) in snake_case and take
upstream's codes, several of them comma-separated as upstream takes them (`"757,842"`).
Reporter and partner codes are UN Comtrade's, not ISO numeric: Switzerland is 757.
Every argument is checked before the call: coded ones (`type_code`, `cl_code`,
`flow_code`, `customs_code`, `mot_code`, `aggregate_by`, `breakdown_mode`) against
the lists packaged from upstream's reference files and spec (`list_codes` gives each value
with upstream's words for it),
`reporter_code` against the packaged copy of upstream's `Reporters.json`
(`reference/Reporters.json`) and `partner_code` and `partner2_code` against that of
`partnerAreas.json`, the others by shape. An unknown area, customs or transport code
raises `UnknownCode`, an `InvalidRequestError` naming the packaged list, its fetch date
and the closest code (`756` names `757`, Switzerland; `C16` names `C15`, Relief
consignments); any other mistake raises `InvalidRequestError` naming the closest valid
value. Each refusal before a request says that nothing was sent. Every answer names the
reporter, partner, customs, transport, supply, unit and frequency codes of its rows in
`meta.names`, by the packaged lists.

```python
from xippios.comtrade import (
    list_classifications,
    list_codes,
    list_commodities,
    list_partners,
    list_reporters,
)

list_reporters().data  # 256 reporters, packaged with this version: no call
list_reporters(search="switz").data  # code, ISO alpha-3 or name, any case: 757
list_partners().data  # 310 partner areas, 0 World among them
list_commodities("HS", search="coffee").data  # from 8,262 HS codes, fetched keyless once
list_codes("motCode").data[3]  # MotCodeValue(mot_code='2100', text='Sea'): packaged
list_classifications("cmd:H6").data[0].variable  # 'Product [HS 2022]': upstream's index
```

Release dates are per dataset, so they sit on the rows, not in `meta.published_at`.
Upstream prints `first_released`, `last_released`, `publication_date` and `date_release`
without a zone, so they are naive datetimes:

```python
from xippios.comtrade import (
    get_comtrade_releases,
    get_data_availability,
    get_live_update,
    get_metadata,
    get_world_share,
)

[dataset] = get_data_availability("C", "A", "HS", reporter_code="757", period="2023").data
dataset.first_released, dataset.last_released  # first publication and latest revision
notes = get_metadata("C", "A", "HS", reporter_code="757", period="2023").data[0].notes
[note.publication_date for note in notes]  # "New Data", then each "Revised Data"
get_live_update().data  # the 50 most recent releases, newest first
get_comtrade_releases().data  # upstream's recent releases (newest first when recorded); keyless
[share] = get_world_share("C", "A", period="2023", reporter_code="757").data  # keyless
share.world_share, share.last_released  # Decimal('0.01651852126450239'), its release
```

Two Tools operations, which upstream's spec marks "EXPERIMENTAL - USE SPARINGLY", put
exports beside imports and a reporter's figures beside its partners' mirror figures:

```python
from xippios.comtrade import get_bilateral_data, get_trade_balance

ch = {"reporter_code": "757", "period": "2023", "cmd_code": "TOTAL"}
[row] = get_trade_balance("C", "A", "HS", partner_code="0", breakdown_mode="classic", **ch).data
row.primary_value_x, row.primary_value_m  # Switzerland's 2023 exports and imports
row.primary_value_bal  # upstream's "X - M", as sent
bilateral = get_bilateral_data("C", "A", "HS", partner_code="842", flow_code="X", **ch).data
bilateral.note  # upstream's data-gap note: 'EXPERIMENTAL: We have good news! ...'
[row] = bilateral.data
row.primary_value, row.mirror_primary_value  # exports to the USA; the USA's imports
```

Both need `reporter_code` or `partner_code`, and `cmd_code`, since upstream offers no
count to check a query's size first. A mirror of 0 is no sign of no trade: the mirror
depends on whether the partner reported. So `get_bilateral_data` returns upstream's
`note`, which counts the partners with a data gap without naming them, and its
`timestamp_requested`, with the rows: its `data` is one `BilateralData`, not a list.

`get_data` counts first with upstream's `countOnly`: a count of zero returns an empty
result without a second call, and a count above 100,000 raises core's `QueryTooLarge`
(`xippios.core.QueryTooLarge`) with the count before any data is fetched, because upstream
would cut the answer at 100,000 rows without saying so; `meta.total` is the count. The
client keeps the reference files for the life of the process and the keyed answers for
five minutes, so a repeated call spends no call of the daily quota. A free key allows 1
call per second and 500 calls per day, and `countOnly` calls count; the client spaces
calls 1.5 s apart (upstream's gateway refuses some calls spaced exactly 1 s apart) and
counts no calls, so the daily quota is yours to track: once upstream answers that it is
spent, the client sends no keyed call until the time upstream names and raises
`RateLimitError` instead, while the keyless operations and reference files, which spend
none of it, go on.

## MCP

```json
{
  "mcpServers": {
    "comtrade": {
      "command": "uvx",
      "args": ["--from", "xippios-comtrade[mcp]", "xippios-comtrade-mcp"],
      "env": { "COMTRADE_API_KEY": "..." }
    }
  }
}
```

Tools are read-only and named `comtrade_<verb>_<noun>`. Results are capped at
200 rows or 64 KB with a note on how to narrow the query; `comtrade_list_reporters` and
`comtrade_list_partners` have a cap of their own, 400 rows or 100 KB, so their whole
tables reach the agent. `comtrade_list_commodities` has the same cap, but a
classification is larger (8,262 HS codes), so its note says to search. All three take
`search`: `{"search": "switz"}` returns 757 Switzerland. `comtrade_get_world_share` has the
same cap too, so one period for every reporter (214 rows for 2023) reaches the agent
whole; its note says to narrow by `reporter_code` or `period`. `--http` serves streamable
HTTP instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `data/v1/get/{typeCode}/{freqCode}/{clCode}` with `countOnly=true` | `get_counts(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, ...)` | `comtrade_get_counts` | alpha |
| `data/v1/get/{typeCode}/{freqCode}/{clCode}` | `get_data(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, ...)` | `comtrade_get_data` | alpha |
| `data/v1/getDa/{typeCode}/{freqCode}/{clCode}` | `get_data_availability(type_code, freq_code, cl_code, *, reporter_code=, period=, published_date_from=, published_date_to=)` | `comtrade_get_data_availability` | alpha |
| `data/v1/getMetadata/{typeCode}/{freqCode}/{clCode}` | `get_metadata(type_code, freq_code, cl_code, *, reporter_code=, period=)` | `comtrade_get_metadata` | alpha |
| `data/v1/getLiveUpdate` | `get_live_update()` | `comtrade_get_live_update` | alpha |
| `public/v1/getComtradeReleases`, keyless | `get_comtrade_releases()` | `comtrade_get_comtrade_releases` | alpha |
| `public/v1/getWorldShare/{typeCode}/{freqCode}`, keyless | `get_world_share(type_code, freq_code, *, period=None, reporter_code=None)` | `comtrade_get_world_share` | alpha |
| `tools/v1/getTradeBalance/{typeCode}/{freqCode}/{clCode}` | `get_trade_balance(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, cmd_code=, ...)` | `comtrade_get_trade_balance` | alpha; experimental upstream |
| `tools/v1/getBilateralData/{typeCode}/{freqCode}/{clCode}` | `get_bilateral_data(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, cmd_code=, flow_code=, ...)`, returns `BilateralData` (`note`, `timestamp_requested`, the rows as `data`) | `comtrade_get_bilateral_data` | alpha; experimental upstream |
| `files/v1/app/reference/Reporters.json`, packaged | `list_reporters(search=None)` | `comtrade_list_reporters` | alpha |
| `files/v1/app/reference/partnerAreas.json`, packaged | `list_partners(search=None)` | `comtrade_list_partners` | alpha |
| `files/v1/app/reference/{clCode}.json`, keyless | `list_commodities(cl_code, search=None)` | `comtrade_list_commodities` | alpha |
| `files/v1/app/reference/` code lists and the spec's enums, packaged | `list_codes(param)` | `comtrade_list_codes` | alpha |
| `files/v1/app/reference/ListofReferences.json`, packaged | `list_classifications(category=None)` | `comtrade_list_classifications` | alpha |

The package covers these fourteen tasks and requires xippios-core 0.5.x (`~=0.5.0`); 0.3.0
does not work with core 0.5.0. The slices `get_bilateral_flows`, `get_world_trade` and
`get_mirror_flows`, the ranking `get_top_partners` and `get_commodity_series`, which 0.3.0
served, left after it: a task of a source fixes no filter, sort, rank or cut for the
caller, and `get_data` and `get_bilateral_data` answer the same rows with the arguments
that those five fixed. Alpha: the public surface may change in a minor version before
1.0; `CHANGELOG.md` lists every change.

## Upstream terms and attribution

Data comes from UN Comtrade (https://comtradeplus.un.org), on the terms upstream states
for it in its [Policy on Comtrade Data Use](https://uncomtrade.org/docs/policy-on-comtrade-data-use/),
under which use of the data is subject to the license agreement at
https://comtrade.un.org/licenseagreement.html; this package adds no rights to it.
Documentation snapshot and its attribution: `docs/upstream/FETCHED.md`.

## Workflows

`ci.yml` runs ruff, its format check, mypy, pytest and pre-commit on Python 3.12, 3.13 and
3.14, requires a changelog entry of every pull request but Dependabot's and refuses a
fixture file over 256 KiB that a pull request adds or changes. It runs on every pull request and,
called by `publish.yml`, once for a release, and its job `ci` is the check the
organization's ruleset requires. It is handed no secret, and no variable switches it off.

`publish.yml` is the release train (conventions §12): on a push to `main` whose
`pyproject.toml` names a version that has no tag yet and has its section in `CHANGELOG.md`,
it runs `ci.yml`, refuses a core pinned to git, tags the merge commit, builds the package
and, once a reviewer of the environment `pypi` approves the run, publishes it to PyPI by
trusted publishing. Every push to `main` and a dispatch start it, and a push that brings no
release ends quietly. It is handed no secret: the step that tells a release is handed the
job's token as `GH_TOKEN`, the tag goes with the job's token and PyPI trusts the workflow
itself. Its job `tag` holds the one checkout of the repository that keeps its credentials,
since it pushes the tag with the job's token; every other checkout sets
`persist-credentials: false` (conventions §13). No variable switches it off.

`live.yml` runs every `live` test against the upstream with `--tb=short --assert=plain`, so
its public log holds neither a failing test's arguments nor the values an assertion compared.
It runs every night at 05:31 UTC and on demand, never on a pull request.
Its pytest step alone is handed `XIPPIOS_LIVE_TESTS` and, each from the secret of the same
name, `COMTRADE_API_KEY`, so the checkout, setup-uv and `uv sync` see none.
A variable `WORKFLOW_LIVE` of `off`, the repository's over the organization's, switches it off.

`conventions.yml` calls the organization's review of a pull request against the documents
listed under Documents below, the check `conventions / conventions`, when a pull request
opens, is pushed to, reopens or is edited, and on a push to `main` or a dispatch the review
of the range of commits, `range / range`. It hands the review the organization's
secret of the model's key, by name. A variable `WORKFLOW_CONVENTIONS` of `off`, the
repository's over the organization's, switches both off.

`adr-index.yml` calls the organization's check of the ADR index, `adr-index / adr-index`,
which runs `scripts/adr_index.py --check`, when a pull request opens, is pushed to or
reopens. It hands over nothing, and the called workflow reads its switch itself: a variable
`WORKFLOW_ADR_INDEX` of `off`, the repository's over the organization's, skips the check.

## Documents

- sdk-core: [docs/conventions.md](https://github.com/xippios/sdk-core/blob/main/docs/conventions.md) — the conventions every xippios source package follows: its layout, names, results, tests and releases.
- sdk-core: [docs/adr.md](https://github.com/xippios/sdk-core/blob/main/docs/adr.md) — the index of the family's architecture decisions, which the conventions cite.
- sdk-core: [docs/definition-of-done.md](https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md) — what a change satisfies before its pull request is opened.
- sdk-core: [docs/review-checklist.md](https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md) — what the review of a pull request checks, in order.
- sdk-comtrade: [docs/adr.md](https://github.com/xippios/sdk-comtrade/blob/main/docs/adr.md) — the index of this package's own decisions, generated from the records in `docs/adr/`.
- sdk-comtrade: [docs/upstream/FETCHED.md](https://github.com/xippios/sdk-comtrade/blob/main/docs/upstream/FETCHED.md) — the snapshot of the upstream documentation, the reference for names, parameters and semantics.

## Licence

Apache-2.0. See [LICENSE](https://github.com/xippios/sdk-comtrade/blob/main/LICENSE).
