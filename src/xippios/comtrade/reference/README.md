# Reference data for UN Comtrade

Code lists UN Comtrade publishes ship here as JSON, versioned with the package, and load
through `xippios.comtrade.params` (built on `xippios.core.reference`):

```python
from xippios.comtrade.params import packaged_values

packaged_values("flowCode").values  # ['M', 'X', 'DX', ...], no network call
```

Rules:

- Files come from the upstream through `scripts/refresh_reference.py`
  (`/refresh-reference-data`), never typed in by hand; the script also regenerates
  `enums.py`, one `StrEnum` per list, with `xippios.core.reference.render_str_enums`.
- Every file has a row below naming the endpoint or URL it came from and the date; the
  same origin is in the file's `origin` field.
- Each file is named after the upstream parameter it lists. `get_data` and `get_counts`
  check their arguments against these lists before calling upstream.
- Reference lookups are tools too (`comtrade_list_<thing>`), so agents can form valid calls.

| File | Origin | Fetched |
| --- | --- | --- |
| `clCode.json` | the `cmd:<clCode>` categories of https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json | 2026-10-23 |
| `flowCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/tradeRegimes.json | 2026-10-23 |
| `customsCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/CustomsCodes.json | 2026-10-23 |
| `motCode.json` | `id` of https://comtradeapi.un.org/files/v1/app/reference/ModeOfTransportCodes.json | 2026-10-23 |
| `typeCode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `typeCode` enum (snapshot of https://comtradeapi.un.org/files/v1/app/apim/comtrade.json) | 2026-10-23 |
| `freqCode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `freqCode` enum (same snapshot) | 2026-10-23 |
| `breakdownMode.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the `breakdownMode` enum (same snapshot) | 2026-10-23 |
| `aggregateBy.json` | `docs/upstream/apidocs/comtrade.json`, operation `get`, the names `aggregateBy`'s description lists (same snapshot) | 2026-10-23 |
