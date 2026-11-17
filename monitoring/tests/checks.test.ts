import {after,before,test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium, type Browser} from 'playwright-core';
import {checkPage,checkOrigin,analytics,checks} from '../src/checks.js';

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
  if(url.pathname==='/blog') {
    res.setHeader('content-type','text/html');
    const html=await readFile(new URL('blog.html',fixtures),'utf8');
    res.end(url.searchParams.has('unlinked') ? html.replace('<a href="/article">','<span>').replace('</h2></a>','</h2></span>') : html);return;
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
    res.writeHead(scenario==='data' || url.pathname.includes('2099-01-01') || url.pathname.endsWith('/1.json')?404:200,{'content-type':'application/json'});
    res.end('{}');return;
  }
  if(url.pathname==='/optional.js' || url.pathname==='/retry-data') {res.writeHead(503);res.end();return;}
  if(url.pathname==='/optional.ico') {res.writeHead(404);res.end();return;}
  res.setHeader('content-type','text/html');
  res.end((await readFile(new URL('map.html',fixtures),'utf8')).replace('cnec-view-map',url.searchParams.get('renderer') ?? 'cnec-view-map'));
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
    checkPage(browser,{id:scenario,url:base+'/?case='+scenario,kind:'map',renderer:'#cnec-view-map'},2000,100)));
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
test('analytics exclusion is narrow',()=>{
  assert.equal(analytics('https://static.cloudflareinsights.com/beacon.min.js'),true);
  assert.equal(analytics('https://example.com/beacon.min.js'),false);
});
test('optional asset failures and recovered data do not fail a ready page',async()=>{
  const result=await checkPage(browser,{id:'recovery',url:base+'/?case=recovery',kind:'map',renderer:'#cnec-view-map'},2000,100);
  assert.equal(result.failed,false);
  assert.ok(result.diagnostics.some(line=>line.includes('503')));
});

test('blog requires a visible linked article title',async()=>{
  for(const [query,failed] of [['',false],['?unlinked=1',true]] as const)
    assert.equal((await checkPage(browser,{id:'blog',url:base+'/blog'+query,kind:'blog'},1000,0)).failed,failed);
});
test('each map check rejects the other product renderer',async()=>{
  for(const check of checks.filter(check=>check.kind==='map')) {
    for(const renderer of ['cnec-view-map','opf-map']) {
      const result=await checkPage(browser,{...check,url:base+'/?renderer='+renderer},1000,0);
      assert.equal(result.failed,check.renderer!=='#'+renderer);
    }
  }
});
test('fatal reason survives a full diagnostic buffer',async()=>{
  const result=await checkPage(browser,{id:'noisy',url:base+'/?case=noisy',kind:'map',renderer:'#cnec-view-map'},1000,0);
  assert.equal(result.failed,true);
  assert.equal(result.diagnostics.length,50);
  assert.match(result.diagnostics[0]!,/fixture fatal after noise/);
});
