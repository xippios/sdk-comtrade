# Reference data for UN Comtrade

Code lists and calendars the upstream publishes (commodities, countries, report
schedules) ship here as CSV or JSON, versioned with the package, and load through
`xippios.core.reference`:

```python
from xippios.core import load_table

rows = load_table("xippios.comtrade", "commodities.csv", Commodity)
```

Rules:

- Files come from the upstream through `scripts/refresh_reference.py`
  (`/refresh-reference-data`), never typed in by hand; the script also regenerates
  `enums.py`, one `StrEnum` per list, with `xippios.core.reference.render_str_enums`.
- Every file has a row below naming the endpoint or URL it came from and the date.
- Reference lookups are tools too (`comtrade_list_<thing>`), so agents can form valid calls.

| File | Origin | Fetched |
| --- | --- | --- |
| (none yet) | | |
