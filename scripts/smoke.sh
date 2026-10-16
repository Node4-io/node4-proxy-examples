#!/usr/bin/env bash
# Smoke test: run the examples in this repo against live Node4 proxies and check that
# each one prints an exit IP. Traffic is tiny (a full run makes well under 100 requests,
# each a few hundred bytes).
#
#   export NODE4_USER=... NODE4_PASS=...
#   export NODE4_PROXY=203.0.113.10:4443      # optional: also test a static proxy
#   scripts/smoke.sh                           # everything
#   scripts/smoke.sh --only curl,python,go     # a subset
#   scripts/smoke.sh --skip kotlin,rust --no-socks
#
# A language runs on the local runtime when one is installed, otherwise in Docker,
# otherwise it is skipped. Exit status: 0 if nothing failed, 1 if anything failed.
set -u

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ALL_CHECKS=(curl python node go scrapy checker java kotlin csharp php powershell ruby rust browsers)

usage() {
  cat <<EOF
Usage: scripts/smoke.sh [options]

  --only a,b,c     run only these checks
  --skip a,b,c     skip these checks
  --no-socks       skip the SOCKS5 examples (the free tier is HTTP(S) only)
  --no-docker      never fall back to Docker; skip languages with no local runtime
  --docker         always use Docker, even when a local runtime exists
  --timeout SEC    per-check time limit (default 900; first Docker runs download images)
  -v, --verbose    print each check's output
  --list           list the checks and exit

Checks: ${ALL_CHECKS[*]}

Environment: NODE4_USER and NODE4_PASS (required), NODE4_GATEWAY (default
gw-rotating_datacenter.node4.io:8083), NODE4_PROXY (a static IP:4443, optional).
EOF
}

ONLY="" SKIP="" SOCKS=1 DOCKER=auto VERBOSE=0 LIMIT=900
while [ $# -gt 0 ]; do
  case "$1" in
    --only) ONLY="${2:-}"; shift ;;
    --skip) SKIP="${2:-}"; shift ;;
    --no-socks) SOCKS=0 ;;
    --no-docker) DOCKER=never ;;
    --docker) DOCKER=always ;;
    --timeout) LIMIT="${2:-900}"; shift ;;
    -v|--verbose) VERBOSE=1 ;;
    --list) printf '%s\n' "${ALL_CHECKS[@]}"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

for name in ${ONLY//,/ } ${SKIP//,/ }; do
  case " ${ALL_CHECKS[*]} " in *" $name "*) ;; *) echo "unknown check: $name (see --list)" >&2; exit 2 ;; esac
done

if [ -z "${NODE4_USER:-}" ] || [ -z "${NODE4_PASS:-}" ]; then
  echo "Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies)." >&2
  exit 2
fi
export NODE4_USER NODE4_PASS
export NODE4_GATEWAY="${NODE4_GATEWAY:-gw-rotating_datacenter.node4.io:8083}"
[ -n "${NODE4_PROXY:-}" ] && export NODE4_PROXY

