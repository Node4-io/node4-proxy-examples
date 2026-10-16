<?php
// Guzzle through a Node4 proxy (composer install first).
//
// Guzzle takes the proxy as a URL, so percent-encode the username and password:
// a password containing @ : or / otherwise breaks the URL.
require __DIR__ . '/vendor/autoload.php';
require __DIR__ . '/_env.php';

use GuzzleHttp\Client;
use GuzzleHttp\Exception\RequestException;

function proxy_url(string $endpoint, string $user, string $pass, string $scheme = 'http'): string
{
    return sprintf('%s://%s:%s@%s', $scheme, rawurlencode($user), rawurlencode($pass), $endpoint);
}

$client = new Client(['timeout' => 30, 'connect_timeout' => 15]);

try {
    // Rotating gateway over HTTP.
    $r = $client->get(IP_URL, ['proxy' => proxy_url($GATEWAY, $USER, $PASS)]);
    echo "HTTP gateway        -> {$r->getBody()}\n";

    // Sticky session: a session ID in the username holds one exit.
    $sticky = proxy_url($GATEWAY, "$USER-session-" . bin2hex(random_bytes(4)), $PASS);
    $a = (string)$client->get(IP_URL, ['proxy' => $sticky])->getBody();
    $b = (string)$client->get(IP_URL, ['proxy' => $sticky])->getBody();
    echo "sticky session      -> $a, $b (", $a === $b ? 'same' : 'different', ")\n";

    // SOCKS5 (paid plans). socks5h:// lets the proxy resolve the hostname.
    $r = $client->get(IP_URL, ['proxy' => proxy_url(socks_endpoint($GATEWAY), $USER, $PASS, 'socks5h')]);
    echo "SOCKS5 gateway      -> {$r->getBody()}\n";
} catch (RequestException $e) {
    // A 407 on an https:// target arrives as a curl error from the CONNECT step.
    if (str_contains($e->getMessage(), '407')) {
        fwrite(STDERR, "407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product\n");
    } else {
        fwrite(STDERR, $e->getMessage() . "\n");
    }
    exit(1);
}
