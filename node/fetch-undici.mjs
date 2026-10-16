// Node's built-in fetch does not read HTTP_PROXY. Pass an undici ProxyAgent as the dispatcher.
import { ProxyAgent, fetch } from "undici";
import { proxyUrl } from "./env.mjs";

const dispatcher = new ProxyAgent(proxyUrl());
const res = await fetch("https://api.ipify.org?format=json", { dispatcher });
console.log("exit IP:", (await res.json()).ip);
await dispatcher.close();
