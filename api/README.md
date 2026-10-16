# REST API

Manage your Node4 account from scripts: check that proxies are serving, export your proxy list, read usage, and add or remove whitelisted IPs.

1. Create an API key under **Settings → API Keys** on [node4.io](https://node4.io). Give it only the permissions you need.
2. Run:

```sh
pip install requests
export NODE4_API_KEY='n4k_...'
python node4_api.py status
python node4_api.py export proxies.txt
```

| Command | Permission | What it does |
|---|---|---|
| `status` | `read:proxies` | whether the account can make proxy requests right now, and why not if it can't |
| `export FILE` | `read:proxies` | writes `host:port:username:password`, one proxy per line |
| `usage` | `read:usage` | bandwidth and requests this month |
| `whitelist` | `read:profile` | lists whitelisted IPs |
| `whitelist-add IP [LABEL]` | `write:ip-whitelist` | whitelists a public IPv4 address |
| `whitelist-remove ID` | `write:ip-whitelist` | removes an entry by id |

The same calls with curl:

```sh
curl -H "Authorization: Bearer $NODE4_API_KEY" https://node4.io/api/v1/status
curl -H "Authorization: Bearer $NODE4_API_KEY" "https://node4.io/api/v1/proxies/list?format=txt"
curl -H "Authorization: Bearer $NODE4_API_KEY" -H "Content-Type: application/json" \
     -d '{"ipAddress":"198.51.100.7","label":"build server"}' https://node4.io/api/v1/ip-whitelist
```

`/proxies/list` also takes `format=csv`, and for `txt` a `fields` list and `separator` to match the order your tool expects, for example `?format=txt&fields=username,password,host,port&separator=:`.

Whitelisting the IP of a server lets it use your proxies with no username or password in its code. Whitelist entries must be single public IPv4 addresses; private ranges, IPv6 and CIDR blocks are refused.

Full reference: [API documentation](https://node4.io/help/proxy-management-api), OpenAPI spec at `https://node4.io/openapi.json`. Limit: 60 requests per minute per key.
