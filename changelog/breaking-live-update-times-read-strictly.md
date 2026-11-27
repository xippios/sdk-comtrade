- `get_live_update` reads its four times strictly: an answer with a time that none of its
  four forms reads fails with core's `ValidationError`, which names `data/v1/getLiveUpdate`,
  where that time read as `None`. A time that UN Comtrade sends as null stays `None`.
  (https://github.com/xippios/sdk-usda-esr/issues/60)
