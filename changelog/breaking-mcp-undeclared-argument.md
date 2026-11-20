- A tool refuses an argument that it does not declare before it runs, naming the ones it
  takes: `comtrade_list_codes` with `{"param": "motCode", "paramm": "x"}` answers
  `error: InvalidRequestError: paramm: Not an argument of this tool; it takes param`, where
  it dropped `paramm` and answered the transport codes.
  (https://github.com/xippios/sdk-core/issues/84)
