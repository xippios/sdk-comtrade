- The client keeps the keyed answers under `data/v1` and `tools/v1` for 300 s beside the
  reference files, which it keeps for the life of the process, each by the longest path
  prefix that its path starts with. A call repeated within five minutes is answered from the
  cache and spends no call of the daily quota, while the public operations under
  `public/v1` stay out of it. (https://github.com/xippios/sdk-core/issues/479)
