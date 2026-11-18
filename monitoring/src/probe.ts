import {launchBrowser} from './browser.js';
import {runChecks} from './checks.js';

const browser=await launchBrowser(process.env.LOCAL_BROWSER==='1');
try {
  const results=await runChecks(browser);
  console.log(JSON.stringify(results,null,2));
  process.exitCode=results.some(result=>result.failed)?1:0;
} finally {await browser.close();}
