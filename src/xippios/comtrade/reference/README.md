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
from, `fetched` when, `records` upstream's records under upstream's field names, and
`note` its provenance in words. A list's record holds the value under the parameter's
name and, beside it, the fields upstream words the value in, under upstream's names
(`{"motCode": "2100", "text": "Sea"}`); a value without words is a record of one field.
A table's records are upstream's rows. In the table below, Origin names the endpoint or
URL a file was fetched from, or the `docs/upstream/` file it was rebuilt from; Fetched is
that fetch's UTC time, the answer's `retrieved_at` (for a file the client's cache answered,
the time its entry was stored), or the snapshot's `Fetched` time in
`docs/upstream/FETCHED.md`. `scripts/refresh_reference.py` wrote every file on 2026-10-28,
keyless; no value or row changed from the files of 2026-10-23.

| File | Origin | Fetched |
| --- | --- | --- |
| `clCode.json` | the `cmd:<clCode>` categories of https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json with their `variable` and `description`, plus `BE` and `TM`, values alone, from the `clCode` enum of `docs/upstream/apidocs/comtrade.json` (operation `get`), which upstream accepted (`tests/fixtures/get/count_cl_code_be.json`, `count_cl_code_tm.json`); the enum's `BE5` left out, refused (`count_cl_code_be5.json`). Every other value rests on a recorded count too (HTTP 200), except `H6`, which answered HTTP 500 to all five tries and stays, unsettled. Exceptions and evidence are in the file's `note` | 2026-10-28T22:02:01Z |
| `flowCode.json` | `id` and `text` of https://comtradeapi.un.org/files/v1/app/reference/tradeRegimes.json, plus `MIF` and `XIF`, values alone, from the `flowCode` description of `docs/upstream/apidocs/comtrade.json` (operation `get`), which lists values without wording; upstream accepted both (`tests/fixtures/get/count_flow_code_mif.json`, `count_flow_code_xif.json`, HTTP 200). Exceptions and evidence are in the file's `note` | 2026-10-28T22:02:02Z |
| `customsCode.json` | `id` and `text` of https://comtradeapi.un.org/files/v1/app/reference/CustomsCodes.json | 2026-10-28T22:02:04Z |
| `motCode.json` | `id` and `text` of https://comtradeapi.un.org/files/v1/app/reference/ModeOfTransportCodes.json | 2026-10-28T22:02:05Z |
| `typeCode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `typeCode` enum, each value's `text` the wording the parameter's description gives it ("Type of trade: C for commodities and S for service"; snapshot of https://comtradeapi.un.org/files/v1/app/apim/comtrade.json) | 2026-10-28T14:38:34Z |
| `freqCode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `freqCode` enum, each value's `text` the wording of the description ("Trade frequency: A for annual and M for monthly"; same snapshot) | 2026-10-28T14:38:34Z |
| `breakdownMode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `breakdownMode` enum, values alone: the description ("Breakdown mode to choose from") words none (same snapshot) | 2026-10-28T14:38:34Z |
| `aggregateBy.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the names `aggregateBy`'s description lists, values alone (same snapshot) | 2026-10-28T14:38:34Z |
| `mosCode.json` | `id` and `text` of https://comtradeapi.un.org/files/v1/app/reference/ModeOfSupply.json. The file's ids (`0`, `Mode 1` to `Mode 4`), not proven parameter values: `data/v1/get` accepts `mosCode` though the spec does not list it, refused `Mode 1` and accepted `0` and `1` (`tests/fixtures/get/count_services_eb10_mos_code_*.json`). `mosCode` is not a task parameter; the file's `note` says the same | 2026-10-28T22:02:07Z |
| `qtyUnitCode.json` | `qtyCode`, as text, with `qtyAbbr` and `qtyDescription`, of https://comtradeapi.un.org/files/v1/app/reference/QuantityUnits.json, the codes `qtyUnitCode` and `altQtyUnitCode` carry on trade rows | 2026-10-28T22:02:08Z |
| `Reporters.json` | https://comtradeapi.un.org/files/v1/app/reference/Reporters.json, every column (255 rows) | 2026-10-28T22:02:10Z |
| `partnerAreas.json` | https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json, every column (310 rows) | 2026-10-28T22:02:11Z |
| `country_area_code_iso.json` | https://comtradeapi.un.org/files/v1/app/reference/country_area_code_iso.json (312 rows). Not in `ListofReferences.json`; it is the table the official `comtradeapicall` package (1.3.2, `convertCountryIso3ToCode`) reads to map ISO alpha-3 codes to UN Comtrade's | 2026-10-28T22:02:13Z |
| `TradeDataItems.json` | https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json, every column (50 rows); also in the snapshot as `docs/upstream/reference/TradeDataItems.json` | 2026-10-28T22:02:14Z |
| `ListofReferences.json` | https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json, the index of the reference files, every column (28 rows: `category`, `variable`, `description`, `fileuri`); also in the snapshot as `docs/upstream/reference/ListofReferences.json` | 2026-10-28T22:02:01Z |
