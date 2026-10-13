"use strict";
(() => {
  const D = window.FORECAST;
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => (n == null ? "unavailable" : Number(n).toFixed(2));
  const pct = (n) => (n == null ? "unavailable" : `${(n * 100).toFixed(1)}%`);
  const names = {
    system: "Automatic selection (with fallbacks)",
    reference: "Yesterday / last-week reference",
    prices: "Price-history model",
    weather: "Price-history + weather model",
    demand: "Price-history + weather + demand model",
  };
  const ns = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, parent, text) {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    parent.append(e);
    return e;
  }
  function el(tag, text, cls) {
    const e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  function definition(parent, key, value) {
    parent.append(el("dt", key), el("dd", String(value)));
  }
  function option(parent, value, text) {
    const o = el("option", text);
    o.value = value;
    parent.append(o);
  }
  try {
    if (!D || D.schema_version !== 1)
      throw Error(
        "No supported export loaded. Generate this website with python -m forecasts.explain.",
      );
    let index = 0,
      quarterIndex = 0,
      node = "features";
    let sortKey = null, sortDirection = 1;
    let minimum = Infinity, maximum = -Infinity;
    for (const day of D.days) {
      for (const point of day.points) {
        const values = Object.values(point.q).flat();
        if (point.actual != null) values.push(point.actual);
        for (const value of values) {
          minimum = Math.min(minimum, value);
          maximum = Math.max(maximum, value);
        }
      }
    }
    const padding = Math.max((maximum - minimum) * 0.08, 1);
    const priceScale = { low: minimum - padding, high: maximum + padding };
    const params = new URLSearchParams(location.hash.split("?")[1] || "");
    if (params.has("day")) {
      const i = D.days.findIndex((d) => d.date === params.get("day"));
      if (i >= 0) index = i;
    }
    if (params.has("method") && Object.hasOwn(names, params.get("method")))
      $("method").value = params.get("method");
    for (const m of Object.keys(D.report.breakdowns.month))
      option($("period"), m, m);
    function visibleIndices() {
      return D.days.flatMap((d, i) =>
        $("period").value === "all" || d.date.startsWith($("period").value)
          ? [i]
          : [],
      );
    }
    function address(view) {
      if (view === "trace") return "#trace";
      return `#${view}?day=${D.days[index].date}&method=${$("method").value}&period=${$("period").value}`;
    }
    function route() {
      const view = location.hash.slice(1).split("?")[0] || "explore";
      const target = ["explore", "understand", "trace"].includes(view)
        ? view
        : "explore";
      const p = new URLSearchParams(location.hash.split("?")[1] || "");
      if (p.has("day")) {
        const i = D.days.findIndex((d) => d.date === p.get("day"));
        if (i >= 0) index = i;
      }
      if (
        p.get("period") === "all" ||
        Object.hasOwn(D.report.breakdowns.month, p.get("period"))
      )
        $("period").value = p.get("period");
      if (!visibleIndices().includes(index)) index = visibleIndices()[0];
      overview();
      if (Object.hasOwn(names, p.get("method")))
        $("method").value = p.get("method");
      for (const section of document.querySelectorAll(".view"))
        section.hidden = section.id !== target;
      for (const a of document.querySelectorAll("nav a")) {
        if (a.dataset.view === target) a.setAttribute("aria-current", "page");
        else a.removeAttribute("aria-current");
      }
      renderDay();
    }
    function links() {
      for (const a of document.querySelectorAll('a[href^="#"]')) {
        const target = a.getAttribute("href").slice(1).split("?")[0];
        if (["explore", "understand", "trace"].includes(target))
          a.href = address(target);
      }
    }
    function refreshAddress() {
      const view = location.hash.slice(1).split("?")[0] || "explore";
      history.replaceState(null, "", address(view));
      links();
    }
    function overview() {
      const period = $("period").value;
      const group =
        period === "all" ? D.report : D.report.breakdowns.month[period];
      const m = group.metrics.system,
        r = group.metrics.reference;
      $("population").textContent =
        `${period === "all" ? `${D.days[0].date} – ${D.days.at(-1).date}` : period} · ${m.rows.toLocaleString()} scored quarters · ${group.missing_truth} missing outcomes · dates in Europe/Berlin`;
      $("metrics").replaceChildren();
      for (const [key, label, value, sub] of [
        [
          "wis",
          "Weighted interval score (WIS) ↓",
          fmt(m.wis),
          `Reference ${fmt(r.wis)} · €/MWh`,
        ],
        [
          "coverage",
          "Observed 95% coverage",
          pct(m.coverage_95),
          `Nominal 95% · reference ${pct(r.coverage_95)}`,
        ],
      ]) {
        const card = el("div", null, "metric");
        card.append(
          el("span", label, "metric-label"),
          el("span", value, "metric-value"),
          el("span", sub, "metric-sub"),
        );
        if (key === "wis") {
          card.append(
            el(
              "p",
              "Balances median error, band width and misses outside the bands. Lower is better; this is not a typical price error.",
              "metric-caption",
            ),
          );
          const teaching = $("wis-template").content.cloneNode(true);
          teaching.querySelector(".wis-caveat p").textContent =
            "WIS combines band-width cost with errors and misses; coverage asks only how often outcomes land inside. A system can win the combined score while its bands under-cover. Check both results for the selected period: the better score alone does not establish calibration.";
          card.append(teaching);
        }
        $("metrics").append(card);
      }
      $("verdict-title").textContent =
        `${m.wis < r.wis ? "Lower" : "Higher"} WIS than the reference. ${m.coverage_95 < 0.95 ? "The 95% band under-covers." : "Read coverage alongside width."}`;
      const c = D.report.comparison.system;
      $("verdict-text").textContent =
        `The nominal 95% band contained ${pct(m.coverage_95)} of observed prices in this period. ${period === "all" ? `The full-period WIS difference is ${fmt(c.wis_difference)} €/MWh; its paired seven-day-block 95% interval is ${fmt(c.ci_95[0])} to ${fmt(c.ci_95[1])}.` : "This monthly comparison is descriptive; the full-period uncertainty interval does not apply to this subset."} Historical input timing remains assumed or conditional.`;
      if (!m.rows) {
        $("verdict-title").textContent = "No observed prices in this period.";
        $("verdict-text").textContent =
          "Forecasts remain visible, but scores and observed coverage cannot be calculated without outcomes.";
      }
      renderComparison(group);
    }
    function renderComparison(group) {
      $("comparison").replaceChildren();
      const rows = Object.entries(group.metrics);
      if (sortKey) rows.sort(([a, x], [b, y]) => {
        const left = sortKey === "name" ? names[a] : x[sortKey];
        const right = sortKey === "name" ? names[b] : y[sortKey];
        if (left == null) return right == null ? 0 : 1;
        if (right == null) return -1;
        return sortDirection * (sortKey === "name" ? left.localeCompare(right) : left - right);
      });
      for (const button of document.querySelectorAll("[data-sort]")) {
        const active = button.dataset.sort === sortKey;
        button.closest("th").setAttribute("aria-sort", active ? (sortDirection === 1 ? "ascending" : "descending") : "none");
        button.querySelector(".sort-indicator").textContent = active ? (sortDirection === 1 ? " ▲" : " ▼") : " ↕";
      }
      for (const [n, s] of rows) {
        const tr = el("tr");
        for (const value of [
          names[n],
          fmt(s.wis),
          fmt(s.median_mae),
          fmt(s.median_rmse),
          pct(s.coverage_50),
          pct(s.coverage_95),
          fmt(s.width_50),
          fmt(s.width_95),
        ])
          tr.append(el("td", value));
        $("comparison").append(tr);
      }
    }
    function chart(day, method) {
      const root = $("chart");
      root.replaceChildren();
      svg(
        "title",
        { id: "chart-title" },
        root,
        `${names[method]} and realised prices, ${day.date}`,
      );
      svg(
        "desc",
        { id: "chart-desc" },
        root,
        "Median with central 50% and 95% bands. Hover over the chart or use the daily values table to read exact prices. The price scale is fixed across all saved days and methods.",
      );
      const points = day.points,
        reference = $("reference").checked,
        W = 1100,
        H = 380,
        L = 64,
        R = 22,
        T = 30,
        B = 42;
      const { low, high } = priceScale;
      root.dataset.priceMin = low;
      root.dataset.priceMax = high;
      const x = (i) => L + ((W - L - R) * i) / Math.max(points.length - 1, 1),
        y = (v) => T + ((H - T - B) * (high - v)) / (high - low);
      for (let j = 0; j <= 5; j++) {
        const v = low + ((high - low) * j) / 5;
        svg(
          "line",
          { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "#e1e5dd" },
          root,
        );
        svg(
          "text",
          {
            x: L - 12,
            y: y(v) + 4,
            "text-anchor": "end",
            fill: "#596966",
            "font-size": 12,
          },
          root,
          v.toFixed(0),
        );
      }
      svg(
        "text",
        { x: L, y: 15, fill: "#596966", "font-size": 12 },
        root,
        "€/MWh",
      );
      if (low < 0 && high > 0)
        svg(
          "line",
          {
            x1: L,
            x2: W - R,
            y1: y(0),
            y2: y(0),
            stroke: "#8d9a90",
            "stroke-dasharray": "4 4",
          },
          root,
        );
      const pathFor = (values) =>
        values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ");
      function band(name, a, b, fill, opacity = 1) {
        const upper = points.map((p) => p.q[name][b]),
          lower = points.map((p) => p.q[name][a]);
        const path =
          pathFor(upper) +
          " " +
          lower
            .map(
              (v, i) =>
                `L${x(points.length - 1 - i)},${y(lower[points.length - 1 - i])}`,
            )
            .join(" ") +
          " Z";
        svg("path", { d: path, fill, opacity }, root);
      }
      if (reference && method !== "reference")
        band("reference", 0, 4, "#c1a774", 0.22);
      band(method, 0, 4, "#d8e5dc");
      band(method, 1, 3, "#9dbfb3");
      svg(
        "path",
        {
          d: pathFor(points.map((p) => p.q[method][2])),
          fill: "none",
          stroke: "#19766b",
          "stroke-width": 2.5,
        },
        root,
      );
      if (reference && method !== "reference")
        svg(
          "path",
          {
            d: pathFor(points.map((p) => p.q.reference[2])),
            fill: "none",
            stroke: "#96722d",
            "stroke-width": 2,
            "stroke-dasharray": "7 5",
          },
          root,
        );
      let actual = "",
        connected = false;
      points.forEach((p, i) => {
        if (p.actual == null) {
          connected = false;
          return;
        }
        actual += `${connected ? "L" : "M"}${x(i)},${y(p.actual)} `;
        connected = true;
      });
      svg(
        "path",
        { d: actual, fill: "none", stroke: "#233b3a", "stroke-width": 2.2 },
        root,
      );
      for (
        let i = 0;
        i < points.length;
        i += Math.max(1, Math.floor(points.length / 6))
      )
        svg(
          "text",
          {
            x: x(i),
            y: H - 14,
            "text-anchor": "middle",
            fill: "#596966",
            "font-size": 12,
          },
          root,
          points[i].clock.slice(0, 5),
        );
      const selected = quarterIndex;
      svg(
        "line",
        {
          id: "cursor",
          x1: x(selected),
          x2: x(selected),
          y1: T,
          y2: H - B,
          stroke: "#a74c2b",
          "stroke-dasharray": "3 4",
        },
        root,
      );
      root.onpointermove = (e) => {
        const p = root.createSVGPoint();
        p.x = e.clientX;
        p.y = e.clientY;
        const local = p.matrixTransform(root.getScreenCTM().inverse());
        const i = Math.max(
          0,
          Math.min(
            points.length - 1,
            Math.round(((local.x - L) / (W - L - R)) * (points.length - 1)),
          ),
        );
        quarterIndex = i;
        pointDetail();
      };
      $("reference-legend").hidden = !reference;
    }
    function pointDetail() {
      const day = D.days[index],
        i = quarterIndex,
        p = day.points[i],
        q = p.q[$("method").value];
      $("point-detail").textContent =
        `${p.clock} · Actual ${fmt(p.actual)} · Median ${fmt(q[2])} · 50% [${fmt(q[1])}, ${fmt(q[3])}] · 95% [${fmt(q[0])}, ${fmt(q[4])}] €/MWh`;
      const cursor = $("cursor");
      if (cursor) {
        const x =
          64 + ((1100 - 64 - 22) * i) / Math.max(day.points.length - 1, 1);
        cursor.setAttribute("x1", x);
        cursor.setAttribute("x2", x);
      }
    }
    function renderDay() {
      const d = D.days[index],
        method = $("method").value,
        m = d.metrics[method];
      const visible = visibleIndices();
      $("day").min = D.days[visible[0]].date;
      $("day").max = D.days[visible.at(-1)].date;
      $("day").value = d.date;
      $("previous").disabled = index === visible[0];
      $("next").disabled = index === visible.at(-1);
      quarterIndex = Math.min(quarterIndex, d.points.length - 1);
      $("day-title").textContent = new Intl.DateTimeFormat("en-GB", {
        dateStyle: "long",
        timeZone: "UTC",
      }).format(new Date(d.date + "T12:00:00Z"));
      chart(d, method);
      pointDetail();
      $("day-metrics").replaceChildren();
      for (const [label, value] of [
        ["Daily WIS", fmt(m.wis)],
        ["Median MAE", fmt(m.median_mae)],
        ["95% coverage", pct(m.coverage_95)],
        ["Scored quarters", m.rows],
      ]) {
        const item = el("span", `${label} `);
        item.append(el("strong", value));
        $("day-metrics").append(item);
      }
      const chosen = [...new Set(d.points.map((p) => p.selected))]
          .map((n) => names[n])
          .join(", "),
        reasons = [...new Set(d.points.map((p) => p.reason).filter(Boolean))];
      $("day-context").textContent =
        `${d.points.length} delivery quarters · ${d.missing_truth} missing outcomes. System used: ${chosen}. ${
          reasons.length
            ? `Fallback: ${reasons
                .map((reason) =>
                  reason
                    .split(";")
                    .map((part) => {
                      const [model, cause] = part.split(":");
                      return `${names[model] || model}: ${{ demand_source_unavailable: "no eligible demand forecast", weather_source_unavailable: "weather source unavailable", price_lags_unavailable: "price history unavailable", prediction_failure: "model execution failed" }[cause] || cause}`;
                    })
                    .join("; "),
                )
                .join("; ")}.`
            : "No source fallback."
        } Historical issue deadline: ${d.issue}.`;
      $("quarters").replaceChildren();
      for (const p of d.points) {
        const tr = el("tr");
        for (const v of [p.clock, fmt(p.actual), ...p.q[method].map(fmt)])
          tr.append(el("td", v));
        $("quarters").append(tr);
      }
      links();
    }
    const stages = [
      {
        id: "prices",
        x: 20,
        y: 25,
        w: 215,
        title: "SMARD prices",
        sub: "DE–LU · quarter-hour · €/MWh",
      },
      {
        id: "weather",
        x: 285,
        y: 25,
        w: 205,
        title: "Open-Meteo / ICON-EU",
        sub: "12 locations · hourly forecasts",
      },
      {
        id: "demand",
        x: 540,
        y: 25,
        w: 200,
        title: "ENTSO-E demand",
        sub: "Germany · quarter-hour · MW",
      },
      {
        id: "snapshot",
        x: 285,
        y: 125,
        w: 205,
        title: "Validate & freeze inputs",
        sub: "Three typed Parquet tables",
      },
      {
        id: "select",
        x: 285,
        y: 225,
        w: 205,
        title: "Select eligible versions",
        sub: "Before the historical deadline",
      },
      {
        id: "features",
        x: 285,
        y: 325,
        w: 205,
        title: "Transform into features",
        sub: "Clock lags · alignment · flags",
      },
      {
        id: "labels",
        x: 20,
        y: 425,
        w: 215,
        title: "Select training labels",
        sub: "Earlier prices at fit cutoff",
      },
      {
        id: "fit",
        x: 285,
        y: 425,
        w: 205,
        title: "Learn from past examples",
        sub: "Monthly models + reference",
      },
      {
        id: "predict",
        x: 540,
        y: 425,
        w: 200,
        title: "Predict five quantiles",
        sub: "Evaluate trees · sort outputs",
      },
      {
        id: "fallback",
        x: 540,
        y: 525,
        w: 200,
        title: "Select usable forecast",
        sub: "Source / execution fallback",
      },
      {
        id: "truth",
        x: 20,
        y: 605,
        w: 215,
        title: "Join realised prices",
        sub: "After prediction · scoring only",
      },
      {
        id: "score",
        x: 285,
        y: 605,
        w: 205,
        title: "Measure the result",
        sub: "Errors · coverage · width",
      },
    ];
    function renderPipeline() {
      const root = $("pipeline");
      root.replaceChildren();
      const defs = svg("defs", {}, root);
      const marker = svg(
        "marker",
        {
          id: "arrow",
          viewBox: "0 0 10 10",
          refX: 9,
          refY: 5,
          markerWidth: 6,
          markerHeight: 6,
          orient: "auto-start-reverse",
        },
        defs,
      );
      svg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#73897c" }, marker);
      const edges = [
        ["M128 89 V105 H388 V125", false],
        ["M388 89 V125", false],
        ["M640 89 V105 H388 V125", false],
        ["M388 189 V225", false],
        ["M285 157 H255 V457 H235", true],
        ["M388 289 V325", false],
        ["M388 389 V425", false],
        ["M490 357 H640 V425", false],
        ["M235 457 H285", true],
        ["M490 457 H540", false],
        ["M640 489 V525", false],
        ["M640 589 V637 H490", false],
        ["M235 637 H285", true],
      ];
      for (const [d, dashed] of edges)
        svg(
          "path",
          {
            d,
            fill: "none",
            stroke: "#73897c",
            "stroke-width": 1.8,
            "stroke-dasharray": dashed ? "5 5" : "none",
            "marker-end": "url(#arrow)",
          },
          root,
        );
      for (const s of stages) {
        const g = svg(
          "g",
          {
            role: "button",
            tabindex: 0,
            "aria-label": s.title,
            "aria-pressed": s.id === node ? "true" : "false",
          },
          root,
        );
        svg(
          "rect",
          { x: s.x, y: s.y, width: s.w, height: 64, rx: 6, class: "node-box" },
          g,
        );
        svg(
          "text",
          {
            x: s.x + 14,
            y: s.y + 26,
            "font-size": 13,
            fill: "#233b3a",
            "font-weight": 600,
          },
          g,
          s.title,
        );
        svg(
          "text",
          { x: s.x + 14, y: s.y + 46, "font-size": 11, fill: "#596966" },
          g,
          s.sub,
        );
        const activate = () => {
          node = s.id;
          for (const sibling of root.querySelectorAll("[role=button]"))
            sibling.setAttribute(
              "aria-pressed",
              sibling === g ? "true" : "false",
            );
          nodeDetail();
        };
        g.onclick = activate;
        g.onkeydown = (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            activate();
          }
        };
      }
      nodeDetail();
    }
    function nodeDetail() {
      const key =
        { prices: "price", snapshot: "load", fit: "train" }[node] || node;
      const stage = D.pipeline[key],
        panel = $("node-detail");
      panel.replaceChildren(
        el("p", "HOW THIS STAGE WORKS", "eyebrow"),
        el("h3", stage.title),
      );
      const explanation = el("dl");
      for (const [label, key] of [
        ["What comes in", "input"],
        ["What happens, and why", "operation"],
        ["What goes out", "output"],
      ])
        definition(explanation, label, stage[key]);
      panel.append(explanation);
      const evidence = el("details");
      evidence.append(el("summary", "Evidence from this saved run"));
      const facts = el("dl");
      evidence.append(facts);
      definition(facts, "Run", D.run.run_id);
      if (["prices", "weather", "demand", "snapshot"].includes(node))
        definition(facts, "Input snapshot", D.snapshot);
      if (node === "features")
        for (const [name, count] of Object.entries(D.features))
          definition(facts, names[name], `${count} input columns`);
      if (["fit", "labels"].includes(node)) {
        definition(facts, "Training begins", D.config.train_start);
        definition(facts, "Monthly fitted folds", Object.keys(D.folds).length);
        if (node === "fit")
          definition(
            facts,
            "Saved settings",
            JSON.stringify(D.config.catboost),
          );
      }
      if (node === "predict")
        for (const [name, fraction] of Object.entries(
          D.report.raw_crossing_fraction,
        ))
          definition(
            facts,
            `${names[name]}: raw crossing fraction`,
            pct(fraction),
          );
      if (["truth", "score"].includes(node)) {
        definition(facts, "Scored quarters", D.report.scored_rows);
        definition(facts, "Missing outcomes", D.report.missing_truth);
      }
      if (node === "fallback")
        for (const [name, count] of Object.entries(D.report.fallback_rows))
          definition(
            facts,
            `System selected ${names[name]}`,
            `${count} quarters`,
          );
      panel.append(evidence);
      const link = el("a", "Read the source contract ↗");
      link.href =
        D.sources[
          ["prices", "weather", "demand", "select", "snapshot"].includes(node)
            ? "inputs"
            : "evaluation"
        ].url;
      panel.append(link);
    }
    for (const a of document.querySelectorAll("[data-source]"))
      a.href =
        D.sources[a.dataset.source].url +
        (a.dataset.anchor ? "#" + a.dataset.anchor : "");
    $("coverage-explanation").textContent =
      `Across the full saved evaluation, the nominal 95% system band covered ${pct(D.report.metrics.system.coverage_95)} of observed quarters; its mean width was ${fmt(D.report.metrics.system.width_95)} €/MWh. The reference covered ${pct(D.report.metrics.reference.coverage_95)} with width ${fmt(D.report.metrics.reference.width_95)} €/MWh.`;
    for (const [k, v] of Object.entries(D.report.timing_limits))
      definition($("timing"), k, v);
    $("identity").textContent =
      `Run ${D.run.run_id} · ${D.run.exploratory ? "Exploratory execution" : "Saved baseline execution"} · ${D.days.length} delivery days`;
    for (const [k, v] of Object.entries({
      ...D.run,
      snapshot: D.snapshot,
      manifest_sha256: D.manifest_sha256,
    }))
      definition($("provenance"), k.replaceAll("_", " "), v);
    for (const [name, hash] of Object.entries(D.presentation_sha256))
      definition($("provenance"), `Presentation: ${name}`, hash);
    for (const source of Object.values(D.sources)) {
      const li = el("li"),
        a = el("a", source.path);
      a.href = source.url;
      li.append(
        a,
        el(
          "span",
          ` · ${source.revision.slice(0, 12)} · SHA256 ${source.sha256}`,
        ),
      );
      $("sources").append(li);
    }
    for (const button of document.querySelectorAll("[data-sort]")) {
      button.onclick = () => {
        sortDirection = sortKey === button.dataset.sort ? -sortDirection : 1;
        sortKey = button.dataset.sort;
        const period = $("period").value;
        renderComparison(period === "all" ? D.report : D.report.breakdowns.month[period]);
      };
    }
    $("period").onchange = () => {
      if (!visibleIndices().includes(index)) index = visibleIndices()[0];
      overview();
      renderDay();
      refreshAddress();
    };
    $("day").onchange = () => {
      const selected = D.days.findIndex((d) => d.date === $("day").value);
      if (visibleIndices().includes(selected)) index = selected;
      renderDay();
      refreshAddress();
    };
    $("previous").onclick = () => {
      const visible = visibleIndices();
      index = visible[Math.max(0, visible.indexOf(index) - 1)];
      renderDay();
      refreshAddress();
    };
    $("next").onclick = () => {
      const visible = visibleIndices();
      index = visible[Math.min(visible.length - 1, visible.indexOf(index) + 1)];
      renderDay();
      refreshAddress();
    };
    $("method").onchange = () => {
      renderDay();
      refreshAddress();
    };
    $("reference").onchange = () => renderDay();
    window.addEventListener("hashchange", route);
    renderPipeline();
    overview();
    route();
  } catch (e) {
    $("error").hidden = false;
    $("error").textContent = `Unable to display this export: ${e.message}`;
    console.error(e);
  }
})();
