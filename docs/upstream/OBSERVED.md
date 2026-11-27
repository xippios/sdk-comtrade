# What UN Comtrade does but never documents

Notes, written by hand, on what UN Comtrade's API does that no file of this snapshot states
(sdk-core's conventions §3, sdk-core ADR-0028). The five OpenAPI files under `apidocs/` are
the reference for names and parameters, and the Help Center's articles under `help/` for the
limits of a key and the terms of the data. How the gateway applies those limits, the answers'
shapes, the empty answers, the refusals and the special values below come from the wire, and
`_client.py`, `models.py`, `params.py`, `tasks.py` and `tests/fixtures/` follow it.
`scripts/refresh_upstream.py` neither writes nor checks this file, and the `FETCHED.md` that
it writes lists the file in a row of its own.

Each note ends with its probe: the date, the operation by its path under
`https://comtradeapi.un.org`, as a task's `meta.endpoint` names it, and the sample. A sample
recorded as a fixture is named by its path under `tests/fixtures/`, whose `recorded_at` gives
the time of the request, and a packaged list by its file, whose `fetched` gives the time of its
fetch. A request that kept no answer is named in words beside a sample of its kind. The note on
the documentation's own address names the addresses requested and, in place of an operation and
a sample, the page they lead to with its row in `FETCHED.md`. The notes moved here on
2026-11-26 from `CLAUDE.md`, the docstrings of the wrappers and the modules, and the six tool
descriptions that 0.4.0 trimmed, and the last from
https://github.com/xippios/sdk-comtrade/issues/71; no request was sent to write this file.

## The key and the pace

### Calls spaced 1.0 s apart draw HTTP 429

The Help Center gives a free key one call a second, and the gateway's headers agree,
`x-ratelimit-limit: 1` and `x-ratelimit-operation-limit: 60`, but its one-second window is not
exact. Of 18 keyed calls spaced exactly 1.0 s apart, 9 drew HTTP 429 with
`{ "statusCode": 429, "message": "Rate limit is exceeded. Try again in 1 seconds." }` and
`Retry-After: 1`. Spaced 1.5 s apart, 2 of 39 drew one, and spaced 2.0 s apart none of 10.

Probe: 2026-10-23, `data/v1/get` with `countOnly`; samples
`tests/fixtures/get/count_rate_limited.json`, one of the nine refusals, and
`tests/fixtures/get/count_period_malformed.json`, which carries both headers. The other calls
of the three runs kept no answer.

### An unknown key: HTTP 401

A key that the gateway does not know answers HTTP 401 with `{"statusCode": 401, "message":
"Access denied due to invalid subscription key. Make sure to provide a valid key for an active
subscription."}`.

Probe: 2026-10-23, `data/v1/get` with `countOnly` and a bogus key; sample
`tests/fixtures/get/invalid_key.json`.

### A broad count can outlast a minute

A count over every reporter, `period=2022&partnerCode=0&cmdCode=AG4&flowCode=M`, outlasted a
read timeout of 60 s once, and its repeat answered in 27 s with `count` 5006385.

Probe: 2026-10-23, `data/v1/get` with `countOnly`; sample
`tests/fixtures/get/count_over_limit.json`, the repeat. The attempt that timed out kept no
answer.

## Trade data

### Over 100,000 records the answer is cut without a word

The Help Center allows a free key 100,000 records a call. Above it upstream does not refuse:
the data request of the query that counts 5,006,385 records answered HTTP 200 with the first
100,000 rows, `count` 100000 and an empty `error`, a body of about 89 MB.

Probe: 2026-10-23, `data/v1/get`; sample `tests/fixtures/get/count_over_limit.json`, the count
of the same query. The data request's answer was not kept, for its size.

### A thirteenth period: HTTP 400

A count over thirteen periods, 2010 to 2022, answers HTTP 400 with
`{"error": "Maximum number of periods is 12", "details": null}`. `tools/v1/getTradeBalance`
answers the same, while `data/v1/getDa` and `tools/v1/getBilateralData` answer thirteen periods
(below).

Probe: 2026-10-23, `data/v1/get` with `countOnly`; sample
`tests/fixtures/get/count_13_periods.json`.

### The count's own shape

An answer to `countOnly=true` carries the count in `count`, and in `data` one object of a
row's fields with placeholder values in place of the list of rows. Switzerland's exports to the
World in 2023, all goods, count 32, the rows that the data request answers.

Probe: 2026-10-23, `data/v1/get` with `countOnly` and without; samples
`tests/fixtures/get/count_ch_exports_2023.json` and `tests/fixtures/get/ch_exports_2023.json`.

### `breakdownMode` `plus` is the default

Switzerland's exports to the World in 2023, `cmdCode=TOTAL`, are 32 rows, one for each customs
procedure, mode of transport and second partner, without `breakdownMode` and with `plus` alike.
`classic` answers the total row alone, as pinning `partner2Code` 0, `customsCode` `C00` and
`motCode` 0 does, and the counts of the same queries match the rows. The total row's
`primaryValue` is `419922543423.509` and its `classificationCode` `H6`: a row asked for in `HS`
carries the edition that the reporter used.

Probe: 2026-10-23, `data/v1/get` with `countOnly` and without; samples
`tests/fixtures/get/ch_exports_2023.json`,
`tests/fixtures/get/ch_exports_2023_breakdown_mode_plus.json`,
`tests/fixtures/get/ch_exports_2023_breakdown_mode_classic.json`,
`tests/fixtures/get/ch_exports_2023_totals.json`,
`tests/fixtures/get/count_breakdown_mode_plus.json` and
`tests/fixtures/get/count_breakdown_mode_classic.json`.

### `aggregateBy` answers `-2` and `GG`

Switzerland's 2023 exports to the World by chapter, `cmdCode=AG2`, count 1,338 rows. With
`aggregateBy=cmdCode` they are 32 rows, the product code `-2`, and with
`aggregateBy=partnerCode,cmdCode` the partner code `-2` too, each row with `classificationCode`
`GG`; each count matches its rows.

Probe: 2026-10-23, `data/v1/get` with `countOnly` and without; samples
`tests/fixtures/get/count_ch_exports_2023_ag2.json`,
`tests/fixtures/get/ch_exports_2023_ag2_aggregate_by_cmd_code.json`,
`tests/fixtures/get/ch_exports_2023_ag2_aggregate_by_partner_code_cmd_code.json`,
`tests/fixtures/get/count_aggregate_by_cmd_code.json` and
`tests/fixtures/get/count_aggregate_by_partner_code_cmd_code.json`.

### `includeDesc` fills the descriptions

With `includeDesc=true` the rows carry the `*ISO` and `*Desc` fields, `reporterISO` `CHE` and
`reporterDesc` `Switzerland`; without it they are `null`.

Probe: 2026-10-23, `data/v1/get`; samples `tests/fixtures/get/ch_exports_2023_include_desc.json`
and `tests/fixtures/get/ch_exports_2023.json`.

### A code that upstream does not have counts 0

756, which is no reporter, Switzerland being 757, counts 0, and so do the period 1900 and the
product code 999998, while 999999 counts 10. Reporter 999 answers HTTP 200 with no row. An
empty answer cannot tell an unknown code from a known one without data.

Probe: 2026-10-23, `data/v1/get` with `countOnly` and without; samples
`tests/fixtures/get/count_not_a_reporter_756.json`,
`tests/fixtures/get/count_zero_ch_1900.json`, `tests/fixtures/get/count_cmd_code_absent.json`,
`tests/fixtures/get/count_cmd_code_999999.json` and `tests/fixtures/get/unknown_reporter.json`.

### A value of the wrong shape or an unknown flow or classification: HTTP 400

`period=2023-01` answers HTTP 400 with `{"error": "Invalid parameter value", "details":
[{"memberNames": ["period"], "errorMessage": "The field period is invalid"}]}`, and the flow
`Z`, the classification `BE5` and `mosCode=Mode 1` answer the same, each naming its field. The
detail of `data/v1` spells its keys `memberNames` and `errorMessage`, where those of
`public/v1` and `tools/v1` spell them `MemberNames` and `ErrorMessage` (below).

Probe: 2026-10-23, `data/v1/get` with `countOnly`; samples
`tests/fixtures/get/count_period_malformed.json`,
`tests/fixtures/get/count_flow_code_unknown.json`, `tests/fixtures/get/count_cl_code_be5.json`
and `tests/fixtures/get/count_services_eb10_mos_code_mode_1.json`.

### The classification `H6` answers HTTP 500

`clCode=H6`, which `ListofReferences.json` lists and the spec's enum for this operation lacks,
answered HTTP 500 with `{"error": "Something went wrong. Please try again.", "details": null}`
to all five tries, Switzerland and the USA, the product codes `TOTAL` and `01`, while a row of
Switzerland's 2023 asked for in `HS` carries `H6`.

Probe: 2026-10-23, `data/v1/get` with `countOnly`; samples
`tests/fixtures/get/count_cl_code_h6.json`, `tests/fixtures/get/count_cl_code_h6_retried.json`,
`tests/fixtures/get/count_cl_code_h6_retried_later.json`,
`tests/fixtures/get/count_cl_code_h6_usa.json` and
`tests/fixtures/get/count_cl_code_h6_cmd_code_01.json`.

### The other classifications

Switzerland's 2023 exports to the World, `TOTAL`, count 32 rows in `SS`, `S4`, `B4` and `B5`
and none in `H0` to `H5` and `S1` to `S3`: a classification that a reporter did not report in
answers no row, and no refusal.

Probe: 2026-10-23, `data/v1/get` with `countOnly`; samples
`tests/fixtures/get/count_cl_code_ss.json`, `tests/fixtures/get/count_cl_code_s4.json`,
`tests/fixtures/get/count_cl_code_b4.json`, `tests/fixtures/get/count_cl_code_b5.json`,
`tests/fixtures/get/count_cl_code_h0.json`, `tests/fixtures/get/count_cl_code_h5.json`,
`tests/fixtures/get/count_cl_code_s1.json` and `tests/fixtures/get/count_cl_code_s3.json`.

### `BE`, `TM`, `MIF` and `XIF`: values of the spec that the reference files lack

`clCode` `BE` and `TM`, which the spec's enum lists and `ListofReferences.json` does not, are
accepted: Switzerland's 2023 exports count 0 in `BE` and 1 in `TM`. `flowCode` `MIF` and `XIF`,
which the spec lists and `tradeRegimes.json` does not, are accepted and count 0. Upstream serves
no classification file for either classification: `BE.json` answers HTTP 404 with an XML body
whose code is `BlobNotFound`, and `TM.json` answered so too.

Probe: 2026-10-23, `data/v1/get` with `countOnly` and `files/v1/app/reference/BE.json`; samples
`tests/fixtures/get/count_cl_code_be.json`, `tests/fixtures/get/count_cl_code_tm.json`,
`tests/fixtures/get/count_flow_code_mif.json`, `tests/fixtures/get/count_flow_code_xif.json` and
`tests/fixtures/reference/be_absent.json`. The request for `TM.json` kept no answer.

### The totals of services

For services the classification files name `200` the total of `EB`, `EB02` and `EB10`, and
`S` that of `EB10S`. Switzerland's 2023 service exports count one row of `200` in `EB10` and in
`EB02`, and `TOTAL` counts none in `EB10`. In `EB` both `200` and `TOTAL` count 0, and in
`EB10S` `S` counts 0, which cannot be told from an unknown code.

Probe: 2026-10-23, `data/v1/get` with `countOnly` and without; samples
`tests/fixtures/get/count_cl_code_eb10.json`, `tests/fixtures/get/count_cl_code_eb02.json`,
`tests/fixtures/get/count_services_eb10_total.json`, `tests/fixtures/get/count_cl_code_eb.json`,
`tests/fixtures/get/count_services_eb_total.json`, `tests/fixtures/get/count_cl_code_eb10s.json`
and `tests/fixtures/get/services_ch_exports_2023_eb10.json`.

### `mosCode` filters, though no spec lists it

`mosCode`, which no spec lists, is accepted and filters: Switzerland's 2023 service exports in
`EB10` count one row with `0` and none with `1`, and in `EB` none with `0`. `Mode 1`, a
`mosCode` of `ModeOfSupply.json`, answers HTTP 400 naming `mosCode`.

Probe: 2026-10-23, `data/v1/get` with `countOnly`; samples
`tests/fixtures/get/count_services_eb10_mos_code_0.json`,
`tests/fixtures/get/count_services_eb10_mos_code_1.json`,
`tests/fixtures/get/count_services_eb_mos_code_0.json` and
`tests/fixtures/get/count_services_eb10_mos_code_mode_1.json`.

### `maxRecords` caps the rows

`maxRecords=5` answers 5 rows, `count` 5, of the query that counts 5,006,385 records. The Help
Center shows the parameter as `maxrecords=500`, and no spec lists it.

Probe: 2026-10-23, `data/v1/get`; sample `tests/fixtures/get/over_limit_max_records.json`.

### The size of a row

A row of `data/v1/get` is about 900 bytes as sent, the envelope's share included: Switzerland's
32 rows of 2023 are 28,843 bytes. One of `data/v1/getDa` is about 540, 169 rows in 91,029
bytes, and one of `tools/v1/getBilateralData` about 1,400, 13 rows in 18,216 bytes.

Probe: 2026-10-23 and 2026-10-28, `data/v1/get`, `data/v1/getDa` and
`tools/v1/getBilateralData`; samples `tests/fixtures/get/ch_exports_2023.json` and
`tests/fixtures/get_da/all_reporters_2023.json`, recorded 2026-10-23, and
`tests/fixtures/get_bilateral_data/ch_us_exports_13_periods.json`, recorded 2026-10-28.

## Availability, metadata and the release pipeline

### `getDa` answers one dataset for each reporter and period

Switzerland's 2023 is one dataset, and 2023 alone is 169, one for each reporter. 1900 answers
HTTP 200 with `count` 0 and no row. Thirteen periods are answered, 13 rows: the twelve periods
of `data/v1/get` do not bind here.

Probe: 2026-10-23, `data/v1/getDa`; samples `tests/fixtures/get_da/ch_2023.json`,
`tests/fixtures/get_da/all_reporters_2023.json`, `tests/fixtures/get_da/nobody_1900.json` and
`tests/fixtures/get_da/ch_13_periods.json`.

### A dataset revised in the published range counts

`publishedDateFrom=2024-01-01` with `publishedDateTo=2024-12-31` keeps two of Switzerland's
datasets: 2022, first released on 2023-02-01 and last on 2024-04-29, and 2023, first released
on 2024-02-02 and last on 2024-06-07. A dataset revised in the range counts.

Probe: 2026-10-23, `data/v1/getDa`; sample `tests/fixtures/get_da/ch_published_2024.json`.

### `getDa` refuses the spec's `EBSDMX`

`clCode=EBSDMX`, in the spec's enum for this operation, answers HTTP 400 with
`"errorMessage": "The field clCode is invalid"`.

Probe: 2026-10-23, `data/v1/getDa`; sample `tests/fixtures/get_da/services_ebsdmx.json`.

### `getMetadata` honours `reporterCode` and `period`

The spec lists the three path parameters alone. `reporterCode=757`, which the official
`comtradeapicall` package (1.3.2) sends, answers Switzerland's 38 datasets and nobody else's,
and `period=2023` beside it narrows them to one. `clCode=H6`, which the spec's enum for this
operation lacks, is answered as `HS` is. A call without `reporterCode` was not recorded.

Probe: 2026-10-23, `data/v1/getMetadata`; samples `tests/fixtures/get_metadata/ch_all_periods.json`,
`tests/fixtures/get_metadata/ch_2023.json` and `tests/fixtures/get_metadata/ch_2023_h6.json`.

### `getLiveUpdate`: 50 rows and a `count` of 174

The answer holds 50 rows, as the spec's "50 most recently updated releases" says, but its
`count` is 174, not the number of rows. No row carries a `publishedDate`, and every row is
`releaseStatus` `Released` and `status` `Success`, so the shapes of the other states are
unseen.

Probe: 2026-10-23, `data/v1/getLiveUpdate`; sample `tests/fixtures/get_live_update/latest.json`.

### `getLiveUpdate`: four times in three formats

`startedAt` and `completedAt` read `2026-10-22 21:27:39Z`, `lastUpdated` reads
`Thursday, October 22, 2026` and `queuedAt` reads `10/22/2026 11:18:33 PM`, without an offset
and about two hours after `startedAt`: probably a local time, of a zone that no document names.
In each of the 50 rows `completedAt` is earlier than `startedAt`.

Probe: 2026-10-23, `data/v1/getLiveUpdate`; sample `tests/fixtures/get_live_update/latest.json`.

### The release times carry no zone

Every release time is printed without a UTC offset, and no document states a zone:
`firstReleased` and `lastReleased` of `getDa` and `getWorldShare`
(`2024-02-02T04:52:35.2166667`, seven fractional digits), `publicationDate` of `getMetadata`
(`2024-02-02T05:18:25.78`) and `dateRelease` of `getComtradeReleases` (`2026-10-28T00:00:00`).
Switzerland's 2023 dataset has the same `firstReleased` and `lastReleased` in `getDa` and in
`getWorldShare`.

Probe: 2026-10-23 and 2026-10-28, `data/v1/getDa`, `data/v1/getMetadata`,
`public/v1/getWorldShare` and `public/v1/getComtradeReleases`; samples
`tests/fixtures/get_da/ch_2023.json` and `tests/fixtures/get_metadata/ch_2023.json`, recorded
2026-10-23, and `tests/fixtures/get_world_share/ch_2023.json` and
`tests/fixtures/get_comtrade_releases/calendar.json`, recorded 2026-10-28.

## The Tools

### The free key was answered on both Tools

Both Tools operations answered the package's free key. The spec's HTTP 403 "User not allowed"
for a free-tier key that is not on getTradeBalance's allow-list did not occur, and no other
403 was seen.

Probe: 2026-10-28, `tools/v1/getTradeBalance` and `tools/v1/getBilateralData`; samples
`tests/fixtures/get_trade_balance/ch_world_2023_include_desc.json` and
`tests/fixtures/get_bilateral_data/ch_us_exports_2023.json`.

### `countOnly` counts nothing on the Tools

`countOnly=true`, which neither spec lists, answers getTradeBalance with `count` 0 and a
placeholder object in `data` for the query that answers 48 rows, and getBilateralData ignores
it and answers the same row as without it.

Probe: 2026-10-28, `tools/v1/getTradeBalance` and `tools/v1/getBilateralData`; samples
`tests/fixtures/get_trade_balance/count_only_ch_world_2023.json`,
`tests/fixtures/get_trade_balance/ch_world_2023_include_desc.json` and
`tests/fixtures/get_bilateral_data/count_only_ch_us_exports_2023.json`.

### `getTradeBalance` answers every breakdown by default

Switzerland and the World in 2023, `TOTAL`, without `breakdownMode` are 48 rows, every customs
procedure and mode of transport; with `classic` the total row alone, its `primaryValueX`
`419922543423.509`, `primaryValueM` `365372487609.004` and `primaryValueBal`, the spec's
"X - M", `54550055814.504944`. `plus` was not sent. With `includeDesc` the `*ISO` and `*Desc`
fields are filled, and no answer with rows was recorded without it. 1900 answers `count` 0 and
no row, and thirteen periods HTTP 400 with "Maximum number of periods is 12".

Probe: 2026-10-28, `tools/v1/getTradeBalance`; samples
`tests/fixtures/get_trade_balance/ch_world_2023_include_desc.json`,
`tests/fixtures/get_trade_balance/ch_world_2023_include_desc_breakdown_mode_classic.json`,
`tests/fixtures/get_trade_balance/ch_world_1900_empty.json` and
`tests/fixtures/get_trade_balance/ch_world_13_periods.json`.

### `getBilateralData`: one flow, thirteen periods and the total row

Thirteen periods of Switzerland's exports to the USA answer 13 rows. `flowCode=M,X` answers
HTTP 400 with `"ErrorMessage": "The field flowCode is invalid"`: one flow a call, the spec's
enum, although its description reads "Multi value input should be in the form of csv". Only
`X` was recorded. Every row is the total of every breakdown, `customsCode` `C00` and `motCode`
0, and `includeDesc=true` changes nothing: the descriptions stay `null`.

Probe: 2026-10-28, `tools/v1/getBilateralData`; samples
`tests/fixtures/get_bilateral_data/ch_us_exports_13_periods.json`,
`tests/fixtures/get_bilateral_data/ch_us_2023_flow_code_m_x.json`,
`tests/fixtures/get_bilateral_data/ch_us_exports_2023.json` and
`tests/fixtures/get_bilateral_data/ch_us_exports_2023_include_desc.json`.

### The mirror and the note on a data gap

Switzerland's 2023 exports to the USA, DPRK (408) and Afghanistan (4) answer two rows,
Afghanistan's `mirrorPrimaryValue` 0, and a `note` that counts the partners with a gap and
names none: "EXPERIMENTAL: In reviewing the selection criteria, we've identified a data gap for
2 partner(s) during specific periods, which accounts for approximately 0.015% of the
accumulated world's share. ..." To DPRK alone the answer has `count` 0 and a gap for 1
partner, and `data/v1/get` answers no row for that pair either. To the USA alone the note
reads "EXPERIMENTAL: We have good news! There is no data gap among the selected partners for
bilateral trade comparison. ..." So the second gap is inferred to be Afghanistan's; no answer
states it. The note's wording varies with the answer, and it ends in HTML markup,
`<b>As a reminder, ...</b>`, where it names a gap.

Probe: 2026-10-28, `tools/v1/getBilateralData` and `data/v1/get`; samples
`tests/fixtures/get_bilateral_data/ch_us_kp_af_exports_2023.json`,
`tests/fixtures/get_bilateral_data/ch_kp_exports_2023_include_desc.json`,
`tests/fixtures/get_bilateral_data/ch_us_exports_2023.json` and
`tests/fixtures/get/ch_kp_exports_2023_totals.json`.

### `primaryValueDisc` and the `mirror2*` fields

In every recorded row `primaryValueDisc` equals (`mirrorPrimaryValue` − `primaryValue`) /
`primaryValue`: about -0.16 for Switzerland's 2023 exports to the USA and -1.0 where the mirror
is 0. The `mirror2*` fields are `null`, but `mirror2PrimaryValue`, 0. Upstream states neither
meaning.

Probe: 2026-10-28, `tools/v1/getBilateralData`; samples
`tests/fixtures/get_bilateral_data/ch_us_exports_2023.json`,
`tests/fixtures/get_bilateral_data/ch_us_kp_af_exports_2023.json` and
`tests/fixtures/get_bilateral_data/ch_us_exports_13_periods.json`.

### `timestampRequested` reads as UTC

The envelope's `timestampRequested`, "UTC, yyyy-MM-dd HH:mm:ss.fff" in the spec, has that form
in every recorded answer, `2026-10-28 16:14:25.593`, and lies within two seconds of the
answer's `Date` header.

Probe: 2026-10-28, `tools/v1/getBilateralData`; samples
`tests/fixtures/get_bilateral_data/ch_us_exports_2023_include_desc.json` and
`tests/fixtures/get_bilateral_data/ch_kp_exports_2023_include_desc.json`.

## The public operations

### `getComtradeReleases`: the recent releases, newest first

The answer is 38 rows, `count` 38, 4,502 bytes, released from 2026-10-22 to 2026-10-28,
newest first, though the spec states no order. Every `dateRelease` is a midnight and none is
after the day of the recording. `nr` is `N` (12 rows) or `R` (26), and `flagCode` two letters,
`CH` for 757; the spec states neither meaning.

Probe: 2026-10-28, `public/v1/getComtradeReleases`; sample
`tests/fixtures/get_comtrade_releases/calendar.json`.

### `getWorldShare` answers one row for each reporter and period

Without `period` it answers every period: Switzerland's are 64 annual rows, 1962 to 2025.
Without `reporterCode` it answers every reporter: 2023 is 214 rows, a body of 85,113 bytes, the
167 available rows first by reporter code and then the unavailable ones in an order that the
recording does not explain, the USA, 842, the 161st. Monthly, `C/M` with `period=202301`, it
answers one row with `month` 1, and an annual row carries `month` 52. `period=1900` answers
HTTP 200 with `count` 0.

Probe: 2026-10-28, `public/v1/getWorldShare`; samples
`tests/fixtures/get_world_share/ch_every_period.json`,
`tests/fixtures/get_world_share/all_reporters_2023.json`,
`tests/fixtures/get_world_share/ch_202301.json` and
`tests/fixtures/get_world_share/ch_1900_empty.json`.

### The shares and the placeholder of an unavailable dataset

The 214 values of 2023 sum to 1.0, Switzerland's `0.01651852126450239`; whether a share is a
fraction or a percentage, and of which trade, no document states. 47 rows have `isAvailable`
false, a `worldShare` all the same and `0001-01-01T00:00:00` as both `firstReleased` and
`lastReleased`, upstream's placeholder on an unavailable dataset.

Probe: 2026-10-28, `public/v1/getWorldShare`; sample
`tests/fixtures/get_world_share/all_reporters_2023.json`.

### `period=recent` answers HTTP 500

`period=recent`, which the spec lists, answered HTTP 500 with `count` -1 and an object in
`error`, `{"error": "Something went wrong. Please try again or contact ..."}`, ending in UN
Comtrade's address, on all three tries, with `reporterCode=757` and without: what it selects
is unknown.

Probe: 2026-10-28, `public/v1/getWorldShare`; samples
`tests/fixtures/get_world_share/ch_recent.json` and
`tests/fixtures/get_world_share/all_reporters_recent.json`. The other tries kept no answer.

### A malformed period: HTTP 400 without a `Content-Type`

`period=2023-01` answers HTTP 400 with `{"error": "Invalid parameter value", "details":
[{"MemberNames": ["period"], "ErrorMessage": "The field period is invalid"}]}` and no
`Content-Type` header.

Probe: 2026-10-28, `public/v1/getWorldShare`; sample
`tests/fixtures/get_world_share/period_malformed.json`.

## The reference files

### The reporter and partner tables share one code space

`Reporters.json` lists 256 areas and `partnerAreas.json` 310. A code in both names the same
area, but the tables differ: 0 World and 55 other areas are partners only, and 97 European
Union and 975 ASEAN are reporters only.

Probe: 2026-11-20, `files/v1/app/reference/Reporters.json` and
`files/v1/app/reference/partnerAreas.json`; samples
`src/xippios/comtrade/reference/Reporters.json` and
`src/xippios/comtrade/reference/partnerAreas.json`.

### The lengths of the lists

Of the packaged lists `qtyUnitCode`, from `QuantityUnits.json`, is the longest, 41 rows, about
3.4 KB of compact JSON, and the index of the files, `ListofReferences.json`, has 28 rows, about
5.5 KB.

Probe: 2026-11-20, `files/v1/app/reference/QuantityUnits.json` and
`files/v1/app/reference/ListofReferences.json`; samples
`src/xippios/comtrade/reference/qtyUnitCode.json` and
`src/xippios/comtrade/reference/ListofReferences.json`.

### The shapes of the product codes

The classification files that `ListofReferences.json` links hold `TOTAL` beside their codes:
digit strings for HS and BEC (`122` in `B4`), digits with a trailing `X` for SITC (`0011X`),
and letters, digits and dots for EBOPS (`SC11z` in `EB10S`, `205X`, `10.1.1.2`).

Probe: 2026-10-23, `files/v1/app/reference/B4.json` and `files/v1/app/reference/EB10S.json`;
samples `tests/fixtures/reference/b4.json` and `tests/fixtures/reference/eb10s.json`. The other
classification files read that day, those of SITC and of the other EBOPS editions among them,
kept no answer.

## The documentation

### The documentation's old address redirects to its new page

`https://comtradeplus.un.org/ApiDocs`, where the snapshot of 2026-10-28 read the documentation,
answered HTTP 302 to `https://comtrade.un.org/ApiDocs`, on another host, and that address
answered HTTP 302 to `/en/api-docs` on its own. `scripts/refresh_upstream.py` names the page
at the address that answers it and requests no page of the old one, since a capture follows no
redirect to another host.

Probe: 2026-11-26, 22:00 UTC, `https://comtradeplus.un.org/ApiDocs` and
`https://comtrade.un.org/ApiDocs`, one request each without a key, no answer kept; the page
they lead to, `https://comtrade.un.org/en/api-docs`, has the first row of the table of files
in `docs/upstream/FETCHED.md`.
