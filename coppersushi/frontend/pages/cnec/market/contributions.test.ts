import physicalCsv from '../../../../pipelines/cnec/testdata/cnec-attribution/observed/physical.csv?raw';
import ptdfsCsv from '../../../../pipelines/cnec/testdata/cnec-attribution/observed/ptdfs.csv?raw';
import pricesCsv from '../../../../pipelines/cnec/testdata/cnec-attribution/observed/prices.csv?raw';
import contextCsv from '../../../../pipelines/cnec/testdata/cnec-attribution/observed/context.csv?raw';
import selection from '../../../../pipelines/cnec/testdata/cnec-attribution/observed/selection.json';
import { describe, expect, test } from "vitest";
import { contributions } from "./contributions";
import type { MarketInterval } from "../data/contracts";
import { CORE_ZONES } from "./reference";

// Independently published JAO/SMARD observations verify the browser-owned calculation.

function csv(content: string): Record<string, string>[] {
  const rows = content
    .trim()
    .split("\n")
    .map((line) =>
      line
        .match(/("(?:[^"]|"")*"|[^,]*)(,|$)/g)!
        .slice(0, -1)
        .map((v) =>
          v.replace(/,$/, "").replace(/^"|"$/g, "").replaceAll('""', '"'),
        ),
    );
  return rows
    .slice(1)
    .map((values) =>
      Object.fromEntries(rows[0].map((key, i) => [key, values[i]])),
    );
}
const physical = csv(physicalCsv),
  ptdfs = csv(ptdfsCsv),
  prices = csv(pricesCsv),
  context = csv(contextCsv);
const times = Object.keys(selection);
const same = (a: string, b: string) => Date.parse(a) === Date.parse(b);
for (const time of times)
  describe(time, () => {
    const input = context.find((r) => same(r.interval, time))!;
    const observed = Object.fromEntries(
      prices
        .filter((r) => same(r.interval, time))
        .map((r) => [r.zone, Number(r.price)]),
    );
    const delta = observed.PL - Number(input.polish_alt);
    const cap =
      Math.abs(delta) > 1e-9 &&
      (delta < 0
        ? Math.abs(
            Number(input.polish_position) - Number(input.export_limit),
          ) <= 0.11
        : Math.abs(
            Number(input.polish_position) + Number(input.import_limit),
          ) <= 0.11);
    const interval: MarketInterval = {
      index: 0,
      label: time,
      prices: observed,
      alpha: Number(input.alpha),
      notes: [],
      constraints: physical
        .filter((r) => same(r.interval, time))
        .map((r) => ({
          source_id: Number(r.source_id), eic: r.eic,
          name: r.name,
          direction: r.direction,
          contingency: r.cont_name,
          shadow_price: Number(r.shadow_price),
          ram: null,
          capacity: null,
          geometry: null,
          ptdfs: Object.fromEntries(
            ptdfs
              .filter(
                (p) => same(p.interval, time) && p.source_id === r.source_id,
              )
              .map((p) => [p.zone, Number(p.ptdf)]),
          ),
        })),
      caps: cap
        ? [
            {
              source_id: delta < 0 ? -2 : -1,
              name: "Poland cap",
              direction: delta < 0 ? "export" : "import",
              capacity: 0,
              shadow_price: Math.abs(delta),
              delta,
            },
          ]
        : [],
    };
    for (const reference of CORE_ZONES)
      test(`published pair spreads reconcile with reference ${reference}`, () => {
        const total: Record<string, number> = {};
        for (const id of new Set([...interval.constraints.map(r=>r.eic), ...(interval.caps.length ? ['cap:PL'] : [])]))
          for (const [zone, value] of Object.entries(
            contributions(interval, id, reference)!,
          ))
            total[zone] = (total[zone] ?? 0) + value;
        for (const a of Object.keys(observed))
          for (const b of Object.keys(observed))
            expect(
              Math.abs(
                (total[b] ?? 0) - (total[a] ?? 0) - (observed[b] - observed[a]),
              ),
            ).toBeLessThanOrEqual(0.02);
      });
  });
