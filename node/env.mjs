// Shared settings for the examples: credentials and endpoints from the environment.
export const USER = process.env.NODE4_USER ?? "";
export const PASS = process.env.NODE4_PASS ?? "";
export const GATEWAY = process.env.NODE4_GATEWAY ?? "gw-rotating_datacenter.node4.io:8083";

if (!USER || !PASS) {
  console.error("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
  process.exit(1);
}

/** scheme://user:pass@host:port with the credentials percent-encoded. */
export function proxyUrl({ endpoint = GATEWAY, user = USER, scheme = "http" } = {}) {
  return `${scheme}://${encodeURIComponent(user)}:${encodeURIComponent(PASS)}@${endpoint}`;
}

/** The SOCKS5 port that pairs with an HTTP endpoint (8083 -> 1083, 4443 -> 1443, ...). */
export function socksEndpoint(endpoint = GATEWAY) {
  const [host, port] = [endpoint.slice(0, endpoint.lastIndexOf(":")), endpoint.slice(endpoint.lastIndexOf(":") + 1)];
  const pairs = { 8082: "1082", 8083: "1083", 8084: "1084", 4443: "1443" };
  return `${host}:${pairs[port] ?? port}`;
}
