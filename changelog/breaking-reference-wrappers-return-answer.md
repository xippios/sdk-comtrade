- `xippios.comtrade.api.reference_rows` and `api.reference` return xippios-core's `Answer`:
  the rows are its `payload` and the time its `retrieved_at`, where they returned
  `api.ReferenceFile`, which is gone, with `rows` and unpacked as a pair.
  (https://github.com/xippios/sdk-core/issues/123)
