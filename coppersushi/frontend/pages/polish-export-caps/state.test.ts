import {expect,test} from 'vitest';
import {readState,writeState,sortRows,filterRows} from './state';
import {type BindingInterval} from './data';

const row:BindingInterval={utc:'2026-10-25T01:15:00Z',date:'2026-10-25',index:13,shadow:100,required:{status:'available',mw:1000,products:[100,200,300,400],published_at:'2026-10-24T06:00:00Z'},procured:{status:'available',mw:900,products:[100,200,300,300],published_at:'2026-10-24T06:00:00Z'},cap:0,price:-10};
test('reload restores selection, sort and camera, including the repeated autumn hour',()=>{
  const state=readState('',row);
  state.camera={lat:52,lon:19.5,zoom:4.5};state.sort='price';state.order='asc';state.selection.selected=null;
  expect(readState(writeState(state),row)).toEqual(state);
  expect(readState('?day=2026-10-25&interval=9',row).selection.interval).toBe(9);
});
test.each(['?interval=oops','?reference=XX','?constraint=bad','?lat=51','?lat=90&lon=19&zoom=4','?sort=unknown','?order=up','?day=2026-02-30'])('reject invalid link %s',search=>{
  expect(()=>readState(search,row)).toThrow();
});
test('numeric sorting retains negative prices and stable chronological ties',()=>{
  const later={...row,utc:'2026-10-25T01:30:00Z',index:14};
  const expensive={...row,utc:'2026-10-25T01:45:00Z',index:15,price:200};
  expect(sortRows([expensive,later,row],'price','asc')).toEqual([row,later,expensive]);
});
test('inclusive dates and zero-valued numeric bounds round trip and filter',()=>{
  const state=readState('?from=2026-10-25&to=2026-10-25&shortfallMin=0&shortfallMax=100&priceMax=0',row);
  expect(readState(writeState(state),row)).toEqual(state);
  expect(filterRows([row,{...row,price:1}],state)).toEqual([row]);
});
test.each(['?from=2026-10-26&to=2026-10-25','?priceMin=10&priceMax=0','?shadowMin=NaN'])('reject invalid filter %s',search=>{
  expect(()=>readState(search,row)).toThrow();
});

test('surplus procurement remains negative when sorting and filtering shortfall',()=>{
  const surplus:BindingInterval={...row,procured:{...row.procured,mw:1200,products:[300,300,300,300]}};
  const balanced={...row,procured:row.required};
  expect(sortRows([row,surplus,balanced],'shortfall','asc')).toEqual([surplus,balanced,row]);
  const state=readState('?shortfallMin=-200&shortfallMax=-1',row);
  expect(readState(writeState(state),row)).toEqual(state);
  expect(filterRows([row,surplus,balanced],state)).toEqual([surplus]);
});
