# Hold one exit IP across several connections with a session ID in the username.
#
# On the rotating gateways a session holds its exit for up to 30 minutes from first use.
# Use a new ID to get a new exit. Residential sessions are best effort with the same ceiling.
. "$PSScriptRoot/_env.ps1"; if (-not $Node4Ready) { exit 1 }

$session = -join ((1..8) | ForEach-Object { '0123456789abcdef'[(Get-Random -Maximum 16)] })
$cred = Get-Node4Credential "$Node4User-session-$session"

$seen = @{}
foreach ($i in 1..3) {
    # -DisableKeepAlive closes the connection after each request, so every request is a
    # new connection, yet the exit stays the same.
    $ip = Invoke-RestMethod $IpUrl -Proxy "http://$Node4Gateway" -ProxyCredential $cred -DisableKeepAlive -TimeoutSec 30
    $seen[$ip] = $true
    "session $session -> $ip"
}
"distinct exits: $($seen.Count) (expect 1)"
