# [Trade Flows in UN Comtrade](https://uncomtrade.org/docs/trade-flows-in-un-comtrade/)

Upstream modified: 2026-04-09T20:59:14

## 1. Overview

**Trade flows (or trade regimes)** represent the classification of goods movements based on:

- Direction of trade (imports / exports)
- Customs procedures applied to the goods
- Statistical treatment under international standards

The list of flows is defined in the reference tables (<https://comtradeplus.un.org/ListOfReferences> – under the “Trade Flow”) and implemented in the API and datasets.

These flows are derived from:

- **Statistical standards**, notably\
  *International Merchandise Trade Statistics ([IMTS 2026](https://unstats.un.org/go/imts2026))*. It describes domestic exports, foreign imports, re-exports and re-imports
- **Customs procedures**, particularly those defined in the\
  Revised Kyoto Convention ([Specific Annex F – Processing](https://www.wcoomd.org/en/Topics/Facilitation/Instrument%20and%20Tools/Conventions/pf_revised_kyoto_conv/Kyoto_New)). It focuses on inward and outward processing.

---

## 2. Core Flows

These correspond to the standard IMTS concepts of cross-border trade.

### 2.1 Total Imports (M)

Goods entering the economic territory.

### 2.2 Total Exports (X)

Goods leaving the economic territory.

### 3. Origin-Based Subclassification

UN Comtrade distinguishes trade flows based on whether goods are **domestically produced or foreign-origin**.

### 3.1 Domestic Exports (DX)

Exports of goods that:

- Are **produced or substantially transformed** in the reporting country

### 3.2 Re-exports (RX)

Exports of goods that:

- Were previously imported
- Are exported again **without substantial transformation**

### 3.3 Foreign Imports (FM)

Imports of goods that:

- Are of **foreign origin**

### 3.4 Re-imports (RM)

Imports of goods that:

- Were previously exported
- Are re-imported **without substantial transformation**

---

## 4. Processing-Related Flows (Kyoto Convention – Annex F)

UN Comtrade extends the basic IMTS flows using **customs procedure codes**, especially those related to processing.

### 4.1 Inward Processing (IP)

**Definition (WCO):**\
Goods imported for processing and subsequently exported, with conditional duty relief.

#### Derived flows:

- **MIP — Imports for Inward Processing**\
  Goods imported under inward processing procedure
- **XIP — Exports after Inward Processing**\
  Resulting goods exported after processing under inward processing

### 4.2 Outward Processing (OP)

**Definition (WCO):**\
Goods exported for processing abroad and subsequently imported.

#### Derived flows:

- **XOP — Exports for Outward Processing**\
  Goods exported for processing abroad
- **MOP — Imports after Outward Processing**\
  Goods imported after outward processing

---

## 5. Full Set of Trade Regime Flows

Based on the **trade regimes reference table**, the flows include:

| Code | Flow description | Relationships |
| --- | --- | --- |
| M | Total Imports | M = FM + RM + MIP + MOP |
| X | Total Exports | X = DX + RX +XIP + XOP |
| DX | Domestic exports |  |
| RX | Re-exports |  |
| FM | Foreign imports |  |
| RM | Re-imports |  |
| MIP | Imports for inward processing |  |
| XIP | Exports after inward processing |  |
| MOP | Imports after outward processing |  |
| XOP | Exports for outward processing |  |

Note that in UN Comtrade, the flows of M and X always exist, but the breakdowns may not. Some countries may report RX or DX, and others may report XIP or MOP. Be cautious when analyzing the sub-flows.
