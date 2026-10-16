// Playwright: credentials go in the separate username/password fields, not in the URL.
// (npm i playwright && npx playwright install chromium)
import { chromium } from "playwright";
import { GATEWAY, PASS, USER } from "./env.mjs";

const browser = await chromium.launch({
  proxy: { server: `http://${GATEWAY}`, username: USER, password: PASS },
});
const page = await browser.newPage();
await page.goto("https://api.ipify.org");
console.log("browser exit IP:", (await page.textContent("body")).trim());
await browser.close();
