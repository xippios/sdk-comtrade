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
`reporter_code` against the packaged `Reporters.json` and `partner_code` and
`partner2_code` against `partnerAreas.json`, the others by shape; a mistake raises
`InvalidRequestError` naming the closest valid value (`756` names `757`, Switzerland).

```python
from xippios.comtrade import list_commodities, list_partners, list_reporters

list_reporters().data  # 255 reporters, packaged with this version: no call
list_partners().data  # 310 partner areas, 0 World among them
list_commodities("HS").data  # 8,262 HS codes, fetched keyless once per process
```

`get_data` counts first with upstream's `countOnly`: a count of zero returns an empty
result without a second call, and a count above 100,000 raises `QueryTooLarge` with the
count before anything is fetched, because upstream would cut the answer at 100,000 rows
without saying so. A free key allows 1 call per second and 500 calls per day, and
`countOnly` calls count; the client spaces calls a second apart, the daily quota is
yours to track.

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
200 rows or 64 KB with a note on how to narrow the query. The list tools take no filter
yet, so `comtrade_list_reporters`, `comtrade_list_partners` and `comtrade_list_commodities`
show the first rows of their table only (200 of 255 reporters, in upstream's alphabetical
order). `--http` serves streamable HTTP instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| `data/v1/get/{typeCode}/{freqCode}/{clCode}` with `countOnly=true` | `get_counts(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, ...)` | `comtrade_get_counts` | alpha |
| `data/v1/get/{typeCode}/{freqCode}/{clCode}` | `get_data(type_code, freq_code, cl_code, *, reporter_code=, partner_code=, ...)` | `comtrade_get_data` | alpha |
| `files/v1/app/reference/Reporters.json`, packaged | `list_reporters()` | `comtrade_list_reporters` | alpha |
| `files/v1/app/reference/partnerAreas.json`, packaged | `list_partners()` | `comtrade_list_partners` | alpha |
| `files/v1/app/reference/{clCode}.json`, keyless | `list_commodities(cl_code)` | `comtrade_list_commodities` | alpha |

## Upstream terms and attribution

Data comes from UN Comtrade (https://comtradeplus.un.org) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
