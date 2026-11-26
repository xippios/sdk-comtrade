- `get_commodity_series`, its MCP tool `comtrade_get_commodity_series` and its route leave
  the package: the task fixed goods, partner 0 and the total row for the caller and sent at
  most 120 periods, 12 a call. `get_data` answers each 12 periods with `type_code` `"C"`,
  `partner_code="0"`, `breakdown_mode="classic"` and `include_desc=True`, and a series of
  `get_data` over more than 12 periods waits for a later release. (sdk-core ADR-0060,
  https://github.com/xippios/sdk-core/issues/474,
  https://github.com/xippios/sdk-comtrade/issues/36)
