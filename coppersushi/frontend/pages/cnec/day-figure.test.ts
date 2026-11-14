import {expect, test} from 'vitest';
// Geometry is schematic here; the price arithmetic above uses published observations.
import {dayFigure, zoneFeatures} from './day-figure';
import type {DayBundle} from './data/contracts';
import {orderedMapLayers} from '../../map/map-layer-order';
function drawingFixture(): DayBundle {
  return {version:3,day:'2026-11-03',labels:['Tue 03 Nov 2026 · 00:00 CET'],price_range:[90,100],
    zones:[{zone:'DE',name:'Germany',centre:[10,50],rings:[[[9,49],[11,49],[11,51],[9,49]]]},{zone:'PL',name:'Poland',centre:[20,52],rings:[[[19,51],[21,51],[21,53],[19,51]]]}],
    elements:{line:{branch_id:'line',kind:'line',endpoints:[[9,50],[11,50]]},pst:{branch_id:'pst',kind:'transformer',endpoints:[[15,51],[15,51]]}},
    intervals:[{index:0,label:'Tue 03 Nov 2026 · 00:00 CET',prices:{DE:100,PL:90},alpha:1,notes:[],caps:[{source_id:-2,name:'Poland export cap',direction:'export',shadow_price:5,capacity:100,delta:-5}],
      constraints:[{source_id:1,eic:'11T0-0000-0984-D',name:'Line',direction:'DIRECT',contingency:null,shadow_price:10,capacity:200,ram:100,geometry:'line',ptdfs:{DE:0,PL:0.2}},
      {source_id:2,eic:'11T0-0000-0984-D',name:'Line',direction:'OPPOSITE',contingency:'Other outage',shadow_price:2,capacity:200,ram:100,geometry:'line',ptdfs:{DE:0,PL:-0.2}},
      {source_id:3,eic:'11T0-0000-0986-7',name:'PST',direction:'DIRECT',contingency:null,shadow_price:1,capacity:200,ram:100,geometry:'pst',ptdfs:{DE:0,PL:0.1}}]}]};
}
function draw(selected:string|null, compactTooltips=false) {const data=drawingFixture();return dayFigure(data,0,selected,'DE',{mapbox:{style:'dark'},uirevision:'camera'},zoneFeatures(data),compactTooltips);}

test('opposite directions have opposite triangles and share line hit identities',()=>{
  const figure=draw(null);
  const symbols=figure.data.find(t=>t.name==='binding rows')!;
  const angles=(symbols.marker as {angle:number[]}).angle;
  expect(Math.abs(angles[0]-angles[1])).toBeCloseTo(180);
  const hit=figure.data.find(t=>t.name==='select line')!;
  expect(new Set((hit.customdata as string[][]).map(d=>d[0]))).toEqual(new Set(['11T0-0000-0984-D']));
  expect((hit.text as string[])[0]).toContain('Other outage');
});
test('selected transformer retains its native ring symbol and effect metadata',()=>{
  const trace=draw('11T0-0000-0986-7').data.find(t=>t.name==='selected CNEC')!;
  expect((trace.marker as {symbol:string}).symbol).toBe('transformer-selected');
  expect(trace.meta).toEqual({role:'binding-symbol',effect:'transformer'});
  expect(trace.lon).toEqual([15]);
});
test('country cap uses the shared display boundary and reports its actual limit',()=>{
  const figure=draw('cap:PL'), hit=figure.data.find(t=>t.name==='select country cap')!;
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
  const before=dayFigure(data,0,'11T0-0000-0984-D','DE',layout,geography);
  const next=structuredClone(data);
  next.intervals[0].prices={DE:120,PL:110};
  for (const selected of [null,'11T0-0000-0986-7','cap:PL']) {
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
  const figure=draw('UNKNOWN');
  expect(figure.data.some(trace=>trace.name==='ray contributions')).toBe(false);
});

test('asset rays sum opposite directions while tooltip keeps each contingency',()=>{
  const figure=draw('11T0-0000-0984-D');
  expect(figure.data.find(t=>t.name==='ray contributions')!.text).toEqual(['−€1.60']);
  const text=(figure.data.find(t=>t.name==='select line')!.text as string[])[0];
  expect(text).toContain('Base case');
  expect(text).toContain('Other outage');
  expect(text).not.toContain('Direction:');
  for (const trace of figure.data.filter(t=>String(t.name).endsWith(' ray') || t.name==='ray contributions')) {
    expect(trace.hoverinfo).toBe('skip');
  }
});

test('one EIC highlights all of its distinct branches',()=>{
  const data=drawingFixture();
  data.elements.other={branch_id:'other',kind:'line',endpoints:[[11,50],[12,51]]};
  data.intervals[0].constraints[1].geometry='other';
  const figure=dayFigure(data,0,'11T0-0000-0984-D','DE',{mapbox:{},uirevision:'camera'},zoneFeatures(data));
  expect(figure.data.find(t=>t.name==='selected CNEC')!.lon).toEqual([9,11,null,11,12,null]);
});

test('a selected asset with no binding rows has no rays or selection effect',()=>{
  const data=drawingFixture();data.intervals[0].constraints=[];
  const figure=dayFigure(data,0,'11T0-0000-0984-D','DE',{mapbox:{},uirevision:'camera'},zoneFeatures(data));
  expect(figure.data.some(t=>t.name==='selected CNEC' || t.name==='ray contributions')).toBe(false);
});

test('touch tooltips omit contingencies and keep both limits on one row',()=>{
  const figure=draw('11T0-0000-0984-D',true);
  const text=(figure.data.find(t=>t.name==='select line')!.text as string[])[0];
  expect(text).not.toContain('Binding under:');
  expect(text).not.toContain('Other outage');
  expect(text).toContain('RAM: 100 MW · Capacity: 200 MW');
  expect(text).toContain('Shadow price: 10.00 €/MWh');
});
