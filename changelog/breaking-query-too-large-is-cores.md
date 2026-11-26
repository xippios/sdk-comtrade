- `xippios.comtrade.errors` holds no `QueryTooLarge` of its own any more, so an import of it
  fails. A caller catches core's `xippios.core.QueryTooLarge`, which `get_data` raises, an
  `InvalidRequestError` with the count and the limit as before.
  (https://github.com/xippios/sdk-comtrade/issues/38)
