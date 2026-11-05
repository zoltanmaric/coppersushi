# Observed spread reconciliation

Twelve quarter-hours selected from six audited days in 2026. `selection.json`
records why each interval was retained; selection was based on constraint coverage
and known failures, not on whether prices reconcile.

JAO physical rows and country PTDFs come from the Core
`activeFbConstraints` publication. Context combines Core `alphaFactor`,
`allocationConstraint`, `netPos`, and Cross-CCR `DA_PL_AC`. Cached responses were
filtered and converted using the application's adapters, without changing values.
The November rows come from the existing normalized cache. `PL_ALT` quarter-hours
use the adapter's ID ordering and independent position cross-check.

Sources:
- https://publicationtool.jao.eu/core/
- https://publicationtool.jao.eu/crossCCR/

Prices: Bundesnetzagentur | SMARD.de, retrieved through Fraunhofer ISE's
Energy-Charts API on 2026-11-04. `price-sources.json` records the request URLs and
returned licence labels. Only series labelled CC BY 4.0 are included. Values are
unaltered; the selection and CSV format are adaptations. Licence:
https://creativecommons.org/licenses/by/4.0/

SMARD's current notice asks users not to reuse wholesale prices while HEDWIG
licensing is reviewed. This fixture proceeds on the research-use interpretation
of the draft, not a claim that unrestricted redistribution is settled:
https://www.smard.de/home/datennutzung and
https://www.bundesnetzagentur.de/1067894 . JAO's data also remain subject to its
source terms; these observations are not relicensed under the repository's code licence.

The tests sum normalized physical contributions and the validated Polish cap.
Interface bounds are excluded from this Core-country decomposition.
LTA decomposition is not tested here. Poland's observed price enters its inferred cap term, so
its comparison is not fully independent. The empirical tolerance is EUR 0.02/MWh.

A separate local audit covered all 66 Core country pairs in all 576 quarter-hours
of September 12, 17, 24, 25, October 8 and November 3. With a 0.11 MW cap-saturation
tolerance, all 38,016 comparisons passed (maximum EUR 0.013844/MWh). The previous
0.051 MW guard failed 67 intervals, with a maximum EUR 165.140268/MWh error.
Those audit prices came from Electricity Maps and are not included here.

Checked-in price coverage is AT, BE, CZ, DE-LU, FR, HU, NL, PL and SI (36 pairs).
HR, RO and SK responses explicitly restrict external use and are excluded.
All 12 Core PTDF columns remain available, allowing every reference choice.
