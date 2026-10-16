// SOCKS5 (paid plans) with socks-proxy-agent. socks5h:// resolves hostnames at the proxy.
import https from "node:https";
import { SocksProxyAgent } from "socks-proxy-agent";
import { proxyUrl, socksEndpoint } from "./env.mjs";

const agent = new SocksProxyAgent(proxyUrl({ endpoint: socksEndpoint(), scheme: "socks5h" }));

https.get("https://api.ipify.org", { agent }, (res) => {
  let body = "";
  res.on("data", (c) => (body += c));
  res.on("end", () => console.log("exit IP over SOCKS5:", body));
}).on("error", (e) => {
  console.error(e.message);
  process.exit(1);
});
