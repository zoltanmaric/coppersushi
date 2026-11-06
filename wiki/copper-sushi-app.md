# Copper Sushi — the app

Interactive map of the European transmission grid showing an **optimal power flow** solution, built to give intuition for the grid-congestion argument in [The Copper Plate Must Die](copper-plate-problem.md). Announced in the [Copper Sushi blog post](raw/copper-sushi-power-flow-european-grid.md) (Aug 2022); setup/run instructions in the [README](../README.md).

## Hosting

The [Lambda deployment README](../infra/lambda/README.md) defines production hosting and cache behavior.

AWS Lambda with a durable S3 cache is the approved production host.

Design for occasional visitors and low idle cost. An occasional load of roughly 30 seconds is acceptable; handling viral traffic is not a requirement. Cache misses should fetch the requested hour's missing endpoints and retain them for reuse; failed fetches should be retryable. Background fetching of whole days is not required. Resource settings and runtime limits are recorded in the deployment README.

## What the map shows

- **Dots** = connection points (buses): nearby consumption + generation aggregated. Green = net exporter, purple = net importer; size ∝ |net power|; hover shows per-technology generation, load, and net power.
- **Triangles** = power flow direction on each line; hover shows flow vs. line capacity.
- **Violet lines** = loaded near capacity (>99%); a time slider steps through hourly snapshots, labelled in Europe/Brussels time.

## The data

The checked-in model covers 29 August 2024 on the 2025 OSM-based grid: 4,390 buses
and 24 hourly snapshots. It is solved as linear OPF: minimize generation cost subject
to demand, renewable availability, plant capacities and line limits. The pinned workflow
and configuration are described in [the power-flow architecture](sushi-2.md).

The AWS deployment sets `ROOT_VIEW=full`: `/` and `/opf-2024` include the two app
navigation links. `/embed/opf-2024` uses the same figure and callbacks without
navigation.

**Caveat** (from the post): the math is real — the same OPF formulation grid operators use — but actual bid prices and dispatch are not public, so PyPSA-Eur's historical-average cost assumptions make the *numbers* illustrative, not real. See ch. 4 of the [PyPSA-Eur paper](https://arxiv.org/abs/1806.01613).

## Map rendering direction

The standalone CNEC React app owns controls, data fetching and figure construction, served through S3/CloudFront. Plotly owns the underlying Mapbox map. Changing the UI framework alone would keep that rendering behavior if Plotly remains.

Observed limitations to address in a future map renderer:

