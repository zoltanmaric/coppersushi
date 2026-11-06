import physicalCsv from '../../tests/fixtures/cnec-attribution/observed/physical.csv?raw';
import ptdfsCsv from '../../tests/fixtures/cnec-attribution/observed/ptdfs.csv?raw';
import pricesCsv from '../../tests/fixtures/cnec-attribution/observed/prices.csv?raw';
import contextCsv from '../../tests/fixtures/cnec-attribution/observed/context.csv?raw';
import selection from '../../tests/fixtures/cnec-attribution/observed/selection.json';
import { describe, expect, test } from "vitest";
import { contributions } from "./day-figure";
import type { MarketInterval } from "./contracts";
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
          source_id: Number(r.source_id),
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
        for (const row of [...interval.constraints, ...interval.caps])
          for (const [zone, value] of Object.entries(
            contributions(interval, row.source_id, reference)!,
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

// Geometry is schematic here; the price arithmetic above uses published observations.
import {dayFigure, zoneFeatures} from './day-figure';
import type {DayBundle} from './contracts';
import {orderedMapLayers} from './map-layer-order';
function drawingFixture(): DayBundle {
  return {version:2,day:'2026-11-03',labels:['Tue 03 Nov 2026 · 00:00 CET'],price_range:[90,100],
    zones:[{zone:'DE',name:'Germany',centre:[10,50],rings:[[[9,49],[11,49],[11,51],[9,49]]]},{zone:'PL',name:'Poland',centre:[20,52],rings:[[[19,51],[21,51],[21,53],[19,51]]]}],
    elements:{line:{branch_id:'line',kind:'line',endpoints:[[9,50],[11,50]]},pst:{branch_id:'pst',kind:'transformer',endpoints:[[15,51],[15,51]]}},
    intervals:[{index:0,label:'Tue 03 Nov 2026 · 00:00 CET',prices:{DE:100,PL:90},alpha:1,notes:[],caps:[{source_id:-2,name:'Poland export cap',direction:'export',shadow_price:5,capacity:100,delta:-5}],
      constraints:[{source_id:1,name:'Line',direction:'DIRECT',contingency:null,shadow_price:10,capacity:200,ram:100,geometry:'line',ptdfs:{DE:0,PL:0.2}},
      {source_id:2,name:'Line',direction:'OPPOSITE',contingency:'Other outage',shadow_price:2,capacity:200,ram:100,geometry:'line',ptdfs:{DE:0,PL:-0.2}},
      {source_id:3,name:'PST',direction:'DIRECT',contingency:null,shadow_price:1,capacity:200,ram:100,geometry:'pst',ptdfs:{DE:0,PL:0.1}}]}]};
}
function draw(selected:number|null) {const data=drawingFixture();return dayFigure(data,0,selected,'DE',{mapbox:{style:'dark'},uirevision:'camera'},zoneFeatures(data));}

test('opposite directions have opposite triangles and share line hit identities',()=>{
  const figure=draw(null);
  const symbols=figure.data.find(t=>t.name==='binding rows')!;
  const angles=(symbols.marker as {angle:number[]}).angle;
  expect(Math.abs(angles[0]-angles[1])).toBeCloseTo(180);
  const hit=figure.data.find(t=>t.name==='select line')!;
  expect(new Set((hit.customdata as string[][]).map(d=>d[0]))).toEqual(new Set(['1,2']));
  expect((hit.text as string[])[0]).toContain('Other outage');
});
test('selected transformer retains its native ring symbol and effect metadata',()=>{
  const trace=draw(3).data.find(t=>t.name==='selected CNEC')!;
  expect((trace.marker as {symbol:string}).symbol).toBe('transformer-selected');
  expect(trace.meta).toEqual({role:'binding-symbol',effect:'transformer'});
  expect(trace.lon).toEqual([15]);
});
test('country cap uses the shared display boundary and reports its actual limit',()=>{
  const figure=draw(-2), hit=figure.data.find(t=>t.name==='select country cap')!;
  expect((hit.text as string[])[0]).toContain('Net export limit: 100 MW');
  const outline=figure.data.find(t=>t.name==='binding country cap')!;
  expect((outline.lon as number[]).filter(v=>v!==null)).toContain(19);
  expect((outline.lon as number[]).filter(v=>v!==null)).toContain(21);
  expect((figure.data.find(t=>t.name==='ray contributions')!.text as string[])).toEqual(['−€5.00']);
});

test('interval and selection updates retain distinct stable map insertion points',()=>{
  const data=drawingFixture();
  const layers=orderedMapLayers([{id:'land',type:'background'},{id:'boundaries',type:'line'}]);
  const layout={mapbox:{style:{version:8,layers}},uirevision:'camera'};
  const geography=zoneFeatures(data);
  const before=dayFigure(data,0,1,'DE',layout,geography);
  const next=structuredClone(data);
  next.intervals[0].prices={DE:120,PL:110};
  for (const selected of [null,3,-2]) {
    const figure=dayFigure(next,0,selected,'DE',layout,geography);
    const targets=figure.data.map(trace=>trace.below);
    expect(new Set(targets).size).toBe(targets.length);
    expect(targets.every(target=>layers.some(layer=>layer.id===target))).toBe(true);
    for (const name of ['published day-ahead price','binding rows']) {
      const trace=figure.data.find(trace=>trace.name===name)!;
      const previous=before.data.find(trace=>trace.name===name)!;
      expect([trace.uid,trace.below]).toEqual([previous.uid,previous.below]);
    }
    expect(figure.data[0].geojson).toBe(geography);
  }
  const countryAnchor=String(before.data[0].below);
  expect(layers.findIndex(layer=>layer.id===countryAnchor)).toBeLessThan(layers.findIndex(layer=>layer.id==='boundaries'));
});

test('an expired selection emits no temporary empty ray-label trace',()=>{
  const figure=draw(999);
  expect(figure.data.some(trace=>trace.name==='ray contributions')).toBe(false);
});
