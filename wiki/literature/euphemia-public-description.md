# EUPHEMIA public description

**Issued by** the NEMO Committee, the nominated electricity market operators (power exchanges) that own and operate the single day-ahead coupling algorithm; developed by N-SIDE. Edition of 18 December 2025: [PDF, 90 pages](https://www.nemo-committee.eu/assets/files/euphemia-public-description.pdf). Mandated by the algorithm methodology (ACER Decision 04/2020, Article 4.18). The document's copyright notice forbids reproduction, so this page paraphrases and does not quote.

**Draws on it:** [flow-based-market-coupling](../flow-based-market-coupling.md), [core-capacity-calculation](../core-capacity-calculation.md), [specs/core-congestion-forecast](../specs/core-congestion-forecast.md).

## What it settles

**The objective.** EUPHEMIA picks which orders execute and at which zonal prices so that economic surplus, the sum of consumer surplus, producer surplus and congestion rent, is maximal, while the net positions respect the network constraints the TSOs supplied. The grid is an input; the algorithm computes nothing about it.

**Two network models, both zonal.** ATC borders are pipes with capacity per direction, optional losses, tariffs and ramping limits. Flow-based regions are the linear constraint PTDF · net positions ≤ RAM, one row per element, one column per hub. Since version 10.5 the flow-based region can be handed the untouched domain and the long-term-allocation domain separately (extended LTA inclusion); EUPHEMIA respects their union itself, which cut Core's daily constraint count from a projected 27,000 to under 800. External constraints cap a zone's net position. Below the zone, scheduling areas and NEMO trading hubs exist only for disaggregation; all orders in a zone clear at one price.

**Non-intuitive flows are allowed.** A flow-based solution can export from a dearer zone to a cheaper one when that relieves a binding element and enables larger trades elsewhere. A bilateral-intuitiveness mode that forbids this exists but is a configuration, not the default consequence of the maths.

**Orders.** Aggregated hourly and quarter-hourly curves, block orders (fill-or-kill, linked, exclusive, curtailable, flexible), complex orders with minimum-income conditions, scheduled stops and load gradients (Iberia), merit and PUN orders (Italy). Blocks and minimum-income conditions need binary variables; merit and PUN orders need strict consecutiveness.

**The algorithm.** A master surplus-maximisation problem over the block and complex selections, solved by branch and cut, then three sub-problems: price determination (are there zonal prices consistent with the selection, with no paradoxically accepted block, and with the primal-dual relations on flows holding?), PUN search, and volume indeterminacy (curtailment sharing, volume maximisation, merit-order enforcement, flow decomposition). An infeasible sub-problem adds a cut to the master and the search resumes. Prices are duals of the fixed-selection problem; complementary slackness is checked explicitly: two zones price apart only when every path between them is saturated. The run stops at a time limit of about 12 minutes; the best solution so far is published, and the document says optimality is not guaranteed because heuristics are used.

**Solution quality** is graded by constraint violations against two tolerance levels; a violation past the decoupling level fails the session. A partially decoupled Core zone is priced at the average of its neighbours, at the Core TSOs' request.

**History.** Built from COSMOS (CWE, 2010); first production run February 2014; CWE flow-based May 2015; Core flow-based and the Croatian-Hungarian border 8 June 2022; 15-minute market time unit since delivery day 1 October 2025.

## What it leaves open

The document describes structure, not parameters: no tolerances, no cut strategies in detail, no per-region configuration. Annex C gives the mathematical formulation of the master and price problems and the flow models; Annex B lists heuristics.
