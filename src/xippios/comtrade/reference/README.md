# Reference data for UN Comtrade

Code lists and reference tables UN Comtrade publishes ship here, versioned with the
package, and load through `xippios.core.PackagedList` and `xippios.comtrade.params`:

```python
from xippios.core import PackagedList

from xippios.comtrade.models import Reporter

flow_code = PackagedList.load("xippios.comtrade", "flowCode")
[record["flowCode"] for record in flow_code.records]  # ['M', 'X', 'DX', ...], no network call
reporters = PackagedList.load("xippios.comtrade", "Reporters")
reporters.parse(Reporter, source="comtrade")  # 255 Reporter rows, no network call
```

Each file is `reference/<name>.json`, `{"param", "endpoint", "fetched", "records"}` and an
optional `"note"` (conventions §3, ADR-0022): `endpoint` the upstream operation it came
from, `fetched` when, `records` upstream's records under upstream's field names, a value
list as records of one field named by the parameter, and `note` its provenance in words.
In the table below, Origin names the endpoint or URL a file was fetched from, or the
`docs/upstream/` file it was rebuilt from; Fetched is that fetch's UTC time, or the
snapshot's `Fetched` time. A file whose `fetched` is a bare date reads as 00:00 UTC of
that day until the next refresh writes the full time.

| File | Origin | Fetched |
| --- | --- | --- |
| `clCode.json` | the `cmd:<clCode>` categories of https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json, plus `BE` and `TM` from the `clCode` enum of `docs/upstream/apidocs/comtrade.json` (operation `get`), which upstream accepted (`tests/fixtures/get/count_cl_code_be.json`, `count_cl_code_tm.json`); the enum's `BE5` left out, refused (`count_cl_code_be5.json`). Every other value rests on a recorded count too (HTTP 200), except `H6`, which answered HTTP 500 to all five tries and stays, unsettled. Exceptions and evidence are in the file's `note` | 2026-10-23 |
| `flowCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/tradeRegimes.json, plus `MIF` and `XIF` from the `flowCode` description of `docs/upstream/apidocs/comtrade.json` (operation `get`); upstream accepted both (`tests/fixtures/get/count_flow_code_mif.json`, `count_flow_code_xif.json`, HTTP 200). Exceptions and evidence are in the file's `note` | 2026-10-23 |
| `customsCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/CustomsCodes.json | 2026-10-23 |
| `motCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/ModeOfTransportCodes.json | 2026-10-23 |
| `typeCode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `typeCode` enum (snapshot of https://comtradeapi.un.org/files/v1/app/apim/comtrade.json) | 2026-10-23 |
| `freqCode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `freqCode` enum (same snapshot) | 2026-10-23 |
| `breakdownMode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `breakdownMode` enum (same snapshot) | 2026-10-23 |
| `aggregateBy.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the names `aggregateBy`'s description lists (same snapshot) | 2026-10-23 |
| `mosCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/ModeOfSupply.json. The file's ids (`0`, `Mode 1` to `Mode 4`), not proven parameter values: `data/v1/get` accepts `mosCode` though the spec does not list it, refused `Mode 1` and accepted `0` and `1` (`tests/fixtures/get/count_services_eb10_mos_code_*.json`). `mosCode` is not a task parameter; the file's `note` says the same | 2026-10-23 |
| `qtyUnitCode.json` | `qtyCode` of https://comtradeapi.un.org/files/v1/app/reference/QuantityUnits.json, the codes `qtyUnitCode` and `altQtyUnitCode` carry on trade rows | 2026-10-23 |
| `Reporters.json` | https://comtradeapi.un.org/files/v1/app/reference/Reporters.json, every column (255 rows) | 2026-10-23 |
| `partnerAreas.json` | https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json, every column (310 rows) | 2026-10-23 |
| `country_area_code_iso.json` | https://comtradeapi.un.org/files/v1/app/reference/country_area_code_iso.json (312 rows). Not in `ListofReferences.json`; it is the table the official `comtradeapicall` package (1.3.2, `convertCountryIso3ToCode`) reads to map ISO alpha-3 codes to UN Comtrade's | 2026-10-23 |
| `TradeDataItems.json` | https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json, every column (50 rows); also in the snapshot as `docs/upstream/reference/TradeDataItems.json` | 2026-10-23 |
