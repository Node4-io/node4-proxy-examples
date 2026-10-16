<?php
// Many requests at once with curl_multi, capped to your connection count, with retries.
//
//   php concurrent.php [requests] [concurrency]     (defaults 20 and 10)
//
// At most CONCURRENCY transfers are in flight; a new one starts when one finishes. On
// Rotating Unmetered keep it at or below your plan's connection count. Each transfer
// uses a fresh connection, so a retry can leave from a different exit.
//
// 403, 429, 5xx, timeouts: retried after a growing delay.
// 407: wrong username or password, or a product your plan does not include. Retrying
// cannot fix that, and repeated bad logins look like abuse, so the script stops.
require __DIR__ . '/_env.php';

$total = (int)($argv[1] ?? 20);
$concurrency = (int)($argv[2] ?? 10);
const ATTEMPTS = 4;
const RETRY_ON = [403, 429, 500, 502, 503, 504];

$queue = [];           // [job id, attempt, not-before time]
for ($i = 0; $i < $total; $i++) {
    $queue[] = [$i, 1, 0.0];
}
$mh = curl_multi_init();
$running = [];         // (int)$ch => [job id, attempt, handle]
$exits = [];
$failed = 0;
$start = microtime(true);

$add = function (int $job, int $attempt) use ($mh, &$running, $GATEWAY) {
    $ch = proxied_handle(IP_URL, $GATEWAY);
    curl_setopt_array($ch, [CURLOPT_FRESH_CONNECT => true, CURLOPT_FORBID_REUSE => true]);
    curl_multi_add_handle($mh, $ch);
    $running[(int)$ch] = [$job, $attempt, $ch];
};

while ($queue || $running) {
    // Top up to the cap with jobs whose backoff delay has passed.
    $now = microtime(true);
    foreach ($queue as $k => [$job, $attempt, $notBefore]) {
        if (count($running) >= $concurrency) {
            break;
        }
        if ($notBefore <= $now) {
            unset($queue[$k]);
            $add($job, $attempt);
        }
    }

    curl_multi_exec($mh, $active);
    curl_multi_select($mh, 0.2);

    while ($info = curl_multi_info_read($mh)) {
        $ch = $info['handle'];
        [$job, $attempt] = $running[(int)$ch];
        unset($running[(int)$ch]);
        curl_multi_remove_handle($mh, $ch);

        check_407($ch); // exits: no retry on bad credentials
        $code = curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        $body = curl_multi_getcontent($ch);

        if ($info['result'] === CURLE_OK && $code === 200) {
            $ip = trim($body);
            $exits[$ip] = ($exits[$ip] ?? 0) + 1;
            continue;
        }
        $reason = $info['result'] !== CURLE_OK ? curl_strerror($info['result']) : "HTTP $code";
        if ($attempt < ATTEMPTS && ($info['result'] !== CURLE_OK || in_array($code, RETRY_ON, true))) {
            $delay = min(30, 2 ** $attempt) + mt_rand() / mt_getrandmax();
            fwrite(STDERR, sprintf("job %d attempt %d: %s, retrying in %.1fs\n", $job, $attempt, $reason, $delay));
            $queue[] = [$job, $attempt + 1, microtime(true) + $delay];
        } else {
            fwrite(STDERR, "job $job failed: $reason\n");
            $failed++;
        }
    }
}
curl_multi_close($mh);

printf("%d requests, %d failed, %d distinct exits, concurrency %d, %.1fs\n",
    $total, $failed, count($exits), $concurrency, microtime(true) - $start);
exit($failed ? 1 : 0);
