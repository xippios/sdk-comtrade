# [How to retrieve data for “World” exports to a country in UN Comtrade?](https://uncomtrade.org/docs/how-to-retrieve-data-for-world-exports-to-a-country-in-un-comtrade/)

Upstream modified: 2024-11-25T15:27:11

**Question:** How can I use the UN Comtrade database to retrieve data for “World” exports to a specific country, and what filters should I use? For example, how can I find total world exports to Germany for the HS Code 330499?

**Answer:** You can retrieve data for “World” exports to a specific country by using the following two query options in UN Comtrade:

- Reporter: ALL, Partner: [Country], Trade Flow: Exports, HS Commodity Code: [Code]

Example: Reporter: ALL, Partner: Germany, Trade Flow: Exports, HS Commodity Code: 330499.

This query retrieves data reported by individual countries as exporters to the specified partner (e.g., Germany).

Note: Selecting “ALL” as the reporter allows you to gather data from all available reporting countries but does not necessarily represent the global “World” aggregate due to data availability limitations.

- Reporter: [Country], Partner: World, Trade Flow: Imports, HS Commodity Code: [Code]

Example: Reporter: Germany, Partner: World, Trade Flow: Imports, HS Commodity Code: 330499.

This query provides Germany’s own reported imports from all partners as a single aggregated value.

**Important considerations:**

Data Availability: The completeness of the “ALL” reporter query depends on the data availability reported by individual countries. Similarly, the “Partner: World” value is only an aggregate based on the reporting country’s available data for all its partners.

Bilateral Asymmetries: Exports reported by trading partners (Query 1) and imports reported by the specific country (Query 2) are theoretically mirrors of each other. However, they may differ due to issues such as:

1. Differences in reporting standards, classification, or timing.
2. Incomplete or missing data in the “World” aggregate.
3. For more information on data asymmetry issues, refer to the [UN Comtrade Bilateral Asymmetries Guide](https://uncomtrade.org/docs/bilateral-asymmetries/).

By comparing both queries, you can better understand the trade flows and account for possible inconsistencies.
