// axios through the proxy. Set proxy: false and hand axios an agent: axios's own `proxy`
// option does not open a CONNECT tunnel for https:// targets, so TLS is not end to end
// and many proxies reject the request. An agent tunnels properly.
import axios from "axios";
import { HttpsProxyAgent } from "https-proxy-agent";
import { proxyUrl } from "./env.mjs";

const agent = new HttpsProxyAgent(proxyUrl());
const client = axios.create({ httpAgent: agent, httpsAgent: agent, proxy: false, timeout: 30_000 });

const { data } = await client.get("https://api.ipify.org?format=json");
console.log("exit IP:", data.ip);
