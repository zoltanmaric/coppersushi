import type {Browser} from 'playwright-core';
import urls from './checks.json' with {type:'json'};
export {urls};

export const checks = [
  {id:'blog', url:urls.blog, kind:'blog'},
  {id:'critical-elements', url:urls['critical-elements'], kind:'map', renderer:'#cnec-view-map'},
  {id:'power-flow', url:urls['power-flow'], kind:'map', renderer:'#opf-map'},
] as const;
export type Check = {id:string; url:string} & ({kind:'blog'} | {kind:'map'; renderer:string});
export interface Result {id:string; url:string; failed:boolean; durationMs:number; diagnostics:string[]}
export const originUrl = urls['ghost-origin'];

export function analytics(raw:string):boolean {
  const url = new URL(raw);
  return (url.hostname === 'static.cloudflareinsights.com' && url.pathname === '/beacon.min.js')
    || (url.hostname === 'cloudflareinsights.com' && url.pathname.startsWith('/cdn-cgi/rum'))
    || url.pathname === '/cdn-cgi/rum'
    || (url.hostname === 'www.googletagmanager.com' && url.pathname === '/gtag/js')
    || (/(^|\.)google-analytics\.com$/.test(url.hostname) && url.pathname.endsWith('/collect'))
    || (url.hostname === 'cdn.usefathom.com' && url.pathname === '/script.js');
}

export async function checkPage(browser:Browser, check:Check, deadlineMs=45_000, observationMs=3_000):Promise<Result> {
  const start = Date.now();
  const diagnostics:string[] = [];
  let failed = false;
  const record = (message:string, fatal=false) => {
    if (fatal && !failed) diagnostics.unshift(message.slice(0,1500));
    else if (diagnostics.length < 50) diagnostics.push(message.slice(0,1500));
    diagnostics.length = Math.min(diagnostics.length,50);
    failed ||= fatal;
  };
  const context = await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block'});
  const timer = setTimeout(()=>{record('Page deadline exceeded',true);void context.close().catch(()=>{});},deadlineMs);
  try {
    await context.route('**/*', route => analytics(route.request().url()) ? route.abort() : route.continue());
    const page = await context.newPage();
    page.on('console', message=>{if(message.type()==='error') record('Console: '+message.text());});
    page.on('pageerror', error=>record('JavaScript: '+error.message,true));
    page.on('requestfailed', request=>{
      if (!analytics(request.url())) record('Request: '+new URL(request.url()).origin+new URL(request.url()).pathname+' '+request.failure()?.errorText);
    });
    page.on('response', response=>{
      if (response.status()>=400 && !analytics(response.url()))
        record('HTTP '+response.status()+' '+new URL(response.url()).origin+new URL(response.url()).pathname);
    });
    const response = await page.goto(check.url,{waitUntil:'domcontentloaded',timeout:deadlineMs});
    if (!response?.ok()) throw new Error('Unsuccessful document response: '+response?.status());
    if (check.kind==='blog') {
      await page.locator('.site-footer .copyright a').first().waitFor({state:'visible',timeout:deadlineMs});
      await page.locator('article a[href]:not([href=""]) .post-card-title').first().waitFor({state:'visible',timeout:deadlineMs});
    } else {
      const root = page.locator('[data-load-state]');
      await root.waitFor({state:'visible',timeout:deadlineMs});
      await page.waitForFunction(()=>['ready','error'].includes(document.querySelector('[data-load-state]')?.getAttribute('data-load-state') ?? ''),null,{timeout:deadlineMs});
      if (await root.getAttribute('data-load-state')!=='ready') throw new Error('Application reports error');
      await root.locator(check.renderer+' .mapboxgl-canvas').first().waitFor({state:'visible',timeout:deadlineMs});
      await root.getByRole('slider').first().waitFor({state:'visible',timeout:deadlineMs});
    }
    await page.waitForTimeout(observationMs);
    if (check.kind==='map' && await page.locator('[data-load-state]').getAttribute('data-load-state')!=='ready')
      throw new Error('Application lost readiness');
  } catch (error) {record(String(error),true);}
  finally {await context.close().catch(error=>record('Context cleanup: '+String(error),true));clearTimeout(timer);}
  return {id:check.id,url:check.url,failed,durationMs:Date.now()-start,diagnostics};
}

export async function checkOrigin(url=originUrl):Promise<Result> {
  const start=Date.now();
  const result:Result={id:'ghost-origin',url,failed:false,durationMs:0,diagnostics:[]};
  try {
    const response=await fetch(url,{signal:AbortSignal.timeout(10_000)});
    const finalUrl=new URL(response.url);
    if(!response.ok || finalUrl.searchParams.get('uptime')!=='1') throw new Error('Origin status/query: '+response.status+' '+response.url);
    const cache=response.headers.get('cf-cache-status');
    if (!['BYPASS','DYNAMIC'].includes(cache ?? '')) throw new Error('Cache bypass unverified: '+cache);
    if (!response.headers.get('content-type')?.includes('text/html')) throw new Error('Not HTML');
    const html=await response.text();
    if(!html.includes('site-footer') || !html.includes('post-card-title')) throw new Error('Missing site content');
  } catch(error) {result.failed=true;result.diagnostics.push(String(error));}
  result.durationMs=Date.now()-start;
  return result;
}

export async function runChecks(browser:Browser):Promise<Result[]> {
  return Promise.all([
    ...checks.map(check=>checkPage(browser,check).catch(error=>({id:check.id,url:check.url,failed:true,durationMs:0,diagnostics:[String(error)]}))),
    checkOrigin(),
  ]);
}
