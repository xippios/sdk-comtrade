- `get_world_trade`, its MCP tool `comtrade_get_world_trade` and its route leave the
  package: the task fixed goods, partner 0 and the total row for the caller and sorted the
  reporters by `primary_value`. `get_data` without `reporter_code` answers the same rows, in
  upstream's order, with `type_code` `"C"`, `partner_code="0"`, `breakdown_mode="classic"`
  and `include_desc=True`. (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474)
