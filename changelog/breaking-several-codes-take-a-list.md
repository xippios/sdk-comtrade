- Several values of a filter are one argument that takes one code or a list of codes,
  `reporter_code=[757, 842]`, which the package sends as UN Comtrade's comma-separated text,
  and a comma-separated text such as `"757,842"` is refused before any request. It holds for
  `reporter_code`, `period`, `partner_code`, `partner2_code`, `cmd_code`, `flow_code`,
  `customs_code`, `mot_code` and `aggregate_by`, while `flow_code` of `get_bilateral_data`
  stays one value. Over MCP each takes a JSON array, and the route of a task that takes a
  list is a `POST` with a JSON body in place of a `GET` with a query.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-comtrade/issues/66)
