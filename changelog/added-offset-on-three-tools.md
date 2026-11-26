- `comtrade_get_data`, `comtrade_get_data_availability` and `comtrade_get_bilateral_data`
  take `offset`, the rows of a cut answer already shown, and answer the rows after them from
  the client's cache. Every page carries its note, and the note of every page but the last
  names the `offset` to continue with. (https://github.com/xippios/sdk-comtrade/issues/35)
