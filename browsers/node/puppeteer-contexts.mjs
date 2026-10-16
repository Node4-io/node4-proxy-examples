// Puppeteer: a browser context per identity, each with its own sticky session.
// The proxy server is set per context; the username and password go to
// page.authenticate(), because Chrome does not accept them in the proxy URL.
//   npm install && node puppeteer-contexts.mjs
import puppeteer from "puppeteer";
import { GATEWAY, IP_URL, PASS, checkCredentials, newSessionId, sessionUser } from "./env.mjs";

const CONTEXTS = 3;
await checkCredentials();

const browser = await puppeteer.launch(); // headless
try {
  for (let i = 1; i <= CONTEXTS; i++) {
    const session = newSessionId();
    const context = await browser.createBrowserContext({ proxyServer: `http://${GATEWAY}` });
    try {
      const page = await context.newPage();
      await page.authenticate({ username: sessionUser(session), password: PASS });
      await page.goto(IP_URL);
      const first = JSON.parse(await page.$eval("body", (b) => b.innerText)).ip;
      await page.goto(IP_URL);
      const again = JSON.parse(await page.$eval("body", (b) => b.innerText)).ip;
      console.log(`context ${i} (session ${session}): ${first}, reload ${again}`);
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
