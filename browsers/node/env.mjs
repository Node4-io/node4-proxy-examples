// Shared settings for the browser examples: credentials and endpoints from the environment.
import { randomBytes } from "node:crypto";
import net from "node:net";

export const USER = process.env.NODE4_USER ?? "";
export const PASS = process.env.NODE4_PASS ?? "";
export const GATEWAY = process.env.NODE4_GATEWAY ?? "gw-rotating_datacenter.node4.io:8083";
export const IP_URL = "https://api.ipify.org?format=json"; // a tiny page: little data on per-GB plans

if (!USER || !PASS) {
  console.error("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
  process.exit(1);
}

/** A fresh sticky-session ID. */
export const newSessionId = () => randomBytes(6).toString("hex");

/** USER-session-ID: the gateway holds one exit IP for this ID (up to 30 minutes). */
export const sessionUser = (session, user = USER) => `${user}-session-${session}`;

/**
 * Exit early if the proxy rejects the credentials. Browsers report a rejected proxy
 * password badly (a timeout or a generic tunnel error), so check once with a single
 * CONNECT handshake: no page load, no data.
 */
export async function checkCredentials(endpoint = GATEWAY, user = USER) {
  const i = endpoint.lastIndexOf(":");
  const token = Buffer.from(`${user}:${PASS}`).toString("base64");
  const status = await new Promise((resolve, reject) => {
    const sock = net.connect(Number(endpoint.slice(i + 1)), endpoint.slice(0, i), () =>
      sock.write(`CONNECT api.ipify.org:443 HTTP/1.1\r\nHost: api.ipify.org:443\r\n` +
                 `Proxy-Authorization: Basic ${token}\r\n\r\n`));
    sock.setTimeout(15000, () => sock.destroy(new Error(`timed out connecting to ${endpoint}`)));
    sock.once("data", (d) => { resolve(d.toString("latin1").split("\r\n")[0]); sock.destroy(); });
    sock.once("error", reject);
  });
  if (status.includes(" 407")) {
    console.error(`407 from ${endpoint}: wrong NODE4_USER / NODE4_PASS, or your plan does not include this product. Retrying will not help.`);
    process.exit(1);
  }
}
