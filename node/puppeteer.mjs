// Puppeteer: Chrome takes the proxy as a launch flag without credentials;
// page.authenticate() answers the proxy's 407 challenge. (npm i puppeteer)
// More browser examples (per-context sessions, Selenium, a local forwarder): ../browsers/
import puppeteer from "puppeteer";
import { GATEWAY, PASS, USER } from "./env.mjs";

const browser = await puppeteer.launch({ args: [`--proxy-server=http://${GATEWAY}`] });
try {
  const page = await browser.newPage();
  await page.authenticate({ username: USER, password: PASS });
  const response = await page.goto("https://api.ipify.org");
  if (response.status() === 407) {
    // Without this check you would read Chrome's error page as if it were the answer.
    console.error("407 from the proxy: check NODE4_USER / NODE4_PASS. Retrying will not help.");
    process.exitCode = 1;
  } else {
    console.log("browser exit IP:", await page.evaluate(() => document.body.innerText.trim()));
  }
} finally {
  await browser.close();
}
