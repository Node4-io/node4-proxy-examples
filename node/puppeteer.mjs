// Puppeteer: Chrome takes the proxy as a launch flag without credentials;
// page.authenticate() answers the proxy's 407 challenge. (npm i puppeteer)
import puppeteer from "puppeteer";
import { GATEWAY, PASS, USER } from "./env.mjs";

const browser = await puppeteer.launch({ args: [`--proxy-server=http://${GATEWAY}`] });
const page = await browser.newPage();
await page.authenticate({ username: USER, password: PASS });
await page.goto("https://api.ipify.org");
console.log("browser exit IP:", await page.evaluate(() => document.body.innerText.trim()));
await browser.close();
