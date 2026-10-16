<?php
// One request through the rotating gateway with ext-curl.
require __DIR__ . '/_env.php';

$ip = fetch(proxied_handle(IP_URL, $GATEWAY));
echo "exit IP via $GATEWAY: $ip\n";
