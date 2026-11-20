- A route answers an argument that its schema refuses, an `n` of `get_top_partners` that is
  no integer say, or one that is missing, as problem details before the task runs: HTTP 422,
  `application/problem+json`, the title `InvalidRequestError` and the detail
  `n: Input should be a valid integer, unable to parse string as an integer`, where
  FastAPI's own 422 listed its error details with the value sent.
  (https://github.com/xippios/sdk-core/issues/66)
