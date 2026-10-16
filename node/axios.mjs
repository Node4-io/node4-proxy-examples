// axios through the proxy. Set proxy: false and hand axios an agent: axios's own `proxy`
// option sends HTTPS requests to the proxy without a CONNECT tunnel, which proxies refuse.
import axios from "axios";
import { HttpsProxyAgent } from "https-proxy-agent";
import { proxyUrl } from "./env.mjs";

const agent = new HttpsProxyAgent(proxyUrl());
const client = axios.create({ httpAgent: agent, httpsAgent: agent, proxy: false, timeout: 30_000 });

const { data } = await client.get("https://api.ipify.org?format=json");
console.log("exit IP:", data.ip);
