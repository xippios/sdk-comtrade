# [UN Comtrade API](https://uncomtrade.org/docs/un-comtrade-api/)

Upstream modified: 2026-10-01T15:35:19

UN Comtrade offers APIs with or without an API subscription key. However, to access a full set of APIs, you will need a UN Comtrade account and a valid API subscription key. Note that a premium subscription allow access to all APIs, whereas free subscription allow access to some APIs. The API without subscription key is called a “preview” and it has a very limited API end points, and it is intended to have a quick view of the data.

- To create a UN Comtrade B2C account, please see: [How to create a UN Comtrade account](https://uncomtrade.org/docs/how-to-create-a-un-comtrade-account/)
- To request an API subscription key, please see: [Acquiring API Subscription Keys](https://uncomtrade.org/docs/api-subscription-keys/)
- To skip learning UN Comtrade APIs, and instead use Python/R community libraries, please see: [Developer tools for UN Comtrade Data](https://uncomtrade.org/docs/developer-tools/)

### Preview APIs

There is no need to create an account nor having API subscription key, the preview APIs would work as is. However, there is a limitation on number of records and rate limit to ensure a fair usage. If you face any performance issue using the preview APIs, you should use the API end points with subscription key instead. The API endpoints to preview data use the following URL:

|  |  |
| --- | --- |
| `public/v1/preview` | preview final data |
| `public/v1/getMetadata` | preview metadata information |
| `public/v1/getDA` | preview data availability |

As an example, the following URL will preview the China export in 2023. Note: all parameters are described in the developer portal.

```
https://comtradeapi.un.org/public/v1/preview/C/A/HS?flowCode=X&reporterCode=156&period=2023
```

### My API Portal

The My API Portal, <https://comtradeplus.un.org/MyComtrade/APIPortal> and API Explorer <https://comtradeplus.un.org/ApiDocs>, allow users to generate API key and explore API end points, respectively.

Some of API endpoints are described below — but the complete set is available at API Explorer

The API endpoints to extract trade data, including the data availability are as follows: **get, getTariffline, getDa**, **getDaTariffline**, **getLiveUpdate**, **getTariffline.**

|  |  |
| --- | --- |
| `data/v1/getDa` | extract data availability – final data |
| `data/v1/getDaTariffline` | extract data availability – tariffline data |
| `data/v1/getLiveUpdate` | extracts most recent publication updates |
| `data/v1/get` | extracts final data |
| `data/v1/getTariffline` | extracts tariffline data |
| `data/v1/getMetadata` | extracts metadata information |

The API endpoints to download trade data in [bulk format (pre-packaged compressed files)](https://uncomtrade.org/bulk-files/#bulkfiletypes) are: **get**, **getTariffLine, getClassic**.

|  |  |
| --- | --- |
| `bulk/v1/get` | trade data availability and link to bulk trade data file |
| `bulk/v1/getTariffline` | tariffline data availability and link to bulk tariffline data file |
| `bulk/v1/getClassic` | trade data availability and link to trade data file in classic format |

### Using your subscription key for calling APIs

You can browse through the API endpoints/operations in the Developer Portal, and you can also try it using the interface. The examples below show some of usual use cases such as downloading bulk files.

|  |  |  |
| --- | --- | --- |
| **API calls** | **Description** | **Subscription Tier** |
| `https://comtradeapi.un.org/data/v1/getLiveUpdate?subscription-key={yourSUBSCRIPTIONkeyGOEShere}` | To show the progress on data release | Free |
| `https://comtradeapi.un.org/data/v1/get/C/A/HS?cmdCode=93&period=1998&reporterCode=124&partnerCode=0&flowCode=X&maxrecords=500&subscription-key={yourSUBSCRIPTIONkeyGOEShere}` | To extract small amount of trade data: commodity code 93, year 1998, reporter code 124, partner code 0, flow code X | Free |
| `https://comtradeapi.un.org/bulk/v1/file/792/9276b9391090069cc73e0250164f39a63e089dbd1fb02?subscription-key={yourSUBSCRIPTIONkeyGOEShere}` | To download a bulk file, the URL is provided when calling the data availability. See below for details | Premium |

### Download the data with csv or txt format

If you don’t use the **format** parameter, it will return a JSON format as default (you can also use format=json but it is not required). See below,

```
https://comtradeapi.un.org/data/v1/getDA/C/A/HS?period=2022&subscription-key=yourSubsKey
```

When you include the parameter **format=csv** or **format=txt** in your API call, the downloaded file will be a csv or text file. For example:

```
https://comtradeapi.un.org/data/v1/getDA/C/A/HS?period=2022&subscription-key=yourSubsKey&format=csv will download in csv format and it is comma separated;
```

```
https://comtradeapi.un.org/data/v1/getDA/C/A/HS?period=2022&subscription-key=yourSubsKey&format=txt  will download in txt format and it is TAB separated (same as bulk files).
```

### Using API for files bulk download – Premium APIs only

Once you have your subscription key, you will be able to query the data availability API for New Comtrade Bulk files using this url below. You can obtain the list of codes in different dimensions from this file [Comtrade Data Items](https://comtradeapi.un.org/files/v1/app/wiki/ComtradePlus_DataItems.xlsx).

```
https://comtradeapi.un.org/bulk/v1/get/{type}/{frequency}/{classificationCode}?<reporterCode>&<period>&subscription-key={yourSUBSCRIPTIONkeyGOEShere}
Classic Format:
https://comtradeapi.un.org/bulk/v1/getClassic/{type}/{frequency}/{classificationCode}?<reporterCode>&<period>&subscription-key={yourSUBSCRIPTIONkeyGOEShere}
```

Parameters:

- **{}** mandatory parameters:
  - **type** => **C** (commodities) or **S** (services)
  - **frequency** => **A** (annual) or **M** (monthly)
  - **classificationCode** => **HS** for original classification or specific HS editions of H5, H4, H3, etc.
- <> optional parameters:
  - **reporterCode**  => M49 Trade country code e.g. 300 Greece
  - **period** => **YYYY** for Annual or **YYYYMM** for Monthly
- **Subscription-Key** => Your personal subscription key

These are full examples of the bulk data availability API (the subscription-key is a sample).

- 2011 Annual – Greece – H3 Classification

```
https://comtradeapi.un.org/bulk/v1/get/C/A/H3?reporterCode=300&period=2011&subscription-key=1A2B3C4D5E6F304e7ea860b6faa627X8Z9
```

- February 2012 Monthly – Greece – HS Original Classification

```
https://comtradeapi.un.org/bulk/v1/get/C/M/HS?reporterCode=300&period=201202&subscription-key=1A2B3C4D5E6F304e7ea860b6faa627X8Z9
```

- 2008 Annual – Greece – SITC Rev3 converted Classification (specify the version)

```
https://comtradeapi.un.org/bulk/v1/get/C/M/S3?reporterCode=300&period=2008&subscription-key=1A2B3C4D5E6F304e7ea860b6faa627X8Z9
```

- All 2023 Monthly Data in H0 classification

[`https://comtradeapi.un.org/bulk/v1/get/C/M/H0?period=202301,202302,202303,202304,202305,202306,202307,202308,202309,202310,202311,202312&subscription-key=1A2B3C4D5E6F304e7ea860b6faa627X8Z9`](https://comtradeapi.un.org/bulk/v1/get/C/M/H0?period=202301,202302,202303,202304,202305,202306,202307,202308,202309,202310,202311,202312&subscription-key=1A2B3C4D5E6F304e7ea860b6faa627X8Z9)

The response of the API call includes a field called fileUrl to the bulk file.

Example result:

![](https://uncomtrade.org/wp-content/uploads/2024/03/image-1.png)

To download a file, you must include your Subscription key in the value of **fileUrl**, for example:

```
https://comtradeapi.un.org/bulk/v1/file/300/8713e7032869f910595a72ec1dfca2d190df5fa95297950f17478421be376bff?subscription-key=1A2B3C4D5E6F304e7ea860b6faa627X8Z9
```
