# One request through a static proxy. Traffic leaves from the exact IP you connect to.
#   $env:NODE4_PROXY = '203.0.113.10:4443'; .\static.ps1
#   .\static.ps1 203.0.113.10:4443
param([string]$Endpoint)
. "$PSScriptRoot/_env.ps1"; if (-not $Node4Ready) { exit 1 }

if (-not $Endpoint) { $Endpoint = $Node4Static }
if (-not $Endpoint) {
    [Console]::Error.WriteLine('Set NODE4_PROXY to one of your static proxies (IP:4443), or pass it as an argument.')
    exit 1
}

try {
    $ip = (Invoke-RestMethod $IpUrl -Proxy "http://$Endpoint" -ProxyCredential (Get-Node4Credential) -TimeoutSec 30).Trim()
} catch {
    if (Test-Node4ProxyAuthError $_) { Write-Node4ProxyAuthHint; exit 1 }
    throw
}
$ok = $ip -eq $Endpoint.Split(':')[0]
"$Endpoint -> exit $ip ($(if ($ok) { 'OK' } else { 'MISMATCH' }))"
if (-not $ok) { exit 1 }
