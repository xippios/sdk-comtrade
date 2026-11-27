- `TypeCodeValue` loses `text`, and `list_codes("typeCode")` answers `C` and `S` without
  words, since UN Comtrade lists no reference file of `typeCode` and a label comes from
  upstream's own list. The words of `freqCode`, in `list_codes("freqCode")` and in
  `meta.names`, are those of UN Comtrade's `Frequency.json`, `Annual` and `Monthly`, in place
  of `annual` and `monthly` cut from the spec's description, and `FreqCodeValue.text` is
  always set. The file's third row, `Q` Quarterly, which the `freqCode` of no API document
  takes, stays refused before any request.
  (sdk-core ADR-0060, https://github.com/xippios/sdk-comtrade/issues/68)
