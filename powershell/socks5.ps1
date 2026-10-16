# SOCKS5 with a username and password. Needs PowerShell 7.2 or later; SOCKS5 is on paid plans.
#
# PowerShell 7 hands -Proxy to .NET, which speaks socks5:// and sends -ProxyCredential
# as SOCKS5 username/password auth. The target hostname goes to the proxy, so its DNS
# lookup happens on the proxy side. Windows PowerShell 5.1 has no SOCKS support.
#
#   pwsh ./socks5.ps1                       # the gateway's SOCKS5 port (8083 -> 1083)
#   pwsh ./socks5.ps1 203.0.113.10:4443     # a static proxy's SOCKS5 port (1443)
param([string]$Endpoint)
. "$PSScriptRoot/_env.ps1"; if (-not $Node4Ready) { exit 1 }

if ($PSVersionTable.PSVersion -lt [version]'7.2') {
    [Console]::Error.WriteLine('SOCKS5 needs PowerShell 7.2 or later (pwsh). Use the HTTP examples on Windows PowerShell 5.1.')
    exit 1
}

if (-not $Endpoint) { $Endpoint = $Node4Gateway }
$socks = Get-Node4SocksEndpoint $Endpoint
try {
    $ip = Invoke-RestMethod $IpUrl -Proxy "socks5://$socks" -ProxyCredential (Get-Node4Credential) -TimeoutSec 30
} catch {
    # A SOCKS5 server has no 407. A wrong password, or a plan without SOCKS5, is refused at
    # the connect step instead, which .NET reports as a proxy tunnel error.
    [Console]::Error.WriteLine("SOCKS5 request failed: $($_.Exception.Message)")
    [Console]::Error.WriteLine('If the target is reachable, check NODE4_USER/NODE4_PASS and that your plan includes SOCKS5.')
    exit 1
}
"exit IP over SOCKS5 via ${socks}: $ip"
