import {expect,test} from 'vitest';
import {renderHour} from './render';
import type {Dataset} from './contracts';
const metadata:Omit<Dataset,'intervals'>={version:2,net_power_scale_mw:100,nodes:[{id:'a',longitude:1,latitude:2,country:'DE',voltage_kv:220},{id:'b',longitude:3,latitude:4,country:'FR',voltage_kv:400}],branches:[{component:'Line',name:'line',bus0:'a',bus1:'b',capacity_mw:10,midpoint_longitude:2,midpoint_latitude:3,forward_bearing:90,reverse_bearing:-90}]};
test('signed flow selects bearing and loading; tooltip markup escapes source names',()=>{
 const figure=renderHour(metadata,{timestamp:'2024-08-29T10:00:00Z',nodes:[{node:'a',net_power_mw:10,load_mw:0,generators:[{technology:'<script>',power_mw:10,available_mw:20}]},{node:'b',net_power_mw:-10,load_mw:10,generators:[]}],branches:[{component:'Line',name:'line',flow_mw:-10}]},[]);
 expect(figure.data[0].lon).toEqual([1,3,null]);
 expect(figure.data[1].lon).toEqual([]);
 expect(figure.data[2].marker).toMatchObject({angle:[-90]});
 expect((figure.data[3].text as string[])[0]).toContain('&lt;script&gt;');
 expect((figure.data[3].text as string[])[0]).toContain('10/20 MW');
 expect((figure.data[3].text as string[])[0]).toContain('Load</b>: 0 MW');
});