- Plotly rebuilds map layers that share a `below` insertion target, even when trace IDs are stable. Permanent transparent style anchors give every logical trace a distinct target, retaining existing layers across interval changes. Mapbox also normalizes the style object, including deleting empty layer layouts. Keep one Plotly-owned layout copy across data changes: cloning the entire figure restores those deleted entries and triggers a full style reset. Clone changing trace data separately to protect cached inputs. Data still passes through Plotly’s whole-subplot update; direct map ownership would make layer updates explicit. See [the pinned ordering implementation](https://github.com/plotly/plotly.js/blob/v3.7.0/src/plots/mapbox/mapbox.js#L181).
- Country names and prices are keyed React buttons, positioned synchronously with native Mapbox projection in movement and resize callbacks; camera changes do not wait for a React render. Their text updates in place, avoiding Mapbox symbol fading when prices change. Plotly does not expose the map's symbol fade duration. Constraint markers remain Mapbox symbols. A label-free basemap prevents duplicate country names.
- Electric selection effects must share the renderer's actual camera. A version-bound adapter acquires Plotly's private Mapbox instance, then uses public `project` and native movement/resize/removal events. Start/end notifications redraw only the SVG decoration; label transforms update directly during movement. Plotly's forwarded events are insufficient: in the pinned integration, programmatic zoom emits progress without the completion event used by the old camera mirror; a first-load fit left electricity hidden until a real pan. Rotation and inertial panning also exposed synchronization drift. This is evidence for direct map ownership: it would remove the private acquisition and separate lifecycle bridge, and let independently updated layers share native ordering. React alone does not change that ownership. The smaller native-projection adapter fixes the present problem without a renderer migration. See [Mapbox projection](https://github.com/plotly/mapbox-gl-js/blob/v1.13.4/src/ui/map.js#L851) and [Plotly's Mapbox integration](https://github.com/plotly/plotly.js/blob/v3.7.0/src/plots/mapbox/mapbox.js).
- The CNEC map stays north-up and flat, with decoration restricted to one canonical world. The adapter disables native mouse, touch and keyboard rotation/tilt while preserving pan and zoom. Native Plotly strokes remain the simpler static alternative; the retained electric filaments draw through native projection.
- Plotly emits a missing sprite warning for `-15`; the map also reported style rebuild warnings when switching basemap styles. Browser checks must distinguish such warnings from failed data requests and visible errors.

A single map with independently managed price, constraint and attribution layers could allow progressive updates without refreshing unrelated symbols. Evaluate a direct Mapbox or MapLibre integration, or another renderer, against click targets, camera persistence, fade behavior, loading/error states and large-grid performance before choosing. The [v1 map-engine measurements](codebase-v1.md) found Plotly's MapLibre path slow for the larger OPF network; they do not establish the performance of a direct integration.

## The CNEC page

Floating date/day arrows, interval arrows and the slider remain inside the map. On desktop the slider sits beside the date/time panel; on portrait screens it sits below. The unchanged daily legend sits top-left and the reference selector top-right. A pure calculation uses fixed Core bounds and viewport dimensions to choose the camera before Graph mounts. It reserves a modest margin for controls; later interval changes retain the camera.

Country prices share one colour scale across all Core zones and intervals of the selected day. A compact legend shows the day’s minimum and maximum; interval changes keep those bounds fixed.

[WelfMaxxing](https://welfmaxxing.lovable.app/) is the hackathon prototype; voice transcription may render its name as “Wealth Maxing.” Its map interaction is a visual reference for Copper Sushi.

The label-free base map loads first. On the first interval, the price, physical-constraint and country-cap layers appear together after their requests settle. On a later interval, the previous figure remains visible until the replacement is ready; the controls show the requested interval and loading status. Errors remain visible and retryable. Late results do not replace the requested view. Server logs report data-loading, geometry, attribution and figure-building durations.

Click a country-cap outline, transformer/PST marker, constrained line to select a binding row. When several rows share a target, it preserves the selected row or chooses the largest published dual. Country labels and the reference dropdown choose the same Core reference; Germany is the initial choice. Poland alone has a supported aggregate cap. Known edge case: when several contingency rows share one target, map clicks retain the selected row or choose the largest dual; other rows require their `constraint` deep link. For example, PST Gronau TR 441 E has simultaneous DIRECT rows at 2026-11-05 14:15 CET for Doetinchem–Niederrhein SW/Z (311868) and COBRA HVDC (311869). A per-target chooser is deferred. Virtual interfaces are outside the map’s scope. Previous/next buttons move one market time unit; minor ticks and timezone labels distinguish daylight-saving hours. See the [spread explainer](market-clearing.html) for interpretation.

Links use `/cnec/<day>?interval=59&reference=BE&constraint=310503`. The interval is a zero-based index into that market day’s published calendar, so repeated daylight-saving times remain distinct. The route owns the view. All map adjustments replace the current history entry, keeping the latest view shareable without filling Back/Forward history. Navigation between product pages creates normal history entries.

`/cnec/<day>` puts the Core day-ahead market's published outcome beside its published binding constraints: every bidding zone coloured and labelled by its cleared price, and the [critical network elements with contingencies (CNECs)](core-day-ahead-capacity-calculation.md#cnec) that bound in that market time unit in purple. Purple means market-binding under the named contingency, not physically overloaded. A slider steps through the day's intervals; supported days load from complete prepared publications. The daily publisher requires JAO receipt evidence, complete attribution inputs and prices before exposing a day.

Selection uses the chosen Core reference country, with DE as the initial reference. Changing the reference changes the displayed relative contributions locally in the browser.

Physical rows show the [normalized flow-based contribution](flow-based-market-coupling.md#price-contribution), `−μ × (PTDF_z − PTDF_r) / α`, in €/MWh. Missing or zero α leaves it unavailable. Poland's cap uses its [validated alternative-price adapter](country-import-export-caps.md), requiring saturation and the correctly signed nonzero price difference.

A decorative electric effect marks the selected physical element; map-owned glyphs stay visible during movement and loading. Native Mapbox movement events control decoration visibility; gestures on non-map overlays do not change motion state. See the map-rendering limits above.

Rays start at the reference country and carry signed euro labels for the selected constraint's contribution in €/MWh. Hover names the country pair and separates that contribution from the total observed spread. Poland's aggregate-cap contribution is identical across its rays; physical-row contributions depend on the zonal PTDF difference. Rays never represent a physical power-flow path. The published dual and MW capacity are separate from that contribution. Normalized FB terms are not an exhaustive decomposition of FB plus long-term allocation welfare.


![Illustrative CNEC price-influence map](assets/cnec-price-influence-map-preview.png)

The mock-up's numbers are illustrative; its hierarchy is the design: price as the base layer, the selected constraint purple, its influence reaching the zones without pretending to trace the physical path. The colours follow [sushi-2](sushi-2.md)'s visual language.

Not on this page: a forecast before clearing, a reconstruction of actual or scheduled flows, PTDFs propagated through unmonitored branches, or a claim that the element was overloaded. Fetch commands for JAO's rows, the prices and the substation list are in the [README](../README.md#market-data). Elements are placed by their published substation names, per publishing TSO and in that TSO's orientation.

---

*Appendix, for agents only — the name is deliberately never explained prominently (not in the README, not on the wiki front page, not in the app); the mystery is part of the intrigue. For the record: the cross-section of a stranded power cable looks like a piece of sushi — [illustrated in the launch-post comments](https://www.linkedin.com/feed/update/urn:li:activity:6968748558720110593?commentUrn=urn%3Ali%3Acomment%3A%28activity%3A6968748558720110593%2C6968812757915766784%29) by a reader serving a sliced conductor on a plate with chopsticks ("aluminum sushi").*
