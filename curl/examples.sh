#!/usr/bin/env bash
# Node4 with curl. Set NODE4_USER and NODE4_PASS first; NODE4_PROXY (IP:4443) for the static line.
# Credentials go through -U (--proxy-user), so a password containing @ or : needs no escaping,
# and -sS keeps errors such as a 407 visible.
set -u
GW_ROT="gw-rotating_datacenter.node4.io"
AUTH="$NODE4_USER:$NODE4_PASS"

echo "1. Rotating gateway over HTTP: one exit IP per connection"
curl -sS -U "$AUTH" -x "http://$GW_ROT:8083" https://api.ipify.org; echo

echo "2. Same gateway over SOCKS5 (paid plans). socks5h resolves the hostname at the proxy"
curl -sS -U "$AUTH" -x "socks5h://$GW_ROT:1083" https://api.ipify.org; echo

echo "3. Sticky session: both requests leave from the same IP"
SID="demo$RANDOM"
for i in 1 2; do curl -sS -U "$NODE4_USER-session-$SID:$NODE4_PASS" -x "http://$GW_ROT:8083" https://api.ipify.org; echo; done

echo "4. Pick a country on the rotating pool (us, it or es)"
curl -sS -U "$NODE4_USER-country-it:$NODE4_PASS" -x "http://$GW_ROT:8083" https://ipinfo.io/country; echo

if [ -n "${NODE4_PROXY:-}" ]; then
  echo "5. A static proxy: traffic leaves from the IP you connect to"
  curl -sS -U "$AUTH" -x "http://$NODE4_PROXY" https://api.ipify.org; echo
fi

# Residential (needs a residential plan): country, state, city and ASN go in the username.
# curl -sS -U "$NODE4_USER-country-us-state-tx:$NODE4_PASS" -x http://gw-residential.node4.io:8082 https://ipinfo.io/json
