// Rotation is per connection. One keep-alive agent reuses its tunnel and keeps one exit;
// a new connection per request can get a different exit each time. A session ID holds one
// exit across connections on purpose.
import { ProxyAgent, fetch } from "undici";
import { USER, proxyUrl } from "./env.mjs";

const URL = "https://api.ipify.org";

async function distinctExits(makeDispatcher, n = 5) {
  const seen = new Set();
  const shared = makeDispatcher();
  for (let i = 0; i < n; i++) {
    const d = shared ?? new ProxyAgent(proxyUrl());
    seen.add(await (await fetch(URL, { dispatcher: d })).text());
    if (!shared) await d.close();
  }
  if (shared) await shared.close();
  return seen.size;
}

console.log("one agent, 5 requests       ->", await distinctExits(() => new ProxyAgent(proxyUrl())), "exit(s)");
console.log("new agent per request       ->", await distinctExits(() => null), "exit(s)");

const sticky = proxyUrl({ user: `${USER}-session-${Math.random().toString(36).slice(2, 10)}` });
const seen = new Set();
for (let i = 0; i < 3; i++) {
  const d = new ProxyAgent(sticky);
  seen.add(await (await fetch(URL, { dispatcher: d })).text());
  await d.close();
}
console.log("session ID, new connections ->", seen.size, "exit(s) (expect 1)");
