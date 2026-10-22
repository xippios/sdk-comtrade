# [Menu: Data Availability](https://uncomtrade.org/docs/data-availability/)

Upstream modified: 2026-10-01T16:05:23

![](https://uncomtrade.org/wp-content/uploads/2024/02/data-availability-menu.png)

## **How do you view data availability?**

There are several ways to view data availability in UN Comtrade:

1. You can browse detailed data availability at <https://comtradeplus.un.org/DataAvailability>.
2. You can view the dashboard:  [https://comtradeplus.un.org/Visualization/DADashboard.](https://comtradeplus.un.org/Visualization/DADashboard)
3. You can view recent releases: <https://comtradeplus.un.org/RecentReleases>
4. You can view the time series <https://comtradeplus.un.org/DATimeSeries>.
5. You can also obtain this information through the [My API Portal](https://comtradeplus.un.org/MyComtrade/APIPortal).   You will need an API subscription key to place API calls.

### **Dashboard**

The [dashboard](https://comtradeplus.un.org/Visualization/DADashboard) provides a visual summary of available data and its estimated world share, explore released datasets whether they are new or revised data, and view a summary of data gaps in terms of world share and number of reporters.

### **Recent Releases**

This page displays a list of datasets organized by their publication date, with the most recent dates appearing first.

### **Time Series**

This page displays the data availability in a series format, and includes the reported classification code, and the availability of extended data items such as modes of transport, second partner country, and customs procedure codes by dataset.

### **Detailed**

The detailed data availability page returns a catalog of datasets in New Comtrade. It provides summary information of published file types available by dataset. <https://comtradeplus.un.org/DataAvailability>

![](https://uncomtrade.org/wp-content/uploads/2024/03/image-3-1024x638.png)

Similar to the trade data query page, a user can retrieve this catalog information by selecting the appropriate criteria as follows:

- **Type of Product** – Goods or Services
- **Frequency** – Annual or Monthly
- **Classification Code** – HS, SITC, BEC for Goods, EBOPS for Services
- **Period** – YYYY for Annual or YYYYMM for Monthly (maximum of 12 periods)
- **Reporter** – All or Individual Reporters
- **Publication Date** – Publication date range

For example, a user wants to know all available USA annual merchandise datasets published from January 1, 2019, to December 31, 2023. The parameter values would be the following:

- **Type of Product** – Goods
- **Frequency** – Annual
- **Classification Code** – HS, As Reported
- **Period** – Recent periods
- **Reporter** – USA
- **Publication Date** – 01/01/2019 – 12/31/2023

![](https://uncomtrade.org/wp-content/uploads/2024/03/image-4-1024x227.png)

The user can choose to view the results on screen by

1. clicking **Preview** to view the results on screen, or
2. clicking on **Download** to save the results into a file.

A snapshot of the results screen is returned below.

![](https://uncomtrade.org/wp-content/uploads/2024/03/image-5-1024x601.png)

From the result screen, the user can do the following:

![](https://uncomtrade.org/wp-content/uploads/2024/03/image-6-1024x378.png)

Click on ‘Extended Columns’ and see item ‘A’ in the figure above. Expand the results table to include Reporter Code and Type Code as part of the results table.

![](https://uncomtrade.org/wp-content/uploads/2024/03/image-7-1024x374.png)

Click on the download icon; see item ‘B’ in the figure above. The results file will be downloaded immediately.

User can also click more information on the tip right information icon, toggle between the list or cube viewing format and the eye icon to see metadata.

### **Data Availability via API**

Users can query the data availability through APIs through these endpoints:

1. <https://comtradeapi.un.org/public/v1/getComtradeReleases>: return the list of the recent releases, the same with [the UI live update](https://comtradeplus.un.org/RecentReleases) page.
2. <https://comtradeapi.un.org/data/v1/getDa> and <https://comtradeapi.un.org/data/v1/getDaTariffline>: return the data availability for trade and tariffline data respectively.
3. <https://comtradeapi.un.org/bulk/v1/get> and <https://comtradeapi.un.org/bulk/v1/getTariffline>: return the data availability for the bulk trade and tariffline files respectively. Note that these APIs are only accessible to premium users.

For users’ convenience, the Python package of [comtradeapicall](https://pypi.org/project/comtradeapicall/) (provided as is by the community) can be utilized to extract data availability with the following model classes:

**Data Availability:** Model class to extract data availability.

- `getFinalDataAvailability(subscription_key, SelectionCriteria):` return data frame containing final data availability.
- `getTarifflineDataAvailability(subscription_key, SelectionCriteria)`: return data frame containing tariff line data availability.
- `getFinalDataBulkAvailability(subscription_key, SelectionCriteria, [publishedDateFrom], [publishedDateTo])`: return data frame containing final bulk files data availability.
- `getTarifflineDataBulkAvailability(subscription_key, SelectionCriteria, [publishedDateFrom], [publishedDateTo])`: return the data frame containing the data availability of tariffline bulk files.
- `getLiveUpdate(subscription_key)`: return data frame recent data releases.

Examples of Python data availability classes are available at [comtradeapicall](https://pypi.org/project/comtradeapicall/).

---

## **Timetable for data availability of country**

##### **Q: How soon will country data for imports and exports be available?**

**A:** There is no expected date or time when a specific country’s data will become available. We request the annual and monthly merchandise and services data in February and June. However, we receive data from various countries at different times. When our office receives the data, we harmonize, validate, and upload it into the UN Comtrade database.

You can use [data availability API](https://comtradedeveloper.un.org/) to monitor newly released data or visit our [data availability page](https://comtradeplus.un.org/DataAvailability).

##### **Q: What is the frequency of data refresh?**

**A:** Similarly, there is no set schedule for data refresh.  We process data continuously as long as data providers send data.  For annual data, most data providers send provisional data earlier during the year and follow up with revised and/or final data towards the latter part of the year.  For monthly merchandise data, we follow up with countries that have indicated they will regularly provide monthly data. Receipt of monthly data varies by data provider and can be received monthly or quarterly, or together with their annual dataset. Some countries provide their latest monthly data within a month of the close of the reference period, while others provide their data later.  Many countries still need to establish regular provision of monthly data, and we are working with data providers to improve the regularity of data provision.

##### **Q: Why is monthly data not available for a specific year when annual data for the same reporter/period exists?**

**A:**Countries submit their datasets in diverse formats and follow varying schedules. Some countries furnish annual data without monthly breakdowns, so we can only release the annual data. However, certain countries may include the monthly breakdown within their annual data or transmit monthly data separately. In these instances, we publish both sets of data.

##### **Q: API Data Versions and Updates**

To my understanding, countries report both provisional trade data as well as revised and/or final trade data later on. I wonder, is the data that’s provided through the API always the final version of the trade data, or could it be subject to change later on? That is, would I have to update already fetched data now and then to ensure I have the latest version/revision of the data?

I have looked through the code on GitHub for the comtradeapicall Python package, but despite the functions having names such as bulkDownloadFinalFile, they seem to simply redirect to bulkDownloadFile and so on, only with the parameter tradeDataType set to ‘FINAL’. However, this parameter doesn’t seem to have an impact on the actual API call, so that makes me wonder if all data provided through the API is always final?

**A:** To clarify, the data provided through the UN Comtrade API is always the latest available reported data. UN Comtrade only keeps one version of a dataset, which means the data may be updated with revisions over time, but there is no permanent archive of multiple versions. When you retrieve data through the API (using the functions: bulkDownloadFinalFile — for the most recent data in *reported* classification, or bulkDownloadFile — for the most recent data in *converted* classification), you’re getting the most recent dataset as reported by the country.

To ensure you always have the latest version of the trade data, it would be a good practice to periodically update your fetched data. You can refer to the publication notes on the UN Comtrade website for the latest publication dates, which can guide you on when new or revised data is available.

##### **Q: Does UN Comtrade revise its annual data after the initial release?**

**A:** Yes. UN Comtrade data may be updated or revised after the initial release. This happens because national data providers often submit **provisional data** early in the year, followed by **revised and/or final data** later on.

**Revision Policy**

- Single-version policy: UN Comtrade maintains only **one version** of each dataset. This means that once data are updated, only the most recent version is accessible — there is **no archive** of earlier versions.
- Ongoing updates: Users should be aware that data may change over time as countries submit updates or corrections.

**How to Track or Access Updated Figures**

To stay informed about revisions and updates:

1. Check Publication Notes – Visit the [UN Comtrade Publication Notes](https://comtradeplus.un.org/PublicationNotes) for the latest release dates and update information.
2. Browse the Data Availability Page – Explore data availability and updates directly via the [Data Availability Page](https://comtradeplus.un.org/DataAvailability).
3. Use the Data Availability API – Monitor newly released or revised datasets programmatically through the [Data Availability API](https://comtradeplus.un.org/ApiDocs).

For details on data updates, please visit and monitor the [Data Availability section](https://comtradeplus.un.org/DataAvailability) on the UN Comtrade website.

---
