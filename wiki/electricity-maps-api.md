# Electricity Maps API

[Electricity Maps](https://www.electricitymaps.com/) exposes zonal grid and market signals through
its [v4 API](https://portal.electricitymaps.com/docs/reference/). It provides observations and
proprietary forecasts. It is not an order book: it contains no bids, bid curves, plant schedules or
network constraints.

## Signals

| Signal | What it says | What it is for |
|---|---|---|
| Electricity mix and source | The whole mix, or one generation or storage technology, in MW; either domestic generation or flow-traced consumption | Generation and consumption-mix forecasts |
| Electricity flows | Imports and exports with each neighbouring zone, in MW | Cross-border-flow and net-position forecasts |
| Total load | Consumption calculated consistently as generation − exports + imports − charging + discharging | Comparable demand across zones |
| Total reported load | Load as defined by each grid operator | Matching the operator's published demand |
| Net load | Reported load minus wind and solar generation | Demand left for dispatchable generation |
| Day-ahead price | Published and proprietary forecast prices in the response's local currency per MWh; Core uses EUR/MWh | Price forecasts and scoring |
| Carbon intensity and shares | Carbon intensity plus renewable and carbon-free shares, from domestic generation or flow-traced consumption | Emissions accounting and carbon-aware scheduling |
| Fossil-only carbon intensity | Emissions per kWh generated from fossil sources | Comparing the remaining fossil mix |

## Time and place

Requests identify a zone such as `DE` or `SI`, or use latitude and longitude. Depending on the
signal and coverage, v4 accepts 5-minute, 15-minute or hourly resolution.

| Suffix | Result |
|---|---|
| `latest` | Newest available point; it may still be estimated |
| `history` | Latest 24 hours |
| `past` | One requested historical time |
| `past-range` | A requested historical interval |
| `forecast` | Proprietary forecast, normally 6, 24, 48 or 72 hours ahead |

European day-ahead prices add `actual`, for published prices in the past or future, and `combined`,
which extends published prices with Electricity Maps forecasts. Access is licensed per signal,
time window and zone. Clients send the key in the `auth-token` header.

## Latest example

`GET /v4/electricity-mix/latest?zone=DE&breakdownType=normal` returns the newest German domestic-mix
point. Read three fields together:

- `datetime`: the operating hour the point describes;
- `updatedAt`: when Electricity Maps last updated it;
- `isEstimated` and `estimationMethod`: whether it is measured or filled by an estimator.

`latest` therefore means newest available operating hour, not day-ahead forecast.

## Forecast example

`GET /v4/electricity-mix/forecast?zone=DE&horizonHours=24&breakdownType=normal` returns future German
mix points. `updatedAt` identifies the stored version's update time; it is not a selector for
superseded forecast runs. Each `data[].datetime` is a target operating hour, so a next-day example
must select the intended delivery timestamp rather than the first point.

Where the aggregate flow totals are internally consistent, the point implies:

`net position = data[].mix.flows.exports − data[].mix.flows.imports`

Positive means net export. The dedicated `electricity-flows/forecast` instead gives imports and
exports by neighbouring zone.

## Inconsistency

In a same-hour German check on 2026-09-10, the aggregate flow totals in `electricity-mix/forecast`
and the neighbour values in `electricity-flows/forecast` implied opposite net-position signs even
though both responses had the same update time. The total-load identity agreed with the mix totals,
while the dedicated flows route is the documented source for neighbour flows. Treat the forecast
net position as unresolved until Electricity Maps clarifies the contract or an invariant check
passes; choosing either result silently can reverse the modelled trade.

## Access

Direct v4 checks with the project key on 2026-09-10 found:

- Day-ahead price forecasts returned 24 hourly points for every Core zone: AT, BE, CZ, DE, FR, HR,
  HU, NL, PL, RO, SI and SK. Price `latest`, 24-hour `history` and `combined` also worked.
- Electricity mix, flows, total load, net load and carbon-intensity forecasts returned 25 hourly
  points for Germany: the present hour plus 24 hours ahead. Their 24-hour histories also worked.
- Arbitrary `past` and `past-range` requests were denied for those grid signals and prices. The
  price-specific `actual` route nevertheless returned all 24 hours of 2024-08-29 for every Core
  zone.
- `actual` answers hourly unless asked otherwise with `temporalGranularity`, whose values are
  `hourly` and `15_minutes`. For a quarter-hourly day the hourly value is the mean of the four
  cleared prices, and the map at app.electricitymaps.com shows the quarter-hours: on 2026-09-10 at
  20:30 CEST, Germany was 366.57 quarter-hourly and 429.33 hourly.

The key and authenticated response values never belong in the wiki or git.

## Use in Copper Sushi

`coppersushi.data_sources.electricity_maps` fetches and locally caches the `actual` price route for
all twelve Core zones at the day's market time unit — hourly through delivery day 2025-09-30,
quarter-hourly from 2025-10-01 — and refuses an answer at any other resolution, so the CNEC view
reads one cleared price per zone and interval.

For a future forecast experiment, the Core-wide price vector is a comparison target; the German
grid forecasts are candidate inputs once their flow inconsistency is resolved. They remain outcomes
and fundamentals, not bid curves. A future zonal clearing against [JAO's domain](core-day-ahead-capacity-calculation.md)
therefore needs observed bid curves or a model of them. The 2024 backtest can take settled prices
from `actual`, but still needs another source such as energy-charts for historical generation.


### Forecast-history

Authenticated checks on 2026-10-06 returned Germany’s live 48-hour price, total-load, total-reported-load, net-load and mix forecasts. The `total-reported-load/past-range` route also returned historical reported actuals, so the September access observation is not a blanket statement about subsequent access. These actuals are not the forecasts originally issued before delivery.

The documented [reported-load forecast endpoint](https://app.electricitymaps.com/docs/reference/total-reported-load/forecast) has no past issue-time selector. `createdAt` and `updatedAt` do not retrieve superseded values. An original-run archive through another arrangement remains unconfirmed. The independent [day-ahead price forecast](price-forecasting/germany-luxembourg.md) therefore uses its own public-fundamentals inputs; current forecast access does not fill its historical demand gaps. No authenticated payloads or keys are included in the handover.

### Price-spreads

In the incident check for delivery on 2026-11-20, Electricity Maps returned all 96 quarter-hour prices in eight Core zones and none in Croatia, Hungary, Romania or Slovakia. On the same check, the [ENTSO-E Transparency Platform](https://www.entsoe.eu/data/transparency-platform/) returned Germany's prices, empty acknowledgements for Slovakia and Romania, and timeouts for Croatia and Hungary. For 2026-11-19, Electricity Maps attributed every quarter-hour in those four zones to ENTSO-E, so a direct query shared their upstream source. [Electricity Maps price API](https://app.electricitymaps.com/docs/reference/day-ahead-price)

[JAO](https://publicationtool.jao.eu/core/) published all 96 signed spreads on SI→HR, AT→HU, HU→RO and CZ→SK. Adding the CZ→SK spread to the Czech price matched all 96 [Slovak settlement prices](https://isot.okte.sk/api/v1/dam/results?deliveryDayFrom=2026-11-20&deliveryDayTo=2026-11-20) exactly. The [price recovery implementation](https://github.com/zoltanmaric/coppersushi/pull/306) uses a known zonal price as the absolute anchor.


A November 24 replay preserved the original gaps and applied JAO spreads to the eight directly observed zones. It reproduced all 384 missing zone-quarters and all 1,152 prices in the retained table. All 96 Slovak quarters matched OKTE exactly. The replay used fresh publisher responses with the original gap pattern. Its receipts establish availability on November 24. [Incident report](https://github.com/zoltanmaric/coppersushi/pull/306) · [JAO spreads](https://publicationtool.jao.eu/core/api/data/priceSpread?FromUtc=2026-11-19T23%3A00%3A00.000Z&ToUtc=2026-11-20T23%3A00%3A00.000Z&Take=100000) · [OKTE final results](https://isot.okte.sk/api/v1/dam/results?deliveryDayFrom=2026-11-20&deliveryDayTo=2026-11-20)

Reading the November 24 responses as received changed the result. Electricity Maps supplied three direct quarters in each of the four affected zones (00:00, 00:15 and 00:30 CET). Preferring those direct prices recovered the other 372 quarters from spreads. All 12 new direct prices disagreed with the retained table. In Slovakia, final settlement independently confirmed the discrepancy in all three quarters. Direct coverage alone therefore cannot establish price accuracy. [Electricity Maps actual prices](https://app.electricitymaps.com/docs/reference/day-ahead-price) · [OKTE final results](https://isot.okte.sk/api/v1/dam/results?deliveryDayFrom=2026-11-20&deliveryDayTo=2026-11-20)

All twelve disputed values were present in the raw Electricity Maps responses. Each exactly matched its own zone’s final quarter on November 19 (22:45 UTC). The three affected timestamps started at 23:00 UTC and all twelve rows had the same creation time on November 24. A direct ENTSO-E A44 query on November 24, using each bidding zone and its native quarter-hour day-ahead series, matched the retained November 20 table on all 384 quarters across Croatia, Hungary, Romania and Slovakia. The responses establish a carry-over pattern. The publisher’s processing history and the ENTSO-E edition it originally consumed remain unknown. [Electricity Maps actual prices](https://app.electricitymaps.com/docs/reference/day-ahead-price) · [ENTSO-E Transparency Platform](https://www.entsoe.eu/data/transparency-platform/) · [A44 query and series selection](../coppersushi/pipelines/market_data/data_sources/entsoe_auction_prices.py)

The November 20 map alarm preceded those late rows. The publisher first waited for JAO’s Polish alternative-price attribution. By 08:03 CET that feed had all 96 intervals, while Electricity Maps still had no prices for the four zones. The production recovery filled the missing zones from JAO spreads on both November 20 and 21 and labelled them as derived. A later independent check anchored the JAO spread paths to final Slovak prices alone and reproduced all 1,152 retained November 20 zone-quarters. [Attribution recovery](https://github.com/zoltanmaric/coppersushi/pull/305) · [Price recovery](https://github.com/zoltanmaric/coppersushi/pull/306) · [OKTE final results](https://isot.okte.sk/api/v1/dam/results?deliveryDayFrom=2026-11-20&deliveryDayTo=2026-11-20)

### Forecast-price-comparison

For DE–LU delivery on November 20, 21 and 24, the November 24 SMARD receipt at 10:01 Berlin contained zero of 96 quarters per day. The Electricity Maps receipt at 11:40 Berlin contained all 96 per day. On November 19 and 23, all 192 overlapping prices matched exactly. The Electricity Maps receipt came after the 11:00 forecast deadline, so the comparison establishes retrospective coverage only. [November 24 source comparison](https://github.com/zoltanmaric/coppersushi/blob/59a20334/wiki/electricity-maps-api.md#forecast-price-comparison)
