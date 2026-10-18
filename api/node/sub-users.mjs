// One capped proxy login (sub-user) per client, with usage for invoicing.
//
//   export NODE4_API_KEY='n4k_...'
//   node sub-users.mjs list                        # read:proxies
//   node sub-users.mjs create acme-corp 50         # write:credentials; 50 GB monthly cap, prints the login once
//   node sub-users.mjs usage 412                   # read:usage, this UTC month
//   node sub-users.mjs cap 412 100                 # new cap in GB, or "none"
//   node sub-users.mjs disable 412 | enable 412
//   node sub-users.mjs delete 412 [--permanent]
//   node sub-users.mjs connect 412 residential     # gateway string for that client
//
// Writes are sent once, never retried automatically (a retried create can make a second login).
// Changes reach live traffic within about 2 minutes, and a cap can overrun slightly.
// Guide: https://node4.io/help/managing-sub-users-for-clients-with-the-api
import { parseArgs } from "node:util";
import { Node4Client, Node4Error } from "./node4client.mjs";

const GB = 1024; // the API counts in MB
const capText = (mb) => (mb == null ? "no cap" : `${Math.round(mb / GB)} GB`);
const { values: a, positionals: [cmd, id, arg] } = parseArgs({ allowPositionals: true, options: { permanent: { type: "boolean" } } });
const node4 = new Node4Client();

try {
  switch (cmd) {
    case "list": {
      const { plan, subUsers } = await node4.get("/sub-users");
      console.log(`${plan.used} of ${plan.maxSubUsers} sub-users, ${plan.active} active`);
      for (const s of subUsers) {
        console.log(`${String(s.id).padStart(6)}  ${(s.label ?? s.username).padEnd(24)} ${s.status.padEnd(10)} ` +
          `${((s.usage.bandwidthUsedMb ?? 0) / GB).toFixed(2).padStart(8)} GB / ${capText(s.limits.bandwidthLimitMb)}`);
      }
      break;
    }
    case "create": {
      const s = await node4.post("/sub-users", { label: id, bandwidthLimitMb: arg ? Number(arg) * GB : null });
      console.log(`created ${s.id}: ${s.username} / ${s.password}  (${capText(s.limits.bandwidthLimitMb)})`);
      console.log("Store the password now; send it to the client over a private channel.");
      break;
    }
    case "usage": {
      const { period: p } = await node4.get(`/sub-users/${Number(id)}/usage`);
      console.log(`${p.start.slice(0, 10)} to ${p.end.slice(0, 10)}: ${(p.bandwidthUsedMb / GB).toFixed(2)} GB of ${capText(p.bandwidthLimitMb)}`);
      break;
    }
    case "cap": {
      const s = await node4.patch(`/sub-users/${Number(id)}`, { bandwidthLimitMb: arg === "none" ? null : Number(arg) * GB });
      console.log(`${s.id}: cap ${capText(s.limits?.bandwidthLimitMb)}, status ${s.status}`);
      break;
    }
    case "disable":
    case "enable": {
      const s = await node4.patch(`/sub-users/${Number(id)}`, { status: cmd === "disable" ? "disabled" : "active" });
      console.log(`${s.id}: ${s.status}`);
      break;
    }
    case "delete":
      console.log(await node4.delete(`/sub-users/${Number(id)}`, a.permanent ? { permanent: "true" } : undefined));
      break;
    case "connect":
      console.log((await node4.post("/gateways/endpoint", { product: arg, credentialId: Number(id) })).url);
      break;
    default:
      console.error("usage: node sub-users.mjs list | create LABEL [GB] | usage ID | cap ID GB|none | disable ID | enable ID | delete ID [--permanent] | connect ID PRODUCT");
      process.exit(2);
  }
} catch (e) {
  if (e instanceof Node4Error) { console.error(e.message); process.exit(1); }
  throw e;
}