WORK=$(mktemp -d "${TMPDIR:-/tmp}/node4-smoke.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

# ----------------------------------------------------------------------------- helpers

IP_RE='([0-9]{1,3}\.){3}[0-9]{1,3}'
SKIP_CODE=77

have() { command -v "$1" >/dev/null 2>&1; }
skip() { echo "$*" > "$WORK/skip-reason"; return $SKIP_CODE; }
fail() { echo "ASSERT: $*"; return 1; }

# Pass when the output holds at least $2 (default 1) IPv4 addresses.
expect_ips() {
  local n
  n=$(grep -Eo "$IP_RE" "$1" | wc -l | tr -d ' ')
  [ "$n" -ge "${2:-1}" ] || fail "expected at least ${2:-1} IP address(es) in the output, found $n"
}

# Never show the password, whatever a program prints.
redact() {
  local line
  while IFS= read -r line || [ -n "$line" ]; do printf '%s\n' "${line//"$NODE4_PASS"/***}"; done
}

with_timeout() {
  if have timeout; then timeout "$LIMIT" "$@"; else "$@"; fi
}

# Path of the repo as Docker on this machine wants it (Git Bash on Windows needs C:/...).
host_root() { if pwd -W >/dev/null 2>&1; then (cd "$ROOT" && pwd -W); else echo "$ROOT"; fi; }

docker_ok() {
  [ "$DOCKER" != never ] && have docker && docker info >/dev/null 2>&1
}

# use_local CMD: true when the local runtime should be used.
use_local() { [ "$DOCKER" != always ] && have "$1"; }

# Build output and installed dependencies are never copied out of an example folder. The
# patterns are anchored to the folder's top level, because rust/src/bin holds sources.
TAR_EXCLUDES="--exclude=__pycache__ --anchored --exclude=./node_modules --exclude=./target --exclude=./bin --exclude=./obj \
--exclude=./build --exclude=./.gradle --exclude=./vendor"

# in_docker IMAGE DIR SCRIPT: copy DIR out of the read-only repo into the container and
# run SCRIPT there, so builds never write into your checkout. Credentials pass by name only.
in_docker() {
  local image=$1 dir=$2 script=$3
  MSYS_NO_PATHCONV=1 docker run --rm -e NODE4_USER -e NODE4_PASS -e NODE4_GATEWAY -e NODE4_PROXY \
    -v "$(host_root):/repo:ro" "$image" sh -c "mkdir -p /w && cd /repo/$dir && \
      tar cf - $TAR_EXCLUDES . | tar xf - -C /w && cd /w && $script"
}

# stage DIR: a scratch copy of DIR for local builds (cargo, dotnet, gradle write next to the sources).
stage() {
  mkdir -p "$WORK/stage/$1"
  # shellcheck disable=SC2086
  (cd "$ROOT/$1" && tar cf - $TAR_EXCLUDES .) | tar xf - -C "$WORK/stage/$1"
  echo "$WORK/stage/$1"
}

python_with() {  # python_with MODULE: a local Python that can import MODULE
  local py
  for py in "${PYTHON:-}" "$ROOT/.venv/Scripts/python.exe" "$ROOT/.venv/bin/python" python3 python; do
    [ -n "$py" ] && have "$py" && "$py" -c "import $1" >/dev/null 2>&1 && { echo "$py"; return 0; }
  done
  return 1
}

# ----------------------------------------------------------------------------- checks
# Each check prints its output, then asserts on it. Request counts are in the comments.

check_curl() {  # 4-6 requests
  have curl || skip "curl not installed" || return
  local out="$WORK/curl.out"
  (cd "$ROOT/curl" && bash examples.sh) > "$out" 2>&1
  cat "$out"
  ! grep -q "407" "$out" || fail "407 from the proxy" || return
  if [ "$SOCKS" = 1 ]; then expect_ips "$out" 4; else expect_ips "$out" 3; fi
}

check_python() {  # 4-6 requests
  local out="$WORK/py.out" py
  local script='"$PY" basic_requests.py && "$PY" sticky_session.py'
  [ "$SOCKS" = 1 ] && script="$script"' && "$PY" socks5.py'
  [ -n "${NODE4_PROXY:-}" ] && script="$script"' && "$PY" check_static_proxies.py'
  if [ "$DOCKER" != always ] && py=$(python_with requests); then
    (cd "$ROOT/python" && PY="$py" bash -c "$script") > "$out" 2>&1
  elif docker_ok; then
    in_docker python:3.12-slim python "pip install -q --root-user-action=ignore -r requirements.txt && PY=python && $script" > "$out" 2>&1
  else
    skip "no Python with requests installed,, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  grep -Eq "exit IP: $IP_RE" "$out" || fail "basic_requests.py printed no exit IP" || return
  grep -q "distinct exits: 1 " "$out" || fail "sticky_session.py did not hold one exit" || return
  if [ -n "${NODE4_PROXY:-}" ]; then
    grep -Eq '^([0-9]+)/\1 healthy' "$out" || fail "check_static_proxies.py reported an unhealthy proxy" || return
  fi
  expect_ips "$out" 4
}

check_node() {  # 1-2 requests
  local out="$WORK/node.out"
  local script="node fetch-undici.mjs"
  [ "$SOCKS" = 1 ] && script="$script && node socks5.mjs"
  if use_local node; then
    if [ ! -d "$ROOT/node/node_modules/undici" ]; then
      (cd "$ROOT/node" && npm install --no-audit --no-fund --omit=optional >/dev/null 2>&1) || { fail "npm install failed"; return; }
    fi
    (cd "$ROOT/node" && bash -c "$script") > "$out" 2>&1
  elif docker_ok; then
    in_docker node:22-slim node "npm install --no-audit --no-fund --omit=optional --loglevel=error >/dev/null && $script" > "$out" 2>&1
  else
    skip "no Node.js, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  grep -Eq "exit IP: $IP_RE" "$out" || fail "fetch-undici.mjs printed no exit IP" || return
  [ "$SOCKS" = 0 ] || expect_ips "$out" 2
}

check_go() {  # 4 requests
  local out="$WORK/go.out"
  if use_local go; then
    (cd "$ROOT/go" && go run . -workers 2 -n 4) > "$out" 2>&1
  elif docker_ok; then
    in_docker golang:1.22 go "go run . -workers 2 -n 4" > "$out" 2>&1
  else
    skip "no Go, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  # main.go prints a summary, not the IPs: "4 requests, 0 failed, N distinct exits, ..."
  grep -Eq "^4 requests, 0 failed, [1-9][0-9]* distinct exits" "$out" || fail "expected 4 requests, 0 failed"
}

check_scrapy() {  # about 4 requests (the spider is capped at 3 items)
  local out="$WORK/scrapy.out" json="$WORK/exits.json" py
  local args="crawl exit_ip -s CONCURRENT_REQUESTS=1 -s CLOSESPIDER_ITEMCOUNT=3 -s LOG_LEVEL=WARNING"
  if [ "$DOCKER" != always ] && py=$(python_with scrapy); then
    (cd "$ROOT/scrapy" && "$py" -m scrapy $args -O "$json" && cat "$json") > "$out" 2>&1
  elif docker_ok; then
    in_docker python:3.12-slim scrapy "pip install -q --root-user-action=ignore scrapy && scrapy $args -O /tmp/exits.json && cat /tmp/exits.json" > "$out" 2>&1
  else
    skip "no Python with Scrapy installed,, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  grep -Eq "\"exit_ip\": \"$IP_RE\"" "$out" || fail "no exit_ip items in the feed"
}

check_checker() {  # 6 requests, +1 per static proxy
  local out="$WORK/checker.out" py rc
  py=$(python_with json) || { skip "no Python"; return; }
  (cd "$ROOT/checker" && "$py" -m unittest -q test_node4check.py) > "$out" 2>&1 || { cat "$out"; fail "unit tests failed"; return; }
  echo "unit tests: OK" > "$out"
  (cd "$ROOT/checker" && "$py" node4check.py --gateway --rotation 3 --sticky 2 \
     ${NODE4_PROXY:+"$NODE4_PROXY"}) >> "$out" 2>&1
  rc=$?
  cat "$out"
  [ $rc -eq 0 ] || fail "node4check exited $rc" || return
  expect_ips "$out" 6
}

check_java() {  # 1 request
  local out="$WORK/java.out"
  [ -f "$ROOT/java/BasicHttpClient.java" ] || { skip "java/BasicHttpClient.java not found"; return; }
  if use_local java && java -version 2>&1 | grep -Eq 'version "(2[1-9]|[3-9][0-9])'; then
    (cd "$ROOT/java" && java BasicHttpClient.java) > "$out" 2>&1
  elif docker_ok; then
    in_docker eclipse-temurin:21 java "java BasicHttpClient.java" > "$out" 2>&1
  else
    skip "no JDK 21+, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  expect_ips "$out" 1
}

check_kotlin() {  # 3 requests on one sticky session
  local out="$WORK/kotlin.out" dir
  [ -f "$ROOT/kotlin/build.gradle.kts" ] || { skip "kotlin/build.gradle.kts not found"; return; }
  if use_local gradle; then
    dir=$(stage kotlin)
    (cd "$dir" && gradle -q run --args="sticky 1") > "$out" 2>&1
  elif docker_ok; then
    in_docker gradle:8.10-jdk21 kotlin 'gradle -q --no-daemon run --args="sticky 1"' > "$out" 2>&1
  else
    skip "no Gradle, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  grep -q "(1 distinct" "$out" || fail "the sticky session did not hold one exit" || return
  expect_ips "$out" 3
}

check_csharp() {  # 1 request
  local out="$WORK/csharp.out" dir
  [ -f "$ROOT/csharp/Program.cs" ] || { skip "csharp/Program.cs not found"; return; }
  if use_local dotnet; then
    dir=$(stage csharp)
    (cd "$dir" && dotnet run -- basic) > "$out" 2>&1
  elif docker_ok; then
    in_docker mcr.microsoft.com/dotnet/sdk:8.0 csharp "dotnet run -- basic" > "$out" 2>&1
  else
    skip "no .NET SDK, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  expect_ips "$out" 1
}

check_php() {  # 1 request
  local out="$WORK/php.out"
  [ -f "$ROOT/php/basic.php" ] || { skip "php/basic.php not found"; return; }
  if use_local php && php -r 'exit(extension_loaded("curl") ? 0 : 1);'; then
    (cd "$ROOT/php" && php basic.php) > "$out" 2>&1
  elif docker_ok; then
    in_docker php:8.3-cli php "php basic.php" > "$out" 2>&1
  else
    skip "no PHP with the curl extension,, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  expect_ips "$out" 1
}

check_powershell() {  # 1 request
  local out="$WORK/ps.out" ps=""
  [ -f "$ROOT/powershell/basic.ps1" ] || { skip "powershell/basic.ps1 not found"; return; }
  if [ "$DOCKER" != always ]; then
    if have pwsh; then ps=pwsh; elif have powershell.exe; then ps=powershell.exe; fi
  fi
  if [ -n "$ps" ]; then
    local script="$ROOT/powershell/basic.ps1"
    pwd -W >/dev/null 2>&1 && script="$(cd "$ROOT/powershell" && pwd -W)/basic.ps1"
    "$ps" -NoProfile -ExecutionPolicy Bypass -File "$script" > "$out" 2>&1
  elif docker_ok; then
    in_docker mcr.microsoft.com/powershell:lts-debian-12 powershell "pwsh -NoProfile -File ./basic.ps1" > "$out" 2>&1
  else
    skip "no PowerShell, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  expect_ips "$out" 1
}

check_ruby() {  # 1 request
  local out="$WORK/ruby.out"
  [ -f "$ROOT/ruby/basic.rb" ] || { skip "ruby/basic.rb not found"; return; }
  if use_local ruby; then
    (cd "$ROOT/ruby" && ruby basic.rb) > "$out" 2>&1
  elif docker_ok; then
    in_docker ruby:3.3-slim ruby "ruby basic.rb" > "$out" 2>&1
  else
    skip "no Ruby, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  expect_ips "$out" 1
}

check_rust() {  # 1 request
  local out="$WORK/rust.out" dir
  [ -f "$ROOT/rust/Cargo.toml" ] || { skip "rust/Cargo.toml not found"; return; }
  if use_local cargo; then
    dir=$(stage rust)
    (cd "$dir" && cargo run -q --bin basic) > "$out" 2>&1
  elif docker_ok; then
    in_docker rust:1-slim rust "cargo run -q --bin basic" > "$out" 2>&1
  else
    skip "no Rust toolchain, and Docker is unavailable or disabled"; return
  fi
  cat "$out"
  expect_ips "$out" 1
}

check_browsers() {  # 7 page loads (3 contexts x 2, plus a credential check)
  local out="$WORK/browsers.out" py
  [ -f "$ROOT/browsers/playwright_sync.py" ] || { skip "browsers/playwright_sync.py not found"; return; }
  py=$(python_with playwright) || { skip "Playwright for Python not installed (no Docker fallback: browser images are large)"; return; }
  (cd "$ROOT/browsers" && "$py" playwright_sync.py) > "$out" 2>&1
  if grep -q "Executable doesn't exist\|playwright install" "$out"; then
    skip "Playwright browsers not installed (run: playwright install chromium)"; return
  fi
  cat "$out"
  expect_ips "$out" 2
}

# ----------------------------------------------------------------------------- runner

selected() {
  local name=$1
  if [ -n "$ONLY" ]; then case ",$ONLY," in *",$name,"*) ;; *) return 1 ;; esac; fi
  case ",$SKIP," in *",$name,"*) return 1 ;; esac
  return 0
}

