- `get_data` refuses a query over UN Comtrade's limit of 100,000 records per call with
  core's `QueryTooLarge`, whose message gives the count, the limit, that the count was sent
  and no data fetched, and what narrows the query. It still answers a count of 0 with an
  empty list and no data request, and its answer carries the count as `meta.total`.
  (https://github.com/xippios/sdk-comtrade/issues/38)
