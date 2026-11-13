import {afterEach,expect,test,vi} from 'vitest';
import {defaultHour,fetchManifest,fetchHour,fullLabel} from './data';
afterEach(()=>vi.unstubAllGlobals());
test('default selects noon in the operating timezone',()=>{
  const times=['2024-08-29T00:00:00Z','2024-08-29T10:00:00Z','2024-08-29T12:00:00Z'];
  expect(defaultHour(times)).toBe(1);
  expect(fullLabel.format(new Date(times[1]))).toContain('12:00');
});
test('rejects unordered manifest timestamps',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({version:2,generation:'a'.repeat(24),snapshots:['2024-08-29T12:00:00Z','2024-08-29T10:00:00Z']})}));
  await expect(fetchManifest(new AbortController().signal)).rejects.toThrow('Invalid Power Flow manifest');
});
test('rejects missing map layout',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({data:[],layout:{}})}));
  await expect(fetchHour('a'.repeat(24),0,new AbortController().signal)).rejects.toThrow('Invalid Power Flow dataset');
});
