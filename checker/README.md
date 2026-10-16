# node4check

A proxy checker for the command line. It tests a list of proxies, or a rotating gateway, and reports for each one whether it works, the exit IP, and the latency. For a gateway it also tests that new connections rotate and that a session ID holds one exit.

One file, Python 3.9 or newer, no packages to install. SOCKS5 is built in.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'

python node4check.py 203.0.113.10:4443 203.0.113.11:4443      # static proxies
python node4check.py -f proxies.txt --protocol both --geo       # a list, over HTTP and SOCKS5
python node4check.py --gateway                                  # rotating gateway: rotation + sticky test
python node4check.py --gateway gw-residential.node4.io:8082 --json
```

Output:

```
CHECK     PROXY                                 PROTO  STATUS  EXIT IP          MS   DETAIL
gateway   gw-rotating_datacenter.node4.io:8083  http   ok      46.173.86.153    586
rotation  gw-rotating_datacenter.node4.io:8083  http   ok      45.185.54.130    414
rotation  gw-rotating_datacenter.node4.io:8083  http   ok      95.164.169.210   440
rotation  gw-rotating_datacenter.node4.io:8083  http   ok      46.173.71.206    429
rotation  gw-rotating_datacenter.node4.io:8083  http   ok      95.164.97.59     452
rotation  gw-rotating_datacenter.node4.io:8083  http   ok      206.232.112.234  859
sticky    gw-rotating_datacenter.node4.io:8083  http   ok      45.170.12.30     606  session n4c7c67a6ceaf
sticky    gw-rotating_datacenter.node4.io:8083  http   ok      45.170.12.30     477  session n4c7c67a6ceaf
sticky    gw-rotating_datacenter.node4.io:8083  http   ok      45.170.12.30     483  session n4c7c67a6ceaf

rotation/http    PASS  5 new connections -> 5 distinct exits
sticky/http      PASS  session n4c7c67a6ceaf: 3 connections -> 1 exit (45.170.12.30)

9/9 checks ok, median 477 ms
```

## Input

Proxies come from the command line, from `-f FILE` (`-f -` reads stdin), or from `NODE4_PROXY` when nothing else is given. Lines starting with `#` are skipped. Any of these formats:

| Format | Example |
|---|---|
| `HOST:PORT` | `203.0.113.10:4443` (credentials from `NODE4_USER` / `NODE4_PASS`) |
| `HOST:PORT:USER:PASS` | `203.0.113.10:4443:alice:s3cret`, the format of the dashboard and [API](../api/) export |
| `USER:PASS@HOST:PORT` | `alice:s3cret@203.0.113.10:4443` |
| URL | `http://alice:s3cret@203.0.113.10:4443`, `socks5h://...:1443`, `socks5://...` |

In URLs, percent-encode special characters in the password (`p@ss` is `p%40ss`). The other formats take the password as written.

`socks5h://` sends the hostname to the proxy; `socks5://` resolves it on your machine first.

## Options

| Option | Default | Meaning |
|---|---|---|
| `-g, --gateway [HOST:PORT]` | `$NODE4_GATEWAY` or `gw-rotating_datacenter.node4.io:8083` | check a gateway, with the rotation and sticky tests |
| `-p, --protocol http\|socks5\|both` | `http` | for entries without a scheme. `socks5` and `both` move to the paired SOCKS5 port: 4443→1443, 8083→1083, 8084→1084, 8082→1082 |
| `-c, --concurrency N` | 10 | connections at once. The free tier allows 10 |
| `-t, --timeout S` | 15 | seconds per connection step |
| `--rotation N` | 5 | gateway: N new connections; passes if they leave from more than one IP. `0` skips |
| `--sticky N` | 3 | gateway: N connections with one random `-session-` ID; passes if all leave from one IP. `0` skips |
| `--geo` | off | look up each exit IP's country. The lookup goes to ipinfo.io directly from your machine, not through the proxy |
| `--url URL` | `https://api.ipify.org` | any URL that returns the caller's IP as text or as JSON `{"ip": ...}` |
| `--json`, `--csv` | table | machine-readable output |

## Statuses

| Status | Meaning | What to do |
|---|---|---|
| `ok` | the proxy answered and the target returned an IP | |
| `auth_failed` | `407` from an HTTP proxy, or SOCKS5 rejected the login | check the username and password, and that your plan includes this product and port. Do not retry in a loop: repeated failed logins can get your IP blocked |
| `timeout` | no answer in time; DETAIL says at which step | |
| `refused` | nothing listening on that port | check the host and port |
| `proxy_error` | the proxy answered but would not connect (for example `CONNECT answered 502`, or a SOCKS5 error) | |
| `tls_error`, `bad_response`, `dns_error` | the TLS handshake, the target's answer, or the proxy hostname lookup failed | |

For a static proxy, traffic leaves from the IP you connect to; if the exit differs, DETAIL says so.

The exit status is `0` when every check and gateway test passed, `1` when any failed, `2` for a usage error, so it works in scripts and cron:

```sh
python node4check.py -f proxies.txt --csv > report.csv || echo "some proxies failed"
```

Credentials are never printed in any output format.

## Every connection is new

Each check opens its own connection, so on a rotating gateway each one can get a new exit. That is what the rotation test relies on. A proxy list with 100 entries and `--protocol both` makes 200 connections; each fetches a few hundred bytes.

## Tests

```sh
python -m unittest -v test_node4check.py
```

The tests need no network or credentials. They cover the input formats, the SOCKS5 handshake against a local fake server, `407` and other failure classification, and the output formats.
