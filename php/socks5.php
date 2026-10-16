<?php
// SOCKS5 with ext-curl. SOCKS5 is on paid plans.
//
// CURLPROXY_SOCKS5_HOSTNAME makes the proxy resolve the target hostname (socks5h://),
// so DNS lookups do not leave your machine. Plain CURLPROXY_SOCKS5 resolves locally.
//
//   php socks5.php                       # the gateway's SOCKS5 port (8083 -> 1083)
//   php socks5.php 203.0.113.10:4443     # a static proxy's SOCKS5 port (1443)
require __DIR__ . '/_env.php';

$endpoint = socks_endpoint($argv[1] ?? $GATEWAY);
$ch = proxied_handle(IP_URL, $endpoint, null, CURLPROXY_SOCKS5_HOSTNAME);
try {
    $ip = fetch($ch);
    echo "exit IP over SOCKS5 via $endpoint: $ip\n";
} catch (RuntimeException $e) {
    // A SOCKS5 server has no 407. A wrong password, or a plan without SOCKS5, is refused
    // at the connect step: "cannot complete SOCKS5 connection ... (2)".
    fwrite(STDERR, "SOCKS5 request failed: {$e->getMessage()}\n");
    fwrite(STDERR, "If the target is reachable, check NODE4_USER/NODE4_PASS and that your plan includes SOCKS5.\n");
    exit(1);
}
