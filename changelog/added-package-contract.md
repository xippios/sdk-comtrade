- `xippios.comtrade.mcp` exports `build()`, which returns the tool set of xippios-core's
  package contract, `server`, built from it, and `ENV_VARS`, the variables the package
  reads: `COMTRADE_API_KEY`, a secret the data operations need. So a host serves the
  nineteen tools as `xippios-comtrade-mcp` does.
  (https://github.com/xippios/sdk-core/issues/245)
