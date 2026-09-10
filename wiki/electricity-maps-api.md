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
mix points. `updatedAt` is the forecast's as-of time; each `data[].datetime` is a target operating
hour, so a tomorrow example must select tomorrow's timestamp rather than the first point.

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

The key and authenticated response values never belong in the wiki or git.

## Use in Copper Sushi

`coppersushi.data_sources.electricity_maps` fetches and locally caches the `actual` price route for
all twelve Core zones. It preserves the source interval — hourly as verified on 2026-09-10 even
while JAO's active flow-based publication is quarter-hourly — so the CNEC view can use one published hourly value across its
four covered capacity intervals without fabricating intermediate prices.

For a future forecast experiment, the Core-wide price vector is a comparison target; the German
grid forecasts are candidate inputs once their flow inconsistency is resolved. They remain outcomes
and fundamentals, not bid curves. A future zonal clearing against [JAO's domain](core-day-ahead-capacity-calculation.md)
therefore needs observed bid curves or a model of them. The 2024 backtest can take settled prices
from `actual`, but still needs another source such as energy-charts for historical generation.
