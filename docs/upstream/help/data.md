# [How to query data](https://uncomtrade.org/docs/data/)

Upstream modified: 2025-03-10T16:39:49

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-menu.png)

The Data menu links all types of data available in the UN Comtrade database. Each link directs the user to the standard query page for the selected type of data.

**The query page maintains a consistent structure across various data pages, ensuring a standardized approach to data retrieval.**

### Querying Data

**Standard Query Page:**For illustration purposes, see the example below for ***[Trade Data](https://comtradeplus.un.org/TradeFlow):***

![](https://uncomtrade.org/wp-content/uploads/2024/02/query-page-1024x346.png "UN Comtrade > New Comtrade User Guide > image2022-10-25_14-54-28.png")

**Query parameters:** Each query parameter features a drill-down list that allows users to select and submit either single or multiple values for their queries. Additionally, users can enter a search term, and the drill-down list will provide matching values based on the input text or string.

![](https://uncomtrade.org/wp-content/uploads/2024/02/image-24.png)

For the query parameter “**Periods**,” users can expand the list by clicking the chevron or expansion symbol on the right. This action reveals additional values for the parameter, allowing users to scroll through and select one or more options by clicking on the available values.

Additionally, users can manually input search text into the query field. The drill-down functionality will then retrieve matches based on this entered text.

The maximum number of periods that you can submit is 12.

#### Parameter value “ALL”

The parameter value ALL is available under the reporter, partner, 2nd partner, trade flows, modes of transport, and customs codes criteria. Passing ALL will return all individual values under the data item. For partners and 2nd partners, passing ALL will return all individual partners and the WORLD aggregate.

#### Parameter value “WORLD” as partner and 2nd partner

Passing WORLD as a partner and 2nd partner returns the world the aggregate value. “World” as a partner is the same as the sum of individual partners.

---

### Saving Parameters and Searches

As a standard feature, users can save full queries and their parameters for future use. This is particularly useful for those who frequently retrieve data using the same parameters. This functionality is available at both the parameter (field) level and the query level. *Note: To enable aggregation for specific parameters, you must select those parameters in the “Aggregate By” option.*

#### Saving Parameters

![](https://uncomtrade.org/wp-content/uploads/2024/02/image-25.png)

You must be logged in to save your parameters. Once you have defined a list or group, click the **Save Group** icon to the right of each parameter field. This will save the current values selected in the parameter field.\

In this example, ASEAN member countries were selected as trade partners. The user clicks on the **Save Group** icon.

![](https://uncomtrade.org/wp-content/uploads/2024/02/image-26.png)

A window will pop up and ask the user to provide a search name. A user provides “ASEAN Partners.” The user clicks on “Submit,” and the partner grouping is saved.

![](https://uncomtrade.org/wp-content/uploads/2024/02/image-27.png)

The saved partner group will now appear under the **Partners** query field and be available for future queries.

---

#### Saving Queries / Searches

![](https://uncomtrade.org/wp-content/uploads/2024/02/image-30.png)

A window will pop up and ask the user to provide a search name. A user provides the search name, “USA Imports From ASEAN.” The user clicks on “Submit,” and the **query** is saved

![](https://uncomtrade.org/wp-content/uploads/2024/02/image-29-1024x451.png)

First, construct your query by selecting a value for each parameter to save your full query. Click on the Save Query icon on the bottom right.

![](https://uncomtrade.org/wp-content/uploads/2024/02/image-31.png)

Saved parameters and queries can be found under your My Comtrade profile.

---

### Query Options

In addition to specifying selection criteria, the system offers two options for querying:

![](https://uncomtrade.org/wp-content/uploads/2024/02/image2022-8-9_16-16-8.png "UN Comtrade > New Comtrade User Guide > image2022-8-9_16-16-8.png")

- **Breakdown Mode**

Accepted values: **Plus** or **Classic**. The *Plus* enables the breakdown of new data items in Comtrade+ notably detailed trade flow, mode of transport, customs procedure codes, and the 2nd partner (when reported by countries). Whereas the *Classic*, the selection criteria are automatically set to the following values: trade flows to exports, imports, re-imports, and re-exports), mode of transport to total, customs procedure codes to total, and the 2nd partner to World. The *classic* mode returns the same dataset as the legacy Comtrade.

- **Aggregate By**

Accepted values**:** None, or any combinations of Commodity Code, Period, Reporter, Partner, 2nd Partner, Mode of Transports and Customs Procedure Codes. If the Aggregate By is active, then the trade values, netweight and gross weight will be aggregated along the selected combination. For example, the following selection will return four records because all reporters will be aggregated into single code.

![](https://uncomtrade.org/wp-content/uploads/2024/02/image2022-10-25_15-1-55-1024x414.png "UN Comtrade > New Comtrade User Guide > image2022-10-25_15-1-55.png")

And by adding the Period in the Aggregate By, the query will return two records.

![](https://uncomtrade.org/wp-content/uploads/2024/02/image2022-10-25_15-2-57-1024x415.png "UN Comtrade > New Comtrade User Guide > image2022-10-25_15-2-57.png")
![](https://uncomtrade.org/wp-content/uploads/2024/02/image2022-8-9_16-17-21.png "UN Comtrade > New Comtrade User Guide > image2022-8-9_16-17-21.png")

---

### Viewing and saving query results

Users can choose Preview, Download, or Deliver options to receive the requested data. See the table below for the differences.

|  |  |  |
| --- | --- | --- |
| **Data Extraction Mode** | **Description** | **Access** |
| [Preview](https://uncomtrade.org/docs/what-is-data-preview/) | The data will be shown on screen and be limited to 500 records (regardless of the actual results) | Public (no-registration) |
| Download | The data will be downloaded directly and limited to 100K and 250K records for registered users and subscribers, respectively | Registration required |
| [Deliver](https://uncomtrade.org/docs/what-is-data-delivery/) | The data will be prepared in the background, and the link will be sent to the email. The data is limited to 2.5M records | Subscription required |
