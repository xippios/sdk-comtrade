- `xippios.comtrade.enums`, the ten `StrEnum` classes generated from the packaged lists,
  leaves the package, and `scripts/refresh_reference.py` no longer renders it nor takes
  `--render-only`. No module of the package imported it, and a task takes a code as a plain
  text all the same. `list_codes` returns each packaged list with upstream's words for every
  value. (https://github.com/xippios/sdk-comtrade/issues/64)
