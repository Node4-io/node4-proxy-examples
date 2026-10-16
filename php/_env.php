<?php
// Shared settings for the examples: credentials and endpoints from the environment.

const IP_URL = 'https://api.ipify.org';

$USER = getenv('NODE4_USER') ?: '';
$PASS = getenv('NODE4_PASS') ?: '';
$GATEWAY = getenv('NODE4_GATEWAY') ?: 'gw-rotating_datacenter.node4.io:8083';
$STATIC = getenv('NODE4_PROXY') ?: ''; // one of your static proxies, e.g. 203.0.113.10:4443

if ($USER === '' || $PASS === '') {
    fwrite(STDERR, "Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).\n");
    exit(1);
}

/**
 * A curl handle that fetches $url through an HTTP proxy at $endpoint (host:port).
 * The username and password are set separately, so characters like @ and : in the
 * password need no escaping.
 */
function proxied_handle(string $url, string $endpoint, ?string $user = null, int $type = CURLPROXY_HTTP)
{
    global $USER, $PASS;
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_PROXY => $endpoint,
        CURLOPT_PROXYTYPE => $type,
        CURLOPT_PROXYUSERNAME => $user ?? $USER,
        CURLOPT_PROXYPASSWORD => $PASS,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 15,
        CURLOPT_TIMEOUT => 30,
    ]);
    return $ch;
}

/**
 * Run a handle and return the body. Exits on a 407: wrong username or password, or a
 * product your plan does not include. Retrying cannot fix that.
 */
function fetch($ch): string
{
    $body = curl_exec($ch);
    check_407($ch);
    if ($body === false) {
        throw new RuntimeException('curl error: ' . curl_error($ch));
    }
    $code = curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    if ($code !== 200) {
        throw new RuntimeException("HTTP $code");
    }
    return trim($body);
}

/** For an https:// target the 407 comes from the CONNECT step, so check both codes. */
function is_407($ch): bool
{
    return curl_getinfo($ch, CURLINFO_HTTP_CONNECTCODE) === 407
        || curl_getinfo($ch, CURLINFO_RESPONSE_CODE) === 407;
}

function check_407($ch): void
{
    if (is_407($ch)) {
        fwrite(STDERR, "407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product\n");
        exit(1);
    }
}

/** The SOCKS5 port that pairs with an HTTP endpoint (8083->1083, 4443->1443, ...). */
function socks_endpoint(string $endpoint): string
{
    $i = strrpos($endpoint, ':');
    $host = substr($endpoint, 0, $i);
    $port = substr($endpoint, $i + 1);
    $pairs = ['8082' => '1082', '8083' => '1083', '8084' => '1084', '4443' => '1443'];
    return $host . ':' . ($pairs[$port] ?? $port);
}
