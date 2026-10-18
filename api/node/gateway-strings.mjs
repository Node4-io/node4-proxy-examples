// Build gateway proxy strings with the API instead of assembling usernames by hand.
//
//   export NODE4_API_KEY='n4k_...'          # needs read:proxies
//   node gateway-strings.mjs                                     # your gateway products and logins
//   node gateway-strings.mjs rotating_datacenter --country us    # one rotating string
//   node gateway-strings.mjs residential --country us --state ny --count 5 --format hostport
//
// Products: rotating_datacenter (alias of rotating_shared), rotating_unmetered, residential.
// Rotating products take --country only; --state, --city and --asn are residential.
// --count N (up to 100) gives N strings, each with its own sticky session.
// Build once and reuse: strings stay valid as long as the login does. Output contains passwords.
// Guide: https://node4.io/help/building-proxy-strings-with-the-gateway-api
import { parseArgs } from "node:util";
import { Node4Client, Node4Error } from "./node4client.mjs";

const FORMATS = { url: "url", http: "http", socks5: "socks5", hostport: "hostPortUserPass" };
const { values: a, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    protocol: { type: "string" }, country: { type: "string" }, state: { type: "string" }, city: { type: "string" },
    asn: { type: "string" }, session: { type: "string" }, sticky: { type: "boolean" }, count: { type: "string" },
    "credential-id": { type: "string" }, format: { type: "string", default: "url" },
  },
});
const node4 = new Node4Client();
const product = positionals[0];

if (!product) {
  for (const g of (await node4.get("/gateways")).gateways) {
    const t = Object.entries(g.targeting).filter(([, v]) => v).map(([k]) => k).join(", ") || "none";
    console.log(`${g.product.padEnd(20)} ${g.host}  http ${g.ports.http}  socks5 ${g.ports.socks5}  targeting: ${t}` +
      (g.connectionLimit ? `  connection limit: ${g.connectionLimit}` : ""));
    for (const u of g.usernames) console.log(`    ${u.username.padEnd(32)} ${u.status.padEnd(10)} ${u.label ?? ""}`);
  }
  process.exit(0);
}

const num = (v) => (v === undefined ? undefined : Number(v));
const body = Object.fromEntries(Object.entries({
  product, protocol: a.protocol, country: a.country, state: a.state, city: a.city, asn: num(a.asn),
  session: a.session, sticky: a.sticky || undefined, count: num(a.count), credentialId: num(a["credential-id"]),
}).filter(([, v]) => v !== undefined));

try {
  const d = await node4.post("/gateways/endpoint", body);
  const field = FORMATS[a.format] ?? "url";
  for (const e of d.endpoints?.length ? d.endpoints : [d]) console.log(e[field]);
  console.error(`# ${d.name}, rotation ${d.rotation}, sticky ${d.sticky?.enabled ? `up to ${d.sticky.maxSeconds}s` : "off"}`);
} catch (e) {
  // 400 names the bad option, 422 lists the locations that exist, 404/409 point at the login.
  if (e instanceof Node4Error) { console.error(e.message); process.exit(1); }
  throw e;
}
