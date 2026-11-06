import type {DayBundle, BindingRow, MarketInterval, ElementGeometry} from './contracts';
import type {PlotlyFigure, ConstraintOption} from './figure';
import type { CoreZone } from "./reference";
import {layerAnchor} from './map-layer-order';

type Trace = PlotlyFigure["data"][number];
const purple = "#a72af5",
  lavender = "#d4a3ff",
  teal = "#3fd0ff";
const hoverlabel = {
  bgcolor: lavender,
  bordercolor: lavender,
  font: { color: "#21152d" },
};
const scale = [[0.0, "rgb(0, 155, 158)"], [0.16666666666666666, "rgb(66, 183, 185)"], [0.3333333333333333, "rgb(167, 211, 212)"], [0.5, "rgb(241, 241, 241)"], [0.6666666666666666, "rgb(228, 193, 217)"], [0.8333333333333334, "rgb(214, 145, 193)"], [1.0, "rgb(199, 93, 171)"]];
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
const hover = (r: BindingRow) =>
  `<b>${r.name}</b><br>Binding under: ${r.contingency ?? "Base case (no contingency)"}<br>Direction: ${r.direction}<br>RAM: ${r.ram === null ? "n/a" : number(r.ram, 0) + " MW"}<br>Capacity: ${r.capacity === null ? "n/a" : number(r.capacity, 0) + " MW"}<br>Shadow price: ${number(r.shadow_price)} €/MWh`;

/** Normalized-FB contribution; missing inputs remain unavailable. */
export function contributions(
  interval: MarketInterval,
  id: number,
  reference: CoreZone,
): Partial<Record<CoreZone, number>> | null {
  const cap = interval.caps.find((r) => r.source_id === id);
  if (cap)
    return Object.fromEntries(
      Object.keys(interval.prices).map((z) => [
        z,
        cap.delta * ((z === "PL" ? 1 : 0) - (reference === "PL" ? 1 : 0)),
      ]),
    );
  const row = interval.constraints.find((r) => r.source_id === id),
    alpha = interval.alpha;
  if (
    !row ||
    alpha === null ||
    !(alpha > 0 && alpha <= 1) ||
    row.ptdfs[reference] === undefined
  )
    return null;
  return Object.fromEntries(
    Object.entries(row.ptdfs).map(([z, p]) => [
      z,
      (-row.shadow_price * (p - row.ptdfs[reference]!)) / alpha,
    ]),
  );
}

export function optionsFor(interval: MarketInterval): ConstraintOption[] {
  return [
    ...interval.constraints.map((r) => ({
      ...r,
      source: "constraints" as const,
    })),
    ...interval.caps.map((r) => ({ ...r, source: "attribution" as const })),
  ]
    .sort((a, b) => b.shadow_price - a.shadow_price)
    .map((r) => ({
      value: String(r.source_id),
      source: r.source,
      label: r.name,
    }));
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
  selected: number | null,
  reference: CoreZone,
  layout: PlotlyFigure["layout"],
  geojson: ReturnType<typeof zoneFeatures>,
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
      colorscale: scale,
      marker: {
        opacity: 0.6,
        line: { color: "rgba(255,255,255,0.55)", width: 1.2 },
      },
      ...(below ? { below } : {}),
      hoverinfo: "skip",
      showscale: false,
    },
  ];
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
      hitIds.push([group.map((r) => r.source_id).join(",")]);
      hitText.push(group.map(hover).join("<br><br>"));
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
          text: values.map((rs) => rs.map(hover).join("<br><br>")),
          customdata: values.map((rs) => [
            rs.map((r) => r.source_id).join(","),
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
  const chosen = rows.find((r) => r.source_id === selected);
  if (chosen) {
    const g = bundle.elements[chosen.geometry!];
    if (g.kind === "line")
      traces.push(
        line(
          "selected CNEC",
          g.endpoints.map((p) => p[0]),
          g.endpoints.map((p) => p[1]),
          4,
          { effect: "line" },
        ),
      );
    else {
      const p = point(g);
      symbols.push(
        scatter("selected CNEC", [p[0]], [p[1]], {
          mode: "markers",
          marker: {
            symbol: "transformer-selected",
            size: 10,
            angle: 0,
            allowoverlap: true,
          },
          hoverinfo: "skip",
          meta: { role: "binding-symbol", effect: "transformer" },
        }),
      );
    }
  }
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
      selected === cap.source_id ? 4 : 2.5,
      { role: "country-cap", ambient: true },
    );
    traces.push(
      halo(outline),
      outline,
      scatter("select country cap", x, y, {
        mode: "markers",
        marker: { size: 14, color: "rgba(128,80,255,0.01)" },
        customdata: x.map(() => [String(cap.source_id)]),
        text: x.map(
          () =>
            `${cap.name}<br>Net ${cap.direction} limit: ${number(cap.capacity, 0)} MW<br>Cap shadow price: ${number(cap.shadow_price)} €/MWh`,
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
      labels: string[] = [],
      hovers: string[] = [],
      backgrounds: string[] = [];
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
        const observed = interval.prices[z.zone]! - interval.prices[reference]!;
        const text = `<b>Spread: ${z.zone} − ${reference}</b><br>This constraint’s contribution: ${signed(value)} /MWh<br>Total observed spread: ${signed(observed)} /MWh<br>Remainder (other constraints / source precision): ${signed(observed - value)} /MWh`;
        const color = value < 0 ? teal : purple,
          bg = value < 0 ? String(scale[0][1]) : lavender;
        traces.push(
          scatter(`${z.zone} ray`, xs, ys, {
            mode: "lines+markers",
            line: { color, width: 4.2 },
            marker: {
              size: xs.map((_, i) => (i === 0 || i === 23 ? 4.2 : 0)),
              color,
            },
            opacity: 0.48,
            hoverinfo: "text",
            hovertext: text,
            hoverlabel: { ...hoverlabel, bgcolor: bg, bordercolor: bg },
          }),
        );
        labelX.push(xs[12]);
        labelY.push(ys[12]);
        labels.push(signed(value));
        hovers.push(text);
        backgrounds.push(bg);
      }
    traces.push(
      scatter("ray contributions", labelX, labelY, {
        mode: "text",
        text: labels,
        textposition: "middle center",
        marker: { symbol: "circle" },
        textfont: { color: "white", size: 12 },
        hoverinfo: "text",
        hovertext: hovers,
        hoverlabel: {
          ...hoverlabel,
          bgcolor: backgrounds,
          bordercolor: backgrounds,
        },
      }),
    );
  }
  traces.push(
    ...symbols,
    scatter(
      "zone prices",
      zones.map((z) => z.centre[0]),
      zones.map((z) => z.centre[1]),
      {
        mode: "text",
        text: zones.map(
          (z) => `${z.name}<br>€${number(interval.prices[z.zone]!)}`,
        ),
        customdata: zones.map((z) => ["zone", z.zone]),
        hoverinfo: "none",
        marker: { symbol: "circle" },
        textfont: { color: "white", size: 14 },
      },
    ),
  );
  const anchored = Array.isArray(layers) && layers.some(layer =>
    (layer as {id?: unknown}).id === layerAnchor('published day-ahead price'));
  for (const trace of traces) {
    trace.uid = Array.from(String(trace.name), c => c.codePointAt(0)!.toString(16)).join('-');
    if (anchored) trace.below = layerAnchor(String(trace.name), trace.mode);
  }
  return { data: traces, layout };
}
