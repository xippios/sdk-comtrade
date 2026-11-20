- `list_commodities` asks upstream again for a classification file whose answer it could
  not read, where the cache kept that answer and the task failed with it for the life of the
  process. (https://github.com/xippios/sdk-core/issues/122)
