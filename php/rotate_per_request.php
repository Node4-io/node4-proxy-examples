<?php
// Why a reused curl handle keeps one IP, and how to get a new exit per request.
//
// Rotation is per CONNECTION. An HTTPS request travels inside a CONNECT tunnel, and every
// request sent down that tunnel leaves from the same exit. A curl handle keeps its
// connection open for the next request, so the first loop usually reports one IP.
// The second loop forces a new connection each time, so each request can get a new exit.
require __DIR__ . '/_env.php';

const N = 5;

$ch = proxied_handle(IP_URL, $GATEWAY);
$reused = [];
for ($i = 0; $i < N; $i++) {
    $reused[fetch($ch)] = true;
}
echo 'one handle, ', N, ' requests       -> ', count($reused), " distinct exit(s)\n";

$ch = proxied_handle(IP_URL, $GATEWAY);
curl_setopt_array($ch, [
    CURLOPT_FRESH_CONNECT => true, // do not take a cached connection
    CURLOPT_FORBID_REUSE => true,  // close this one when the request ends
]);
$fresh = [];
for ($i = 0; $i < N; $i++) {
    $fresh[fetch($ch)] = true;
}
echo 'FRESH_CONNECT + FORBID_REUSE -> ', count($fresh), " distinct exit(s)\n";
