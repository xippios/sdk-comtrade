- `TypeCodeValue` loses `text`, and `list_codes("typeCode")` answers `C` and `S` without
  words, since UN Comtrade lists no reference file of `typeCode` and a label comes from
  upstream's own list. The words of `freqCode`, in `list_codes("freqCode")` and in
  `meta.names`, come from UN Comtrade's `Frequency.json` in place of those cut from the
  spec's description, and `FreqCodeValue.text` is always set.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-comtrade/issues/68)
