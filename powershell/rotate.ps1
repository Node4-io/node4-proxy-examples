# Rotation is per CONNECTION: how to get a new exit on each request.
#
# An HTTPS request travels inside a CONNECT tunnel, and every request sent down that
# tunnel leaves from the same exit. -DisableKeepAlive closes the tunnel after each
# request, so the next request opens a new one and can get a different exit.
#
# Without it, Windows PowerShell 5.1 keeps the tunnel open between calls and reuses it,
# so several calls in a row usually report one IP. PowerShell 7 builds a new client per
# call unless you pass -WebSession, so the default loop below may already rotate there.
. "$PSScriptRoot/_env.ps1"; if (-not $Node4Ready) { exit 1 }

$n = 5
$cred = Get-Node4Credential
$proxy = "http://$Node4Gateway"

$default = @{}
foreach ($i in 1..$n) {
    $default[(Invoke-RestMethod $IpUrl -Proxy $proxy -ProxyCredential $cred -TimeoutSec 30)] = $true
}
"default (keep-alive), $n calls -> $($default.Count) distinct exit(s)"

$fresh = @{}
foreach ($i in 1..$n) {
    $fresh[(Invoke-RestMethod $IpUrl -Proxy $proxy -ProxyCredential $cred -DisableKeepAlive -TimeoutSec 30)] = $true
}
"-DisableKeepAlive, $n calls    -> $($fresh.Count) distinct exit(s)"
