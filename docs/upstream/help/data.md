# [How to query data](https://uncomtrade.org/docs/data/)

Upstream modified: 2026-11-24T02:26:00

The Data menu has all the types of data in UN Comtrade. Each link opens the query page of that type of data. The query pages have a similar structure. This page uses [Trade statistics](https://comtrade.un.org/en/trade-statistics) as the example.

![](https://uncomtrade.org/wp-content/uploads/2024/02/home-02-menu-data-1.jpg)

### Querying Data

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-01-trade-statistics-2-1024x559.jpg "UN Comtrade > New Comtrade User Guide > image2022-10-25_14-54-28.png")

To query data:

1. Choose the type, frequency and classification.
2. Refine your search: choose the commodity codes, periods, reporters, partners and trade flows.
3. If you need them, set the query options.
4. Select **Preview**. To clear the form, select **Start again**.

### Step 1. Type, frequency and classification

- **Type:** Goods or Services.
- **Frequency:** Annual or Monthly (goods only).
- **Classification:** for goods, HS, SITC or BEC; for services, EBOPS. “HS, as reported” gives the data in the HS edition each country used.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-02-type-frequency-classification-1024x143.jpg)

### Step 2. Refine your search

You can choose one or several values in each field. Select the information icon next to a field for help on it.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-03-refine-your-search-1024x435.jpg)

- **Commodity codes:** type a code or a product name and choose from the suggestions. Wildcards: 0901\* for every code starting with 0901; 27?? for every 4-digit code in chapter 27. AG2 gives all 2-digit codes and ALL gives every code separately. TOTAL is the total of all commodities.
- **Periods:** years such as 2025 for annual data, months such as 202501 for monthly data, or “recent”. For monthly data, “All of 2025” chooses every month of that year.
- **Reporters:** a name, numeric code or ISO code, such as Kenya, 404 or KEN.
- **Partners:** the trading partners. 0 is the world.
- **Second partner:** the country of consignment or destination. 0 is the world.
- **Trade flows:** such as exports (X) and imports (M).
- **Mode of transport:** 0 is the total of all modes.
- **Customs procedure:** C00 is the total of all procedures.

Second partner, mode of transport and customs procedure apply to goods only and are available when you log in.

Type in a field to search for a value:

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-04-search-a-code.jpg)

Or select the arrow on the right of a field to open its list. To remove a value, select the x next to it.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-05-periods-list.jpg)

How many values you can choose depends on your account:

| Account | Commodity codes | Periods |
| --- | --- | --- |
| Not logged in | 1 | 1 |
| Free | Up to 10 | More than one |
| Premium | Up to 500 | More than one |

### The value “all”

The value “all” is available for reporters, partners, second partner, trade flows, mode of transport and customs procedure. It returns every individual value of that field. For partners, it returns every individual partner and also the World total.

### The value “World” as partner and second partner

Choosing World (0) as partner or second partner returns the total for all partners. “World” as a partner is the same as the sum of the individual partners.

### Example

Imports of the United States of America from the ASEAN countries in 2024, all commodities:

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-06-example-query-1024x602.jpg)

## Saving lists and searches

If you often use the same values or the same query, save them. You must be logged in.

### Saving a list of values

1. Choose the values in a field, for example the ASEAN countries in Partners.
2. Select **Save list** below the field.
3. Enter a name, for example “ASEAN partners”, and select **Save list**.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-07-save-list.jpg)

To use the list again, select **My lists** below the same field.

Note: to add up the values of a list into one total, choose that field in “Aggregate by” (see [Query options](https://uncomtrade.org/docs/data/#query-options)).

### Saving a search

1. Build your query and select **Preview**.
2. Select **Save search**.
3. Enter a name, for example “USA imports from ASEAN”, and select **Save**.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-08-save-search-1024x241.jpg)

To use the search again, select **My saved searches** at the top of the Trade statistics page, choose the search and select **Load**.

All your lists and searches are in My Comtrade > Saved searches and lists, where you can open or delete them.

## Query options

When you are logged in, there are two more options:

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-09-query-options-1-1024x141.jpg)

### Breakdown mode

- **Plus** includes trade value in CIF and FOB, quantity in secondary units, gross weight, mode of transport, second partner and customs procedure, when countries report them.
- **Classic** has only the first partner and commodities, in the standard trade flows: imports, exports, re-exports and re-imports.

### Aggregate by

Accepted values: None, or any combination of Reporter, Partner, Second partner, Commodity code, Customs procedure and Mode of transport. The values chosen in those fields are added up into one row. With None, each value has its own row.

Example: imports of the United States of America from the 11 ASEAN countries in 2023 and 2024. With None, the query returns 22 rows: one for each country and year. Aggregated by Partner, it returns 2 rows: one total of the 11 countries for each year.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-10-aggregate-by-1024x567.jpg)

## Viewing and saving query results

After you select **Preview**, the results are shown below the form, with buttons to get or share the data. If you change the query, select Preview again.

### Preview

The preview shows up to 500 records, 50 on each page. Select a column heading to sort by it.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-11-preview-1024x601.jpg)

### Download

Choose a format: CSV, Excel workbook (.xlsx), JSON or tab-separated text. You must be logged in.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-12-download-1024x251.jpg)

### Deliver

For large queries (Premium). The file is prepared in the background. Select **Send me the link**, and a link to download the file is sent to the email address of your account. The file is also in My Comtrade > My data deliveries. Files are deleted 48 hours after they are ready.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-13-deliver-1024x266.jpg)

### Copy link to share

Copies a link to your query. Anyone who opens the link sees the same query, within the limits of their own account.

### API call

Shows the same query as a call to the UN Comtrade API, to use in your own code or tools. Add your subscription key, which you can get in My API portal.

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-14-api-call-1024x491.jpg)

### Preview, Download and Deliver

| Data extraction mode | Description | Access |
| --- | --- | --- |
| [Preview](https://uncomtrade.org/docs/what-is-data-preview/) | The data is shown on screen, up to 500 records. | Public (no registration) |
| Download | The data is downloaded directly: up to 100,000 records per request with a Free account and up to 250,000 with Premium. | Log in required |
| [Deliver](https://uncomtrade.org/docs/what-is-data-delivery/) | The file is prepared in the background and the link is sent by email: up to 2.5 million records. | Premium subscription required |
