<?php
// Hold one exit IP across several connections with a session ID in the username.
//
// On the rotating gateways a session holds its exit for up to 30 minutes from first use.
// Use a new ID to get a new exit. Residential sessions are best effort with the same ceiling.
require __DIR__ . '/_env.php';

$session = bin2hex(random_bytes(4));
$user = "$USER-session-$session";

$seen = [];
for ($i = 0; $i < 3; $i++) {
    // A new handle each time means a new connection, yet the exit stays the same.
    $ip = fetch(proxied_handle(IP_URL, $GATEWAY, $user));
    $seen[$ip] = true;
    echo "session $session -> $ip\n";
}
echo 'distinct exits: ', count($seen), " (expect 1)\n";
