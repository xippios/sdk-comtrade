- The endpoint wrappers of `xippios.comtrade.api` return core's `Answer`, the model of
  upstream's answer as its `payload` beside its `retrieved_at`, where they returned the
  model itself. A caller of a wrapper reads `.payload`.
  (sdk-core ADR-0037, https://github.com/xippios/sdk-core/issues/479)
