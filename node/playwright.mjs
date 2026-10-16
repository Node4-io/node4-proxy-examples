// Playwright: credentials go in the separate username/password fields, not in the URL.
// (npm i playwright && npx playwright install chromium)
// More browser examples (per-context sessions, Selenium, a local forwarder): ../browsers/
import { chromium } from "playwright";
import { GATEWAY, PASS, USER } from "./env.mjs";

const browser = await chromium.launch({
  proxy: { server: `http://${GATEWAY}`, username: USER, password: PASS },
});
try {
  const page = await browser.newPage();
  await page.goto("https://api.ipify.org", { timeout: 20000 });
  console.log("browser exit IP:", (await page.textContent("body")).trim());
} catch (err) {
  // Chromium answers a rejected proxy password again instead of failing, so a wrong
  // NODE4_USER / NODE4_PASS shows up here as a timeout rather than a 407.
  if (err.name === "TimeoutError") {
    console.error("Timed out. If this repeats, check NODE4_USER / NODE4_PASS.");
    process.exitCode = 1;
  } else {
    throw err;
  }
} finally {
  await browser.close();
}
