# Command-line tools and system settings

How to point common tools at Node4. The examples use the Rotating Datacenter gateway; swap in another endpoint from the table in the [root README](../README.md) (a static `IP:4443`, `gw-rotating_unmetered.node4.io:8084`, `gw-residential.node4.io:8082`) and nothing else changes.

Every snippet marked **Tested** was run through a live Node4 gateway or static proxy. The few that were not are marked and say why.

## The proxy URL

Most tools take one URL:

```
http://USER:PASS@gw-rotating_datacenter.node4.io:8083       HTTP proxy (also for https:// sites)
socks5h://USER:PASS@gw-rotating_datacenter.node4.io:1083    SOCKS5, DNS resolved by the proxy (paid plans)
```

Username options such as `USER-session-abc123` or `USER-country-us` go in the same place.

### Special characters in the password

A password containing `@ : / # ? %` or spaces breaks the URL unless it is percent-encoded (`p@ss:w/rd` becomes `p%40ss%3Aw%2Frd`). Build the URL once and reuse it:

```sh
# bash
enc() { python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
export NODE4_URL="http://$(enc "$NODE4_USER"):$(enc "$NODE4_PASS")@gw-rotating_datacenter.node4.io:8083"
```

```powershell
# PowerShell
$env:NODE4_URL = "http://$([uri]::EscapeDataString($env:NODE4_USER)):$([uri]::EscapeDataString($env:NODE4_PASS))@gw-rotating_datacenter.node4.io:8083"
```

Tested: curl, wget, git and pip all decoded a fully percent-encoded password correctly.

Tools with separate username and password settings (`wget --proxy-user`, `aria2c --all-proxy-passwd`, curl `-U`, proxychains) need no encoding.

