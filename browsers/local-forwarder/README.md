# Local forwarder

A small proxy that runs on your machine, takes connections on `127.0.0.1` with no login, and forwards them to Node4 with your username and password added. Use it for anything that cannot send proxy credentials:

- Chrome or Edge started by hand or by Selenium (`--proxy-server` takes no username or password)
- Firefox (its proxy settings have no username or password fields)
- desktop apps and tools that only take `host:port`

One file, Python 3.8+, standard library only. It handles HTTPS (`CONNECT` tunnels) and plain HTTP.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
python node4_forwarder.py
# http://127.0.0.1:8899 -> gw-rotating_datacenter.node4.io:8083 (rotating per connection)

curl -x http://127.0.0.1:8899 https://api.ipify.org
chrome --proxy-server=http://127.0.0.1:8899
```

## Options

| Option | Effect |
|---|---|
| `--upstream HOST:PORT` | the Node4 endpoint (default `NODE4_GATEWAY`, else `gw-rotating_datacenter.node4.io:8083`). A static `IP:4443` works too |
| `--session ID` | hold one exit IP (sticky session, up to 30 minutes) |
| `--sessions N` | open N ports in a row (8899, 8900, ...), each with its own session: one exit IP per port |
| `--country CC` | exit country: `us`, `it`, `es` on rotating; 170+ on residential |
| `--port N` | first listen port (default 8899) |
| `-v` | log each tunnel with its byte count |

Run several browsers with different IPs:

```sh
python node4_forwarder.py --sessions 3
# http://127.0.0.1:8899 -> ... (session 3f9c1a...)
# http://127.0.0.1:8900 -> ... (session 81d0e2...)
# http://127.0.0.1:8901 -> ... (session c47b55...)
```

## Inside your own script

```python
from node4_forwarder import Forwarder

fwd = Forwarder(user, password, upstream="gw-rotating_datacenter.node4.io:8083", session="job42")
port = fwd.start()          # background thread; returns the local port
# ... point your tool at http://127.0.0.1:{port} with no credentials ...
fwd.stop()
```

`../selenium_chrome.py` and `../selenium_firefox.py` do exactly this.

## Notes

- It listens on `127.0.0.1` only by default. Anyone who can reach the port can use your account, so if you pass `--host 0.0.0.0` keep it behind a firewall.
- A `407` from Node4 is logged and passed back to the client. It means wrong credentials or a product your plan does not include; retrying will not help.
- Browsers send some background traffic of their own (update checks, sign-in pings). It goes through the proxy too, and counts on per-GB plans. Run `-v` to see it.
- Plain-HTTP requests are sent one per connection, so each one carries your credentials. HTTPS tunnels stay open as long as the client keeps them.

## Tests

```sh
python -m unittest -v test_forwarder.py                 # offline, against a fake upstream
NODE4_LIVE=1 python -m unittest -v test_forwarder.py    # plus one real request through Node4
```
