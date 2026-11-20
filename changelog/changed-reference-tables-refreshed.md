- Every list and table packaged from UN Comtrade's reference files is the one fetched on
  2026-11-20: `meta.retrieved_at` of `list_reporters`, `list_partners`, `list_classifications`
  and of `list_codes` for the six lists drawn from those files gives that day, and so does the
  fetch date an `UnknownCode` refusal names, while the four lists read from the spec keep
  theirs. `Reporters.json` adds `238` Falkland Isds (Malvinas): `list_reporters` answers 256
  reporters, where it answered 255, and `reporter_code` and the slices' `reporter` take `238`
  or `FLK`, where they refused it as a partner code only. `list_partners` gives `756`
  Switzerland without the trailing space upstream had sent in `text` and `partner_desc`, so an
  exact comparison or a `search` with that space no longer finds it; no code left any list or
  table, and every other record is unchanged. (https://github.com/xippios/sdk-comtrade/issues/54)