On a server with a fixed IP, [IP whitelisting](https://node4.io/help/authentication) avoids credentials entirely: connections from a whitelisted IP need no username or password. It is also the only option for software that cannot send proxy credentials (see [Windows](#windows-system-proxy)).

## Environment variables

```sh
# bash / zsh: set both cases, because tools disagree on which they read
export http_proxy="$NODE4_URL" https_proxy="$NODE4_URL"
export HTTP_PROXY="$NODE4_URL" HTTPS_PROXY="$NODE4_URL"
export no_proxy="localhost,127.0.0.1" NO_PROXY="localhost,127.0.0.1"
# optional, for tools that understand SOCKS (curl, Python requests[socks])
export ALL_PROXY="socks5h://USER:PASS@gw-rotating_datacenter.node4.io:1083"
```

```powershell
# PowerShell (current session)
$env:HTTP_PROXY  = $env:NODE4_URL
$env:HTTPS_PROXY = $env:NODE4_URL
$env:NO_PROXY    = "localhost,127.0.0.1"
```

```bat
:: cmd (current window). No spaces around "=".
set HTTP_PROXY=http://USER:PASS@gw-rotating_datacenter.node4.io:8083
set HTTPS_PROXY=http://USER:PASS@gw-rotating_datacenter.node4.io:8083
```

Windows environment variable names are not case-sensitive, so one spelling covers both.

Who reads what (all tested):

| Tool | Reads | Notes |
|---|---|---|
| curl | `http_proxy` (lowercase only), `HTTPS_PROXY` / `https_proxy`, `ALL_PROXY`, `NO_PROXY` | uppercase `HTTP_PROXY` is ignored for `http://` URLs, on purpose |
| wget | `http_proxy`, `https_proxy` (lowercase only) | uppercase `HTTPS_PROXY` is ignored |
| Windows `curl.exe` | `HTTPS_PROXY` set from PowerShell or cmd | |
| pip | `HTTPS_PROXY`, `PIP_PROXY` | |
| npm, pnpm | `HTTPS_PROXY` | |
| Python requests, urllib | both cases; requests also `ALL_PROXY=socks5h://...` with `requests[socks]` installed | |
| Go `net/http` default client | `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY` | ignores `ALL_PROXY` |
| Node.js `fetch` | nothing, unless `NODE_USE_ENV_PROXY=1` (tested on Node 24) | or pass a `ProxyAgent`, see [`node/`](../node/) |
| Windows PowerShell 5.1 `Invoke-WebRequest` | nothing | use `-Proxy` and `-ProxyCredential` |
| Docker containers | nothing from your shell | use `~/.docker/config.json`, see [Docker](#docker) |

```powershell
# Windows PowerShell 5.1
$cred = New-Object PSCredential($env:NODE4_USER, (ConvertTo-SecureString $env:NODE4_PASS -AsPlainText -Force))
Invoke-RestMethod https://api.ipify.org -Proxy http://gw-rotating_datacenter.node4.io:8083 -ProxyCredential $cred
```

## wget

```sh
https_proxy="$NODE4_URL" wget -qO- https://api.ipify.org

# or keep the credentials out of the URL
wget -qO- -e use_proxy=on -e https_proxy=http://gw-rotating_datacenter.node4.io:8083 \
     --proxy-user="$NODE4_USER" --proxy-password="$NODE4_PASS" https://api.ipify.org
```

`~/.wgetrc`, so every run uses the proxy (Tested):

```
use_proxy = on
http_proxy = http://gw-rotating_datacenter.node4.io:8083/
https_proxy = http://gw-rotating_datacenter.node4.io:8083/
proxy_user = YOUR-USERNAME
proxy_password = YOUR-PASSWORD
```

## git

```sh
# one command
git -c http.proxy="$NODE4_URL" ls-remote https://github.com/Node4-io/node4-proxy-examples HEAD

# every https:// remote for this user
git config --global http.proxy "$NODE4_URL"
git config --global --unset http.proxy          # undo

# one remote only
git config remote.origin.proxy "$NODE4_URL"

# over SOCKS5 (paid plans)
git config --global http.proxy "socks5h://USER:PASS@gw-rotating_datacenter.node4.io:1083"
```

Tested on Linux git and Git for Windows. `http.proxy` covers `https://` remotes only; `git@host:` remotes use SSH, see [SSH](#ssh).

## pip

```sh
pip install --proxy "$NODE4_URL" requests
HTTPS_PROXY="$NODE4_URL" pip install requests
```

Or permanently in `pip.conf` (`~/.config/pip/pip.conf` on Linux, `%APPDATA%\pip\pip.ini` on Windows):

```ini
[global]
proxy = http://USER:PASS@gw-rotating_datacenter.node4.io:8083
```

## npm, pnpm, yarn

```sh
# npm (writes to ~/.npmrc in plain text)
npm config set proxy "$NODE4_URL"
npm config set https-proxy "$NODE4_URL"
npm config delete proxy && npm config delete https-proxy    # undo

# or per command
npm view is-number version --proxy "$NODE4_URL" --https-proxy "$NODE4_URL"
```

- **pnpm** reads the same `proxy` and `https-proxy` keys from `.npmrc`. Tested with `pnpm add`.
- **Yarn 1**: `yarn info is-number version --proxy "$NODE4_URL" --https-proxy "$NODE4_URL"`, or the same keys with `yarn config set` (the flags were tested, `config set` was not).
- **Yarn 2+** (Berry) uses `.yarnrc.yml`:

  ```yaml
  httpProxy: "http://USER:PASS@gw-rotating_datacenter.node4.io:8083"
  httpsProxy: "http://USER:PASS@gw-rotating_datacenter.node4.io:8083"
  ```

Each was tested against a deliberately unreachable proxy first (the command fails), then against Node4 (it succeeds), so the setting is known to be used.

## Docker

**Containers and builds from your machine**: put the proxy in `~/.docker/config.json`. The Docker CLI then sets `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` and their lowercase forms in every new container and build (Tested):

```json
{
  "proxies": {
    "default": {
      "httpProxy": "http://USER:PASS@gw-rotating_datacenter.node4.io:8083",
      "httpsProxy": "http://USER:PASS@gw-rotating_datacenter.node4.io:8083",
      "noProxy": "localhost,127.0.0.1"
    }
  }
}
```

The credentials sit in that file in plain text, and anyone who can run `docker inspect` on your containers can read them.

**One build only**: `HTTP_PROXY`, `HTTPS_PROXY` and their lowercase forms are predefined build arguments, so no `ARG` line is needed (Tested with `curl` and `apt-get` inside the build):

```sh
docker build --build-arg HTTPS_PROXY="$NODE4_URL" --build-arg http_proxy="$NODE4_URL" .
```

**The daemon itself** (`docker pull`): the daemon reads its own environment, not yours. With systemd, create `/etc/systemd/system/docker.service.d/http-proxy.conf`:

```ini
[Service]
Environment="HTTP_PROXY=http://USER:PASS@gw-rotating_datacenter.node4.io:8083"
Environment="HTTPS_PROXY=http://USER:PASS@gw-rotating_datacenter.node4.io:8083"
Environment="NO_PROXY=localhost,127.0.0.1"
```

```sh
sudo systemctl daemon-reload && sudo systemctl restart docker
docker info | grep -i proxy
```

systemd treats `%` as a special character: a percent-encoded password must double every `%` (`p%40ss` becomes `p%%40ss`). We tested that a Docker daemon started with these variables pulls through Node4 (and fails with a dead proxy); the systemd drop-in itself was not run, because our test daemon does not run under systemd. On Docker Desktop, use **Settings → Resources → Proxies** instead.

## apt and dnf

apt, in `/etc/apt/apt.conf.d/95proxy` (Tested; apt sent `Proxy-Authorization` and fetched the index):

```
Acquire::http::Proxy "http://USER:PASS@gw-rotating_datacenter.node4.io:8083/";
Acquire::https::Proxy "http://USER:PASS@gw-rotating_datacenter.node4.io:8083/";
```

dnf, in `/etc/dnf/dnf.conf` under `[main]` (not tested here; a dnf metadata download is too large for our test budget):

```ini
proxy=http://gw-rotating_datacenter.node4.io:8083
proxy_username=YOUR-USERNAME
proxy_password=YOUR-PASSWORD
```

For package mirrors, a static proxy or the per-connection Rotating Unmetered gateway is cheaper than a per-GB plan.

## proxychains-ng

Runs any TCP program through the proxy. proxychains refuses a hostname for the first proxy in the list, so resolve the gateway and use the IP:

```sh
getent hosts gw-rotating_datacenter.node4.io      # or: nslookup / dig +short
```

`proxychains.conf` (or pass `-f FILE`):

```
strict_chain
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
socks5  GATEWAY-IP  1083  YOUR-USERNAME  YOUR-PASSWORD
# or over HTTP:
# http  GATEWAY-IP  8083  YOUR-USERNAME  YOUR-PASSWORD
# a static proxy:
# socks5  203.0.113.10  1443  YOUR-USERNAME  YOUR-PASSWORD
```

```sh
proxychains4 -q curl -s https://api.ipify.org
```

Tested with socks5 and http entries, rotating and static.

## aria2c

```sh
aria2c --all-proxy="$NODE4_URL" https://example.com/file.iso
aria2c --all-proxy=http://gw-rotating_datacenter.node4.io:8083 \
       --all-proxy-user="$NODE4_USER" --all-proxy-passwd="$NODE4_PASS" https://example.com/file.iso
```

Tested. aria2 speaks HTTP proxies only, not SOCKS. aria2 splits a download over several connections, and on a rotating gateway each connection can leave from a different IP; add `-session-ID` to the username, or use a static proxy, if the server objects.

## yt-dlp

```sh
yt-dlp --proxy "$NODE4_URL" URL
yt-dlp --proxy "socks5://USER:PASS@gw-rotating_datacenter.node4.io:1083" URL
```

Tested with both. Or put `--proxy ...` on a line in `~/.config/yt-dlp/config`.

## SSH

**Port 22 is not open through Node4.** A `CONNECT` to port 22 is refused by the gateways (HTTP 403; SOCKS5 "not allowed by ruleset"), and static proxies do not open it either. SSH works to servers that listen on port 443, such as GitHub's `ssh.github.com`.

`~/.ssh/config`, with ncat (from nmap):

```
Host github.com
    HostName ssh.github.com
    Port 443
    ProxyCommand ncat --proxy gw-rotating_datacenter.node4.io:8083 --proxy-type http --proxy-auth USER:PASS %h %p
```

Over SOCKS5, use `--proxy gw-rotating_datacenter.node4.io:1083 --proxy-type socks5`. With `connect-proxy` instead of ncat:

```
    ProxyCommand connect-proxy -H gw-rotating_datacenter.node4.io:8083 %h %p
```

with `HTTP_PROXY_USER` and `HTTP_PROXY_PASSWORD` set in the environment. All three were tested against `ssh.github.com:443` (the SSH handshake completed and GitHub answered with its normal key check). ncat's `--proxy-auth` is visible in the process list; on a shared machine prefer connect-proxy, which reads the credentials from the environment, or IP whitelisting.

## Windows system proxy

Windows has two system proxy settings, and **neither can store a proxy username and password**:

- **Settings → Network & internet → Proxy → Manual** (WinINet, used by Edge, Chrome and many desktop apps). Apps either prompt for the credentials or fail with `407`.
- **WinHTTP**, used by services and some updaters:

  ```bat
  netsh winhttp set proxy proxy-server="203.0.113.10:4443" bypass-list="<local>"
  netsh winhttp show proxy
  netsh winhttp reset proxy
  ```

For either, [whitelist your public IP](https://node4.io/help/authentication) in the dashboard (or with the [API](../api/)) so connections need no credentials. We did not change the system proxy on our test machine; `netsh winhttp show proxy` was run to confirm the syntax.

## Checking it worked

Every tool above prints a Node4 exit IP for `https://api.ipify.org` when the proxy is in use, and your own IP when it is not. To check many proxies at once, see [`checker/`](../checker/).
