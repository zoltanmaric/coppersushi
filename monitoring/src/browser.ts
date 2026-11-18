import {chromium as playwright} from 'playwright-core';
import chromium from '@sparticuz/chromium';

export async function launchBrowser(local=false) {
  return playwright.launch(local ? {headless:true} : {
    executablePath:await chromium.executablePath(),
    // Separate renderer processes allow independently closed parallel contexts.
    args:chromium.args.filter(arg=>!['--single-process','--disable-web-security','--allow-running-insecure-content'].includes(arg)),
    headless:true,
    timeout:30_000,
  });
}
