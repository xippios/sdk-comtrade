# [How should I interpret and use quantity data in UN Comtrade?](https://uncomtrade.org/docs/how-should-i-interpret-and-use-quantity-data-in-un-comtrade/)

Upstream modified: 2025-05-13T15:03:30

**Q: What does a zero or empty value in the quantity field mean?**\
A: In practice, the null and zero values for quantity have the same meaning. They come from the non-reported data (null) or the estimation method (zero). In the original data sources (customs data or enterprise survey), some quantity information may be missing, resulting in a data gap. This does not happen for the value measure. You can learn the estimation methodology at [Quantity and Weight Data in UN Comtrade](https://uncomtrade.org/docs/quantity-and-weight-data-in-un-comtrade/)[.](https://uncomtrade.org/docs/quantity-and-weight-data-in-un-comtrade/)

**Q: Can I sum quantity values, including zero or null?**\
A: Caution is required when summing quantity data:

- **Avoid summing when any data point is zero or null**, which may lead to misleading totals. Some tools might ignore these values, resulting in inaccurate aggregation.
- **Ensure quantity units are consistent** before summing. Mixing different units (e.g., kilograms and number of vehicles) results in meaningless totals.
- **Do not aggregate across incompatible commodities**. Summing quantities like “number of chickens” and “number of cars” is invalid due to unit and category differences.
- **Use judgment when aggregating weight-based units**. While detailed commodity-level aggregation may be problematic, summing weights at a higher level can be useful for applications like infrastructure or logistics planning.
