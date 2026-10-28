# xippios-comtrade

Typed Python client, MCP server and FastAPI routes for
[UN Comtrade](https://comtradeplus.un.org), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries release metadata (source, endpoint,
retrieved_at, published_at, vintage).

## Install

```bash
uv add xippios-comtrade            # client only
uv add "xippios-comtrade[mcp]"     # + MCP server
uv add "xippios-comtrade[http]"    # + FastAPI router
```

Set `COMTRADE_API_KEY` in the environment. Nothing is read from files.

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
the lists packaged from upstream's reference files and spec (`xippios.comtrade.enums`),
`reporter_code` against the packaged copy of upstream's `Reporters.json`
(`reference/Reporters.json`) and `partner_code` and `partner2_code` against that of
`partnerAreas.json`, the others by shape. An unknown area, customs or transport code
raises `UnknownCode`, an `InvalidRequestError` naming the packaged list, its fetch date
and the closest code (`756` names `757`, Switzerland); any other mistake raises
`InvalidRequestError` naming the closest valid value.

```python
from xippios.comtrade import list_commodities, list_partners, list_reporters

list_reporters().data  # 255 reporters, packaged with this version: no call
list_reporters(search="switz").data  # code, ISO alpha-3 or name, any case: 757
list_partners().data  # 310 partner areas, 0 World among them
list_commodities("HS", search="coffee").data  # from 8,262 HS codes, fetched keyless once
```

Four task-shaped slices answer the common questions in one call each (the series in one
call per 12 periods), at the total of every breakdown, one row per reporter × partner ×
product code × period. Areas are UN Comtrade's codes or ISO alpha-3 codes; `YYYY` periods
ask for annual data, `YYYYMM` for monthly:

```python
from xippios.comtrade import (
    get_bilateral_flows,
    get_commodity_series,
    get_top_partners,
    get_world_trade,
)

get_bilateral_flows("CHE", "USA", "TOTAL,27", "2022,2023", "X").data  # 4 rows
years = ",".join(str(year) for year in range(2010, 2024))
get_commodity_series("757", "27", "X", years).data  # 14 years, two calls, by period
get_world_trade("27", "2023", "M").data[0].reporter_desc  # 'China': largest first
[r.partner_desc for r in get_top_partners("CHE", "TOTAL", "2023", "X", 3).data]
# ['USA', 'Germany', 'China']: World, the total, is dropped
```

Release dates are per dataset, so they sit on the rows, not in `meta.published_at`:

```python
from xippios.comtrade import get_data_availability, get_live_update, get_metadata

[dataset] = get_data_availability("C", "A", "HS", reporter_code="757", period="2023").data
dataset.first_released, dataset.last_released  # first publication and latest revision
notes = get_metadata("C", "A", "HS", reporter_code="757", period="2023").data[0].notes
[note.publication_date for note in notes]  # "New Data", then each "Revised Data"
get_live_update().data  # the 50 most recent releases, newest first
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
result without a second call, and a count above 100,000 raises `QueryTooLarge` with the
count before anything is fetched, because upstream would cut the answer at 100,000 rows
without saying so. A free key allows 1 call per second and 500 calls per day, and
`countOnly` calls count; the client spaces calls 1.5 s apart (upstream's gateway refuses
some calls spaced exactly 1 s apart) and counts no calls, so the daily quota is yours to
track: once upstream answers that it is spent, the client sends nothing more until the
time upstream names and raises `RateLimitError` instead.

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
`search`: `{"search": "switz"}` returns 757 Switzerland. `--http` serves streamable HTTP
instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `data/v1/get/{typeCode}/{freqCode}/{clCode}` with `countOnly=true` | `get_counts(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, ...)` | `comtrade_get_counts` | alpha |
| `data/v1/get/{typeCode}/{freqCode}/{clCode}` | `get_data(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, ...)` | `comtrade_get_data` | alpha |
| `data/v1/getDa/{typeCode}/{freqCode}/{clCode}` | `get_data_availability(type_code, freq_code, cl_code, *, reporter_code=, period=, published_date_from=, published_date_to=)` | `comtrade_get_data_availability` | alpha |
| `data/v1/getMetadata/{typeCode}/{freqCode}/{clCode}` | `get_metadata(type_code, freq_code, cl_code, *, reporter_code=, period=)` | `comtrade_get_metadata` | alpha |
| `data/v1/getLiveUpdate` | `get_live_update()` | `comtrade_get_live_update` | alpha |
| `data/v1/get/C/{A,M}/{clCode}`, total row, one reporter and partner | `get_bilateral_flows(reporter, partner, commodities, periods, flow, *, cl_code="HS")` | `comtrade_get_bilateral_flows` | alpha |
| `data/v1/get/C/{A,M}/{clCode}`, total row, partner World, 12 periods per call, at most 120 | `get_commodity_series(reporter, commodity, flow, periods, *, cl_code="HS")` | `comtrade_get_commodity_series` | alpha |
| `data/v1/get/C/{A,M}/{clCode}`, total row, every reporter, partner World | `get_world_trade(commodity, period, flow, *, cl_code="HS")` | `comtrade_get_world_trade` | alpha |
| `data/v1/get/C/{A,M}/{clCode}`, total row, every partner, ranked | `get_top_partners(reporter, commodity, period, flow, n, *, cl_code="HS")` | `comtrade_get_top_partners` | alpha |
| `tools/v1/getTradeBalance/{typeCode}/{freqCode}/{clCode}` | `get_trade_balance(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, cmd_code=, ...)` | `comtrade_get_trade_balance` | alpha; experimental upstream |
| `tools/v1/getBilateralData/{typeCode}/{freqCode}/{clCode}` | `get_bilateral_data(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, cmd_code=, flow_code=, ...)`, returns `BilateralData` (`note`, `timestamp_requested`, the rows as `data`) | `comtrade_get_bilateral_data` | alpha; experimental upstream |
| `files/v1/app/reference/Reporters.json`, packaged | `list_reporters(search=None)` | `comtrade_list_reporters` | alpha |
| `files/v1/app/reference/partnerAreas.json`, packaged | `list_partners(search=None)` | `comtrade_list_partners` | alpha |
| `files/v1/app/reference/{clCode}.json`, keyless | `list_commodities(cl_code, search=None)` | `comtrade_list_commodities` | alpha |

The other twelve came with 0.1.0, the first release; `get_trade_balance` and
`get_bilateral_data` are not released yet. Alpha: the public surface may change
in a minor version before 1.0; `CHANGELOG.md` lists every change.

## Upstream terms and attribution

Data comes from UN Comtrade (https://comtradeplus.un.org), on the terms upstream states
for it in its [Policy on Comtrade Data Use](https://uncomtrade.org/docs/policy-on-comtrade-data-use/),
under which use of the data is subject to the license agreement at
https://comtrade.un.org/licenseagreement.html; this package adds no rights to it.
Documentation snapshot and its attribution: `docs/upstream/FETCHED.md`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
