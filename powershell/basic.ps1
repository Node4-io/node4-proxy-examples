# One request through the rotating gateway.
#   .\basic.ps1
. "$PSScriptRoot/_env.ps1"; if (-not $Node4Ready) { exit 1 }

try {
    $ip = Invoke-RestMethod $IpUrl -Proxy "http://$Node4Gateway" -ProxyCredential (Get-Node4Credential) -TimeoutSec 30
} catch {
    if (Test-Node4ProxyAuthError $_) { Write-Node4ProxyAuthHint; exit 1 }
    throw
}
"exit IP via ${Node4Gateway}: $ip"
