import {after,before,test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium, type Browser} from 'playwright-core';
import {checkPage,checkOrigin,analytics,requiredRequests} from '../src/checks.js';

let browser:Browser;
let base:string;
let analyticsRequests=0;
const fixtures=new URL('../../tests/fixtures/',import.meta.url);
const server=createServer(async(req,res)=>{
  const url=new URL(req.url!,'http://fixture');
  if(url.pathname==='/cdn-cgi/rum') analyticsRequests++;
  if(url.pathname==='/origin') {
    res.setHeader('content-type','text/html');
    res.setHeader('cf-cache-status',url.searchParams.get('cache') ?? 'DYNAMIC');
    res.end(await readFile(new URL('blog.html',fixtures)));return;
  }
  if(url.pathname==='/broken') {res.writeHead(502);res.end('bad gateway');return;}
  if(url.pathname==='/app.js') {
    const referer=new URL(req.headers.referer!);
    if(referer.searchParams.get('case')==='script') {res.writeHead(503);res.end();return;}
    res.setHeader('content-type','text/javascript');
    res.end(await readFile(new URL('app.js',fixtures)));return;
  }
  if(url.pathname.startsWith('/data/')) {
    const scenario=new URL(req.headers.referer!).searchParams.get('case');
    res.writeHead(scenario==='data' || url.pathname.endsWith('/1.json')?404:200,{'content-type':'application/json'});
    res.end('{}');return;
  }
  if(url.pathname==='/optional.ico') {res.writeHead(404);res.end();return;}
  res.setHeader('content-type','text/html');
  res.end(await readFile(new URL('map.html',fixtures)));
});
before(async()=>{
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const address=server.address();
  if(!address || typeof address==='string') throw new Error('No server address');
  base='http://127.0.0.1:'+address.port;
  browser=await chromium.launch({headless:true});
});
after(async()=>{await browser?.close();await new Promise<void>(resolve=>server.close(()=>resolve()));});
test('parallel pages report independently; diagnostics and blocked analytics do not fail healthy pages',async()=>{
  const results=await Promise.all(['console','exception','never','script','data'].map(scenario=>
    checkPage(browser,{id:scenario,url:base+'/?case='+scenario,kind:'map'},2000,100)));
  assert.deepEqual(results.map(result=>result.failed),[false,true,true,true,true]);
  assert.ok(results[0]!.diagnostics.some(line=>line.includes('optional diagnostic')));
  assert.equal(analyticsRequests,0);
});
test('document 502 fails and uncached Ghost content passes only with verified bypass',async()=>{
  assert.equal((await checkPage(browser,{id:'blog',url:base+'/broken',kind:'blog'},2000,0)).failed,true);
  assert.equal((await checkOrigin(base+'/origin?uptime=1')).failed,false);
  assert.equal((await checkOrigin(base+'/origin?uptime=1&cache=HIT')).failed,true);
  assert.equal((await checkOrigin(base+'/origin')).failed,true);
});
test('analytics exclusion is narrow and later intervals are optional',()=>{
  assert.equal(analytics('https://static.cloudflareinsights.com/beacon.min.js'),true);
  assert.equal(analytics('https://example.com/beacon.min.js'),false);
  const required=requiredRequests();
  const request=(path:string)=>({url:()=>base+path,resourceType:()=>'fetch'});
  assert.equal(required(request('/data/cnec/v3/0.json')),true);
  assert.equal(required(request('/data/cnec/v3/1.json')),false);
  assert.equal(required(request('/data/cnec/v3/0.json')),true);
});
