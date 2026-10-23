# Reference data for UN Comtrade

Code lists UN Comtrade publishes ship here as JSON, and its reference tables as CSV,
versioned with the package, and load through `xippios.comtrade.params` (built on
`xippios.core.reference`):

```python
from xippios.comtrade.models import Reporter
from xippios.comtrade.params import packaged_table, packaged_values

packaged_values("flowCode").values  # ['M', 'X', 'DX', ...], no network call
packaged_table("Reporters", Reporter)  # 255 Reporter rows, no network call
```

Rules:

- Files come from the upstream through `scripts/refresh_reference.py`
  (`/refresh-reference-data`), never typed in by hand; the script also regenerates
  `enums.py`, one `StrEnum` per list, with `xippios.core.reference.render_str_enums`.
- Every file has a row below naming the endpoint or URL it came from and the date; the
  same origin is in the file's `origin` field. Where a list departs from its reference
  file because the spec documents more, the file's `exceptions` name each value, the
  decision and the recorded answer it rests on.
- Each value list is named after the upstream parameter it lists. `get_data` and
  `get_counts` check their arguments against these lists before calling upstream.
- Each table is named after the upstream file it was written from, as CSV with one column
  per upstream key under its upstream name, in the order of its row model in `models.py`
  (`params.PACKAGED_TABLES`). An empty cell is a key the upstream row leaves out (no
  upstream value is empty; the script checks). None of the tables has nested fields, so
  none is kept as JSON. `tables.json` records each table's origin, fetch date and rows.
  Reporter codes are checked against `Reporters.csv`, partner and second-partner codes
  against `partnerAreas.csv`; `country_area_code_iso.csv` names the area behind a code
  that is not in the table asked for (756 Switzerland as a partner is 757 as a reporter).
- Reference lookups are tools too (`comtrade_list_<thing>`), so agents can form valid calls.

| File | Origin | Fetched |
| --- | --- | --- |
| `clCode.json` | the `cmd:<clCode>` categories of https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json, plus `BE` and `TM` from the `clCode` enum of `docs/upstream/apidocs/comtrade.json` (operation `get`), which upstream accepted (`tests/fixtures/get/count_cl_code_be.json`, `count_cl_code_tm.json`); the enum's `BE5` left out, refused (`count_cl_code_be5.json`). Every other value rests on a recorded count too (HTTP 200), except `H6`, which answered HTTP 500 to all five tries and stays, unsettled. Exceptions and evidence are in the file | 2026-10-23 |
| `flowCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/tradeRegimes.json, plus `MIF` and `XIF` from the `flowCode` description of `docs/upstream/apidocs/comtrade.json` (operation `get`); upstream accepted both (`tests/fixtures/get/count_flow_code_mif.json`, `count_flow_code_xif.json`, HTTP 200). Exceptions and evidence are in the file | 2026-10-23 |
| `customsCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/CustomsCodes.json | 2026-10-23 |
| `motCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/ModeOfTransportCodes.json | 2026-10-23 |
| `typeCode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `typeCode` enum (snapshot of https://comtradeapi.un.org/files/v1/app/apim/comtrade.json) | 2026-10-23 |
| `freqCode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `freqCode` enum (same snapshot) | 2026-10-23 |
| `breakdownMode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `breakdownMode` enum (same snapshot) | 2026-10-23 |
| `aggregateBy.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the names `aggregateBy`'s description lists (same snapshot) | 2026-10-23 |
| `mosCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/ModeOfSupply.json | 2026-10-23 |
| `qtyUnitCode.json` | `qtyCode` of https://comtradeapi.un.org/files/v1/app/reference/QuantityUnits.json, the codes `qtyUnitCode` and `altQtyUnitCode` carry on trade rows | 2026-10-23 |
| `Reporters.csv` | https://comtradeapi.un.org/files/v1/app/reference/Reporters.json, every column (255 rows) | 2026-10-23 |
| `partnerAreas.csv` | https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json, every column (310 rows) | 2026-10-23 |
| `country_area_code_iso.csv` | https://comtradeapi.un.org/files/v1/app/reference/country_area_code_iso.json (312 rows). Not in `ListofReferences.json`; it is the table the official `comtradeapicall` package (1.3.2, `convertCountryIso3ToCode`) reads to map ISO alpha-3 codes to UN Comtrade's | 2026-10-23 |
| `TradeDataItems.csv` | https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json, every column (50 rows); also in the snapshot as `docs/upstream/reference/TradeDataItems.json` | 2026-10-23 |
| `tables.json` | written by `scripts/refresh_reference.py`: origin, fetch date and rows of each CSV table above | 2026-10-23 |