pass=0 failn=0 skipn=0
echo "Node4 smoke test: gateway $NODE4_GATEWAY${NODE4_PROXY:+, static $NODE4_PROXY}"
for name in "${ALL_CHECKS[@]}"; do
  selected "$name" || continue
  rm -f "$WORK/skip-reason"
  start=$SECONDS
  printf '%-11s ' "$name"
  # Run each check in its own shell so a slow or broken one cannot take the runner down.
  export -f have skip fail expect_ips with_timeout host_root docker_ok use_local in_docker stage python_with "check_$name"
  export ROOT WORK IP_RE SKIP_CODE SOCKS DOCKER LIMIT TAR_EXCLUDES
  with_timeout bash -c "check_$name" > "$WORK/$name.log" 2>&1
  rc=$?
  secs=$((SECONDS - start))
  if [ $rc -eq 0 ]; then
    status=PASS; pass=$((pass + 1)); note=""
  elif [ $rc -eq $SKIP_CODE ]; then
    status=SKIP; skipn=$((skipn + 1)); note=$(cat "$WORK/skip-reason" 2>/dev/null)
  else
    status=FAIL; failn=$((failn + 1))
    [ $rc -eq 124 ] && note="timed out after ${LIMIT}s" || note=$(grep -m1 '^ASSERT:' "$WORK/$name.log" | sed 's/^ASSERT: //')
  fi
  printf '%-4s  %4ss  %s\n' "$status" "$secs" "$note"
  if [ "$VERBOSE" = 1 ] || [ "$status" = FAIL ]; then
    tail -n "$([ "$VERBOSE" = 1 ] && echo 200 || echo 15)" "$WORK/$name.log" | redact | sed 's/^/            | /'
  fi
done

echo
echo "PASS $pass  FAIL $failn  SKIP $skipn"
[ $failn -eq 0 ]
