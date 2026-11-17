import {CloudWatchClient, PutMetricDataCommand} from '@aws-sdk/client-cloudwatch';
import {launchBrowser} from './browser.js';
import {runChecks, urls, type Result} from './checks.js';

export function scheduledTime(event:unknown, now:number):Date {
  if (!event || typeof event!=='object' || !('scheduledTime' in event) || typeof event.scheduledTime!=='string')
    throw new Error('Expected Scheduler scheduledTime');
  const time=Date.parse(event.scheduledTime);
  if(!Number.isFinite(time) || time>now+5000 || now-time>120_000) throw new Error('Stale or invalid scheduled time');
  return new Date(time);
}
export function resultMetrics(results:Result[], timestamp:Date) {
  if(results.length!==Object.keys(urls).length || Object.keys(urls).some(id=>results.filter(result=>result.id===id).length!==1)) throw new Error('Expected four check results');
  return results.map(result=>({MetricName:'Failed',Dimensions:[{Name:'Check',Value:result.id}],Timestamp:timestamp,Value:Number(result.failed),Unit:'Count' as const}));
}
export async function publishResults(results:Result[], timestamp:Date, send:(metrics:ReturnType<typeof resultMetrics>)=>Promise<unknown>) {
  await send(resultMetrics(results,timestamp));
  await send([{MetricName:'Completed',Timestamp:timestamp,Value:1,Unit:'Count',Dimensions:[]}]);
}
export async function handler(event:unknown) {
  const timestamp=scheduledTime(event,Date.now());
  const namespace=process.env.METRIC_NAMESPACE;
  if (!namespace) throw new Error('METRIC_NAMESPACE is required');
  const browser=await launchBrowser();
  let results:Result[];
  try {results=await runChecks(browser);}
  finally {await browser.close();}
  for(const result of results) console.log(JSON.stringify({scheduledTime:timestamp.toISOString(),...result}));
  const client=new CloudWatchClient({});
  try {
    await publishResults(results,timestamp,MetricData=>client.send(new PutMetricDataCommand({Namespace:namespace,MetricData})));
  } finally {client.destroy();}
  return results;
}
