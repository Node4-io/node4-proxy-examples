<?php
// One request through a static proxy. Traffic leaves from the exact IP you connect to.
//
//   NODE4_PROXY=203.0.113.10:4443 php static.php
require __DIR__ . '/_env.php';

$endpoint = $argv[1] ?? $STATIC;
if ($endpoint === '') {
    fwrite(STDERR, "Set NODE4_PROXY to one of your static proxies (IP:4443), or pass it as an argument.\n");
    exit(1);
}

$ip = fetch(proxied_handle(IP_URL, $endpoint));
$ok = $ip === explode(':', $endpoint)[0];
echo "$endpoint -> exit $ip (", $ok ? 'OK' : 'MISMATCH', ")\n";
exit($ok ? 0 : 1);
