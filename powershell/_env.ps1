# Shared settings for the examples: credentials and endpoints from the environment.
# Dot-source it, then stop if credentials are missing:
#   . "$PSScriptRoot/_env.ps1"; if (-not $Node4Ready) { exit 1 }
# (exit inside a dot-sourced file only leaves that file, so each script exits itself.)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 may still default to TLS 1.0 for HTTPS. Allow TLS 1.2 so the
# target site's certificate handshake (inside the proxy tunnel) succeeds.
if ($PSVersionTable.PSVersion.Major -lt 6) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

$Node4User = $env:NODE4_USER
$Node4Pass = $env:NODE4_PASS
$Node4Gateway = if ($env:NODE4_GATEWAY) { $env:NODE4_GATEWAY } else { 'gw-rotating_datacenter.node4.io:8083' }
$Node4Static = $env:NODE4_PROXY  # one of your static proxies, e.g. 203.0.113.10:4443
$IpUrl = 'https://api.ipify.org'

$Node4Ready = [bool]($Node4User -and $Node4Pass)
if (-not $Node4Ready) {
    [Console]::Error.WriteLine('Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).')
}

# A PSCredential for -ProxyCredential. Pass a different user for options such as
# USER-session-abc123 or USER-country-us.
function Get-Node4Credential([string]$User = $Node4User) {
    $secure = ConvertTo-SecureString $Node4Pass -AsPlainText -Force
    New-Object System.Management.Automation.PSCredential($User, $secure)
}

# True when an error is a 407 from the proxy: wrong username or password, or a product
# your plan does not include. Retrying cannot fix that.
function Test-Node4ProxyAuthError($ErrorRecord) {
    $e = $ErrorRecord.Exception
    if ($e.Response -and [int]$e.Response.StatusCode -eq 407) { return $true }
    return "$($e.Message)" -match '407|Proxy Authentication Required'
}

function Write-Node4ProxyAuthHint {
    [Console]::Error.WriteLine('407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product')
}

# The SOCKS5 port that pairs with an HTTP endpoint (8083->1083, 4443->1443, ...).
function Get-Node4SocksEndpoint([string]$Endpoint) {
    $i = $Endpoint.LastIndexOf(':')
    $hostPart = $Endpoint.Substring(0, $i)
    $port = $Endpoint.Substring($i + 1)
    $pairs = @{ '8082' = '1082'; '8083' = '1083'; '8084' = '1084'; '4443' = '1443' }
    if ($pairs.ContainsKey($port)) { $port = $pairs[$port] }
    "${hostPart}:$port"
}
