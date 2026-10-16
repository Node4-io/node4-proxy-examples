// Playwright: one browser, one context per identity, a sticky session per context.
// A browser reuses connections, so pin each context to one exit with a -session- ID
// and open a new context (new ID) to change IP.
//   npm install && npx playwright install chromium && node playwright-contexts.mjs
import { chromium } from "playwright";
import { GATEWAY, IP_URL, PASS, checkCredentials, newSessionId, sessionUser } from "./env.mjs";

const CONTEXTS = 3;
await checkCredentials(); // a wrong password otherwise shows up as a page-load timeout

const browser = await chromium.launch(); // headless; the proxy is set per context
try {
  await Promise.all(
    Array.from({ length: CONTEXTS }, async (_, i) => {
      const session = newSessionId();
      const context = await browser.newContext({
        proxy: { server: `http://${GATEWAY}`, username: sessionUser(session), password: PASS },
      });
      try {
        const page = await context.newPage();
        const first = (await (await page.goto(IP_URL)).json()).ip;
        const again = (await (await page.goto(IP_URL)).json()).ip;
        console.log(`context ${i + 1} (session ${session}): ${first}, reload ${again}`);
      } finally {
        await context.close();
      }
    }),
  );
} finally {
  await browser.close();
}
