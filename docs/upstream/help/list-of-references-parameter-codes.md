# [List of References & Parameter Codes](https://uncomtrade.org/docs/list-of-references-parameter-codes/)

Upstream modified: 2026-04-09T21:00:44

In UN Comtrade website, you can go to [List of References](https://comtradeplus.un.org/ListOfReferences) to view and download the relevant codes.

Alternatively, you can:

- Download this Excel reference file: [UN Comtrade – Data Items and References](https://comtradeapi.un.org/files/v1/app/wiki/ComtradePlus_DataItems.xlsx)
- View the list of reference tables through the following endpoints in the table below
- Refer to the Python package **[comtradeapicall](https://pypi.org/project/comtradeapicall/)** (provided as is by the community)

| Code List | Description |
| --- | --- |
| List all reference tables | <https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json>  **Show list of reference tables**  `mydf = comtradeapicall.listReference()` |
| List of data items | List of data items/variables used in UN Comtrade <https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json> |
| Frequency | The time interval at which observations occur <https://comtradeapi.un.org/files/v1/app/reference/Frequency.json> |
| Trade Flows | Trade flow or sub-flow (exports, re-exports, imports, re-imports, etc.) <https://comtradeapi.un.org/files/v1/app/reference/tradeRegimes.json> |
| Customs Procedure Code | Customs or statistical procedure <https://comtradeapi.un.org/files/v1/app/reference/CustomsCodes.json> |
| Mode of Transports | The mode of transport used when goods enter or leave the economic territory of a country <https://comtradeapi.un.org/files/v1/app/reference/ModeOfTransportCodes.json> |
| Mode of Supply | The mode of supply on delivery of services (trade in services only) <https://comtradeapi.un.org/files/v1/app/reference/ModeOfSupply.json> |
| Partner country/area | The partner country or geographic area for the respective trade flow <https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json>  **Obtain list of partner codes**  `mydf = comtradeapicall.getReference('partner')` |
| Reporter | The country or geographic area to which the measured statistical phenomenon relates <https://comtradeapi.un.org/files/v1/app/reference/Reporters.json> |
| Quantity Units | The unit for quantity and alternate quantity data items <https://comtradeapi.un.org/files/v1/app/reference/QuantityUnits.json> |
| Product | The classification of products – goods or services  BEC 4 and 5:  <https://comtradeapi.un.org/files/v1/app/reference/B4.json> <https://comtradeapi.un.org/files/v1/app/reference/B5.json>   EBOPS 2002, 2010 and SDMX (EB is a combined list):  <https://comtradeapi.un.org/files/v1/app/reference/EB02.json> <https://comtradeapi.un.org/files/v1/app/reference/EB10.json> <https://comtradeapi.un.org/files/v1/app/reference/EB10S.json> <https://comtradeapi.un.org/files/v1/app/reference/EB.json>   HS nomenclatures and its editions (HS is the combined codes across all editions):  <https://comtradeapi.un.org/files/v1/app/reference/H0.json> <https://comtradeapi.un.org/files/v1/app/reference/H1.json> <https://comtradeapi.un.org/files/v1/app/reference/H2.json> <https://comtradeapi.un.org/files/v1/app/reference/H3.json> <https://comtradeapi.un.org/files/v1/app/reference/H4.json> <https://comtradeapi.un.org/files/v1/app/reference/H5.json> <https://comtradeapi.un.org/files/v1/app/reference/H6.json> <https://comtradeapi.un.org/files/v1/app/reference/HS.json>   SITC nomenclature and its revision (SS is the combined codes across all editions):  <https://comtradeapi.un.org/files/v1/app/reference/S1.json> <https://comtradeapi.un.org/files/v1/app/reference/S2.json> <https://comtradeapi.un.org/files/v1/app/reference/S3.json> <https://comtradeapi.un.org/files/v1/app/reference/S4.json> <https://comtradeapi.un.org/files/v1/app/reference/SS.json> |
