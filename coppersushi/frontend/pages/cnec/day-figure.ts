import {contributions} from './market/contributions';
import type {DayBundle, BindingRow, MarketInterval, ElementGeometry} from './data/contracts';
import type {PlotlyFigure} from '../../map/figure';
import type { CoreZone } from "./market/reference";
import {layerAnchor} from '../../map/map-layer-order';
import {PRICE_COLORSCALE} from '../../map/price-scale';

export function reserveTooltip(interval: MarketInterval): string {
  const evidence = interval.polish_upward_reserves;
  if (!evidence) return '<br>Upward reserves: unavailable';
  const reasons = {missing: 'no record', incomplete: 'incomplete products', late: 'no publication before cutoff', ambiguous: 'conflicting versions', fetch_failed: 'source unavailable'};
  const format = new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/Brussels', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'});
  return ([['Required upward capacity', evidence.required], ['Purchased before submission target', evidence.purchased]] as const).map(([label, value]) => {
    if (value.status !== 'available') return `<br>${label}: unavailable (${reasons[value.status]})`;
    return `<br>${label}: ${number(value.mw!, 0)} MW<br>Published ${format.format(new Date(value.published_at!))}`;
  }).join('') + '<br>Cutoff: 10:30 Brussels on D−1.<br>Matching totals alone does not establish that the cap was unnecessary.';
}

type Trace = PlotlyFigure["data"][number];
const purple = "#a72af5",
  lavender = "#d4a3ff",
  teal = "#3fd0ff";
const hoverlabel = {
  bgcolor: lavender,
  bordercolor: lavender,
  font: { color: "#21152d" },
};
const number = (n: number, digits = 2) =>
  n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
const signed = (n: number) => `${n < 0 ? "−" : "+"}€${number(Math.abs(n))}`;
const scatter = (
  name: string,
  lon: (number | null)[],
  lat: (number | null)[],
  rest: Trace,
): Trace => ({
  type: "scattermapbox",
  uid: name,
  name,
  lon,
  lat,
  showlegend: false,
  ...rest,
});
const line = (
  name: string,
  lon: (number | null)[],
  lat: (number | null)[],
  width: number,
  meta = {},
): Trace =>
  scatter(name, lon, lat, {
    mode: "lines",
    hoverinfo: "skip",
    line: { color: purple, width },
    meta,
  });
const halo = (trace: Trace): Trace => ({
  ...trace,
  uid: `${trace.name} glow`,
  name: `${trace.name} glow`,
  opacity: 0.3,
  line: {
    ...(trace.line as object),
    width: Number((trace.line as { width: number }).width) * 3,
    color: lavender,
  },
  meta: {},
});
const point = (g: ElementGeometry) => [
  (g.endpoints[0][0] + g.endpoints[1][0]) / 2,
  (g.endpoints[0][1] + g.endpoints[1][1]) / 2,
];
const bearing = (g: ElementGeometry) => {
  const [[x0, y0], [x1, y1]] = g.endpoints;
  const mercator = (y: number) =>
    (Math.log(Math.tan(((45 + y / 2) * Math.PI) / 180)) * 180) / Math.PI;
  return (
    ((Math.atan2(x1 - x0, mercator(y1) - mercator(y0)) * 180) / Math.PI + 360) %
    360
  );
};
const constraintTooltip = (r: BindingRow, compact: boolean) =>
  `<b>${r.name}</b>${compact ? "" : `<br>Binding under: ${r.contingency ?? "Base case (no contingency)"}`}<br>RAM: ${r.ram === null ? "n/a" : number(r.ram, 0) + " MW"} · Capacity: ${r.capacity === null ? "n/a" : number(r.capacity, 0) + " MW"}<br>Shadow price: ${number(r.shadow_price)} €/MWh`;

export function selectionIds(interval: MarketInterval): string[] {
  return [...new Set([...interval.constraints.map(r=>r.eic), ...interval.caps.map(()=>'cap:PL')])];
}

/** Stable geographic data, constructed once per loaded day. */
export function zoneFeatures(bundle: Pick<DayBundle, 'zones'>) {
  return {
    type: "FeatureCollection",
    features: bundle.zones.map((z) => ({
      type: "Feature",
      id: z.zone,
      properties: {},
      geometry: { type: "MultiPolygon", coordinates: z.rings.map((r) => [r]) },
    })),
  };
}

