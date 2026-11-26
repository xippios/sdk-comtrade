- `get_mirror_flows`, its MCP tool `comtrade_get_mirror_flows` and its route leave the
  package: the task fixed goods for the caller and cut `getBilateralData` to single product
  codes and 12 periods. `get_bilateral_data` answers the same operation with every argument
  that the caller sets, its rows with every field upstream sends beside upstream's note.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-core/issues/474)
