# Scripts

## smoke.sh

Runs the examples in this repo against live Node4 proxies and checks that each one prints an exit IP. Use it after changing an example, or to confirm your account works from every language at once.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
export NODE4_PROXY='203.0.113.10:4443'     # optional: also test one of your static proxies
bash scripts/smoke.sh
```

```
Node4 smoke test: gateway gw-rotating_datacenter.node4.io:8083
curl        PASS     3s
python      PASS     4s
node        PASS     2s
go          PASS     2s
scrapy      PASS     3s
checker     PASS     7s
java        PASS     2s
...
PASS 14  FAIL 0  SKIP 0
```

Each language runs on its local runtime if one is installed, otherwise in Docker (the folder is copied into the container, so nothing is written into your checkout), otherwise it is skipped with the reason. The first Docker run of a language downloads its image and takes longer.

| Option | Meaning |
|---|---|
| `--only curl,python` | run only these checks |
| `--skip kotlin,rust` | skip these checks |
| `--no-socks` | skip the SOCKS5 examples; use this on the free tier, which is HTTP(S) only |
| `--no-docker` / `--docker` | never use Docker / always use Docker |
| `--timeout SEC` | per-check limit (default 900) |
| `-v` | show every check's output (a failing check always shows its last lines) |
| `--list` | list the checks |

A full run makes about 50 small requests (the curl, Python and Go examples, a 3-item Scrapy crawl, a short [`node4check`](../checker/) rotation and sticky test, one request per other language, and a few browser page loads). On a per-GB plan that is well under 1 MB.

The exit status is `0` when nothing failed, so it can gate a CI job that has credentials in its secrets. Your password is masked in everything the script prints.
