- `models.TradeFlowRecord`, `MirrorFlowRecord` and `MirrorFlows` leave with the tasks that
  returned them, and `params.SLICE_PINS`, `MAX_SERIES_PERIODS`, `validate_slice` and
  `validate_mirror_flows` with the tasks that read them. `TradeDataRecord` and
  `BilateralData` hold the rows of the two operations. No task resolves an ISO alpha-3 code
  any more: every area argument takes UN Comtrade's code, which `list_reporters` and
  `list_partners` find by its alpha-3 code. (sdk-core ADR-0060,
  https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-comtrade/issues/37)
