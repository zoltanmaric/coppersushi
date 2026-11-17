import {test} from 'node:test';
import assert from 'node:assert/strict';
import {scheduledTime,resultMetrics,publishResults} from '../src/handler.js';
test('scheduled timestamps are retained across retries; stale and malformed events are rejected',()=>{
  const slot='2026-11-17T12:00:00Z';
  assert.equal(scheduledTime({scheduledTime:slot},Date.parse(slot)+60_000).toISOString(),'2026-11-17T12:00:00.000Z');
  for(const event of [null,{}, {scheduledTime:'invalid'}, {scheduledTime:slot}])
    assert.throws(()=>scheduledTime(event,Date.parse(slot)+121_000));
});
test('a single metric per check shares the scheduled timestamp',()=>{
  const timestamp=new Date();
  const results=['blog','critical-elements','power-flow','ghost-origin'].map((id,i)=>({id,url:'https://example.com',failed:i===1,durationMs:20,diagnostics:[]}));
  const metrics=resultMetrics(results,timestamp);
  assert.deepEqual(metrics.map(metric=>metric.Value),[0,1,0,0]);
  assert.ok(metrics.every(metric=>metric.Timestamp===timestamp));
  assert.throws(()=>resultMetrics(results.slice(1),timestamp));
  assert.throws(()=>resultMetrics(results.map((result,i)=>i===0 ? {...result,id:'renamed-blog'} : result),timestamp));
});

test('heartbeat follows successful result publication and is withheld on publication failure',async()=>{
  const results=['blog','critical-elements','power-flow','ghost-origin'].map(id=>({id,url:'https://example.com',failed:false,durationMs:20,diagnostics:[]}));
  const calls:string[][]=[];
  await publishResults(results,new Date(),async metrics=>{calls.push(metrics.map(metric=>metric.MetricName));});
  assert.deepEqual(calls,[['Failed','Failed','Failed','Failed'],['Completed']]);
  let attempts=0;
  await assert.rejects(publishResults(results,new Date(),async()=>{attempts++;throw new Error('CloudWatch unavailable');}));
  assert.equal(attempts,1);
});
