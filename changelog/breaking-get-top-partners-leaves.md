- `get_top_partners`, its MCP tool `comtrade_get_top_partners` and its route leave the
  package: the task ranked a reporter's partners by `primary_value`, dropped partner 0, the
  World, and kept the first `n`, a ranking that a task of a source does not make.
  `get_data` without `partner_code` answers every partner's row, the World's among them,
  with `type_code` `"C"`, `breakdown_mode="classic"` and `include_desc=True`.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474)
