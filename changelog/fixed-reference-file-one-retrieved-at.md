- The call of `list_commodities` that fetches a classification file reports the
  `meta.retrieved_at` that every later call answered from the cache reports, one reading
  of the clock, where the two were read apart and differed slightly.
  (https://github.com/xippios/sdk-core/issues/79)