export function dayFigure(
  bundle: DayBundle,
  index: number,
  selected: string | null,
  reference: CoreZone,
  layout: PlotlyFigure["layout"],
  geojson: ReturnType<typeof zoneFeatures>,
  compactTooltips = false,
): PlotlyFigure {
  const interval = bundle.intervals.find((i) => i.index === index);
  if (!interval) throw new Error("Interval is outside the selected day");
  const zones = bundle.zones.filter(
    (z) => interval.prices[z.zone] !== undefined,
  );
  const style = layout.mapbox.style;
  const layers =
    style && typeof style === "object" && !Array.isArray(style)
      ? (style as { layers?: unknown[] }).layers
      : null;
  const below = Array.isArray(layers)
    ? (layers.at(-1) as { id: string })?.id
    : undefined;
  const traces: Trace[] = [
    {
      type: "choroplethmapbox",
      uid: "prices",
      name: "published day-ahead price",
      geojson,
      locations: zones.map((z) => z.zone),
      z: zones.map((z) => interval.prices[z.zone]!),
      zmin: bundle.price_range[0],
      zmax: bundle.price_range[1],
      zauto: false,
      colorscale: PRICE_COLORSCALE,
      marker: {
        opacity: 0.6,
        line: { color: "rgba(255,255,255,0.55)", width: 1.2 },
      },
      ...(below ? { below } : {}),
      hoverinfo: "skip",
      showscale: false,
    },
  ];
  const assetHover = (rows: BindingRow[]) => {
    const ids = new Set(rows.map(r=>r.eic));
    return interval.constraints.filter(r=>ids.has(r.eic)).map(r=>constraintTooltip(r, compactTooltips)).join('<br><br>');
  };
  const rows = interval.constraints.filter((r) => r.geometry !== null);
  const lines = rows.filter(
    (r) => bundle.elements[r.geometry!].kind === "line",
  );
  const unique = [
    ...new Map(
      lines.map((r) => [
        bundle.elements[r.geometry!].branch_id,
        bundle.elements[r.geometry!],
      ]),
    ).values(),
  ];
  const lon = unique.flatMap((g) => [
    g.endpoints[0][0],
    g.endpoints[1][0],
    null,
  ]);
  const lat = unique.flatMap((g) => [
    g.endpoints[0][1],
    g.endpoints[1][1],
    null,
  ]);
  const core = line("market-binding CNECs", lon, lat, 2.5, { ambient: true });
  traces.push(
    halo(core),
    core,
    scatter(
      "binding line ends",
      unique.flatMap((g) => g.endpoints.map((p) => p[0])),
      unique.flatMap((g) => g.endpoints.map((p) => p[1])),
      {
        mode: "markers",
        hoverinfo: "skip",
        marker: { color: purple, size: 6, symbol: "circle" },
      },
    ),
  );
  const hitX: number[] = [],
    hitY: number[] = [],
    hitIds: string[][] = [],
    hitText: string[] = [];
  for (const g of unique) {
    const group = lines.filter(
      (r) => bundle.elements[r.geometry!].branch_id === g.branch_id,
    );
    for (let i = 0; i <= 40; i++) {
      const t = i / 40;
      hitX.push(g.endpoints[0][0] * (1 - t) + g.endpoints[1][0] * t);
      hitY.push(g.endpoints[0][1] * (1 - t) + g.endpoints[1][1] * t);
      hitIds.push([[...new Set(group.map((r) => r.eic))].join(",")]);
      hitText.push(assetHover(group));
    }
  }
  traces.push(
    scatter("select line", hitX, hitY, {
      mode: "markers",
      marker: { size: 16, color: "rgba(128,80,255,0.01)" },
      customdata: hitIds,
      text: hitText,
      hoverinfo: "text",
      hoverlabel,
    }),
  );
  const symbols: Trace[] = [];
  for (const kind of ["line", "transformer"]) {
    const groups = new Map<string, BindingRow[]>();
    for (const r of rows) {
      const g = bundle.elements[r.geometry!];
      if (g.kind !== kind) continue;
      const angle =
        kind === "line"
          ? (bearing(g) + (r.direction === "DIRECT" ? 0 : 180)) % 360
          : 0;
      const key = JSON.stringify([...point(g), angle]);
      groups.set(key, [...(groups.get(key) ?? []), r]);
    }
    const points = [...groups.keys()].map((k) => JSON.parse(k) as number[]),
      values = [...groups.values()];
    symbols.push(
      scatter(
        kind === "line" ? "binding rows" : "binding transformers and PSTs",
        points.map((p) => p[0]),
        points.map((p) => p[1]),
        {
          mode: "markers",
          meta: { role: "binding-symbol" },
          text: values.map((rs) => assetHover(rs)),
          customdata: values.map((rs) => [
            [...new Set(rs.map((r) => r.eic))].join(","),
          ]),
          hoverinfo: "text",
          hoverlabel,
          marker: {
            color: purple,
            size: kind === "line" ? 8 : 10,
            symbol: kind === "line" ? "triangle" : "transformer",
            angle: points.map((p) => p[2]),
            allowoverlap: true,
          },
        },
      ),
    );
  }
  const chosenRows = [...new Map(rows.filter(r => r.eic === selected).map(r => [r.geometry,r])).values()];
  const selectedX: (number|null)[] = [], selectedY: (number|null)[] = [];
  const transformerX: number[] = [], transformerY: number[] = [];
  for (const chosen of chosenRows) {
    const g = bundle.elements[chosen.geometry!];
    if (g.kind === "line") {
      selectedX.push(...g.endpoints.map(p=>p[0]),null);
      selectedY.push(...g.endpoints.map(p=>p[1]),null);
    }
    else {const p = point(g);transformerX.push(p[0]);transformerY.push(p[1]);}
  }
  if (transformerX.length) symbols.push(scatter('selected CNEC',transformerX,transformerY,{
    mode:'markers',marker:{symbol:'transformer-selected',size:10,angle:0,allowoverlap:true},
    hoverinfo:'skip',meta:{role:'binding-symbol',effect:'transformer'},
  }));
  if (selectedX.length) traces.push(line('selected CNEC',selectedX,selectedY,4,{effect:'line'}));
  for (const cap of interval.caps) {
    const pl = bundle.zones.find((z) => z.zone === "PL");
    if (!pl) continue;
    const x: (number | null)[] = [],
      y: (number | null)[] = [];
    for (const ring of pl.rings) {
      for (let i = 0; i < ring.length - 1; i++) {
        const a = ring[i],
          b = ring[i + 1],
          n = Math.max(
            1,
            Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 0.05),
          );
        for (let j = 0; j < n; j++) {
          x.push(a[0] + ((b[0] - a[0]) * j) / n);
          y.push(a[1] + ((b[1] - a[1]) * j) / n);
        }
      }
      x.push(ring.at(-1)![0], null);
      y.push(ring.at(-1)![1], null);
    }
    const outline = line(
      "binding country cap",
      x,
      y,
      selected === 'cap:PL' ? 4 : 2.5,
      { role: "country-cap", ambient: true },
    );
    traces.push(
      halo(outline),
      outline,
      scatter("select country cap", x, y, {
        mode: "markers",
        marker: { size: 14, color: "rgba(128,80,255,0.01)" },
        customdata: x.map(() => ['cap:PL']),
        text: x.map(
          () =>
            `${cap.name}<br>Net ${cap.direction} limit: ${number(cap.capacity, 0)} MW<br>Cap shadow price: ${number(cap.shadow_price)} €/MWh${cap.direction === "export" ? reserveTooltip(interval) : ""}`,
        ),
        hoverinfo: "text",
        hoverlabel,
        meta: { role: "country-cap" },
      }),
    );
  }
  if (selected !== null) {
    const values = contributions(interval, selected, reference),
      origin = zones.find((z) => z.zone === reference);
    const labelX: number[] = [],
      labelY: number[] = [],
      labels: string[] = [];
    if (values && origin)
      for (const z of zones) {
        const value = values[z.zone];
        if (value === undefined || Math.abs(value) <= 1e-9) continue;
        const [x0, y0] = origin.centre,
          [x1, y1] = z.centre;
        const cy =
          (y0 + y1) / 2 +
          0.18 *
            Math.hypot(
              (x1 - x0) * Math.cos((((y0 + y1) / 2) * Math.PI) / 180),
              y1 - y0,
            );
        const xs: number[] = [],
          ys: number[] = [];
        for (let i = 0; i < 24; i++) {
          const t = i / 23;
          xs.push(x0 * (1 - t) + x1 * t);
          ys.push((1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1);
        }
        const color = value < 0 ? teal : purple;
        traces.push(
          scatter(`${z.zone} ray`, xs, ys, {
            mode: "lines+markers",
            line: { color, width: 4.2 },
            marker: {
              size: xs.map((_, i) => (i === 0 || i === 23 ? 4.2 : 0)),
              color,
            },
            opacity: 0.48,
            hoverinfo: "skip",
          }),
        );
        labelX.push(xs[12]);
        labelY.push(ys[12]);
        labels.push(signed(value));
      }
    // Plotly cannot dispose an unrendered symbol layer when selection expires.
    // Do not introduce a temporary empty label trace between those two states.
    if (labels.length) traces.push(
      scatter("ray contributions", labelX, labelY, {
        mode: "text",
        text: labels,
        textposition: "middle center",
        marker: { symbol: "circle" },
        textfont: { color: "white", size: 12 },
        hoverinfo: "skip",
      }),
    );
  }
  traces.push(...symbols);
  const anchored = Array.isArray(layers) && layers.some(layer =>
    (layer as {id?: unknown}).id === layerAnchor('published day-ahead price'));
  for (const trace of traces) {
    trace.uid = Array.from(String(trace.name), c => c.codePointAt(0)!.toString(16)).join('-');
    if (anchored) trace.below = layerAnchor(String(trace.name), trace.mode);
  }
  return { data: traces, layout };
}
