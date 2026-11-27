- `search` of `list_reporters`, `list_partners` and `list_commodities` and `category` of
  `list_classifications` are keyword-only, so `list_classifications("cmd:HS")` becomes
  `list_classifications(category="cmd:HS")`. The keyword-only arguments of every task stand
  in the spec's one order, `reporter_code`, `period`, `partner_code`, `partner2_code`,
  `cmd_code`, `flow_code`, `customs_code` and `mot_code` before the rest, which orders the
  tools' input schemas so and breaks no call by name.
  (sdk-core ADR-0061, https://github.com/xippios/sdk-usda-esr/issues/60)
