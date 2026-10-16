# Manage a Node4 account from PowerShell with the REST API.
#
#   $env:NODE4_API_KEY = 'n4k_...'     # Settings -> API Keys on https://node4.io
#   .\api.ps1 status
#   .\api.ps1 export proxies.txt       # host:port:user:pass, one per line
#   .\api.ps1 usage
#   .\api.ps1 whitelist
#   .\api.ps1 whitelist-add 198.51.100.7 "build server"
#   .\api.ps1 whitelist-remove 123
#
# Reference: https://node4.io/help/proxy-management-api (OpenAPI spec at https://node4.io/openapi.json).
# Each call needs a matching permission on the key: read:proxies, read:usage, read:profile
# (listing the whitelist) or write:ip-whitelist. The API allows 60 requests per minute per key.
# The API is called directly, not through a proxy, and needs no NODE4_USER / NODE4_PASS.
param(
    [Parameter(Position = 0)][string]$Command,
    [Parameter(Position = 1)][string]$Arg1,
    [Parameter(Position = 2)][string]$Arg2
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 6) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

$base = 'https://node4.io/api/v1'
if (-not $env:NODE4_API_KEY) {
    [Console]::Error.WriteLine('Set NODE4_API_KEY (create one under Settings -> API Keys on node4.io).')
    exit 1
}
$headers = @{ Authorization = "Bearer $env:NODE4_API_KEY" }

function Invoke-Node4Api([string]$Method, [string]$PathAndQuery, $Body) {
    $params = @{ Method = $Method; Uri = "$base$PathAndQuery"; Headers = $headers; TimeoutSec = 30 }
    if ($Body) { $params.Body = ($Body | ConvertTo-Json); $params.ContentType = 'application/json' }
    try {
        Invoke-RestMethod @params
    } catch {
        $code = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        if ($code -eq 429) { [Console]::Error.WriteLine('Rate limited: 60 requests per minute per key. Wait and retry.') }
        else { [Console]::Error.WriteLine("$Method $PathAndQuery -> HTTP ${code}: $($_.ErrorDetails.Message)") }
        exit 1
    }
}

switch ($Command) {
    'status' {
        $d = (Invoke-Node4Api GET '/status').data
        $d.message
        if ($d.bandwidth.limited) { 'bandwidth: {0:N0} of {1:N0} MB used' -f $d.bandwidth.usedMb, $d.bandwidth.limitMb }
        "active proxies: $($d.proxies.active)"
    }
    'export' {
        if (-not $Arg1) { [Console]::Error.WriteLine('usage: .\api.ps1 export FILE'); exit 2 }
        $text = Invoke-Node4Api GET '/proxies/list?format=txt'
        $lines = @("$text".Trim() -split "`r?`n")
        [IO.File]::WriteAllText((Join-Path (Get-Location) $Arg1), ($lines -join "`n") + "`n")
        "wrote $($lines.Count) proxies to $Arg1"
    }
    'usage' {
        $bw = (Invoke-Node4Api GET '/usage?limit=1').data.bandwidth
        "this month: $($bw.totalFormatted) in $($bw.totalRequests) requests"
    }
    'whitelist' {
        $ips = @((Invoke-Node4Api GET '/ip-whitelist').data.ips)
        foreach ($ip in $ips) { "$($ip.id) $($ip.ipAddress) $($ip.label)" }
        "$($ips.Count) whitelisted"
    }
    'whitelist-add' {
        # Public IPv4 only: proxy endpoints are IPv4, so IPv6, private ranges and CIDR blocks are refused.
        if (-not $Arg1) { [Console]::Error.WriteLine('usage: .\api.ps1 whitelist-add IP [LABEL]'); exit 2 }
        $d = (Invoke-Node4Api POST '/ip-whitelist' @{ ipAddress = $Arg1; label = $Arg2 }).data
        "added $($d.id) $($d.ipAddress)"
    }
    'whitelist-remove' {
        if (-not $Arg1) { [Console]::Error.WriteLine('usage: .\api.ps1 whitelist-remove ID'); exit 2 }
        Invoke-Node4Api DELETE "/ip-whitelist/$([int]$Arg1)" | Out-Null
        "removed $Arg1"
    }
    default {
        [Console]::Error.WriteLine('usage: .\api.ps1 status | export FILE | usage | whitelist | whitelist-add IP [LABEL] | whitelist-remove ID')
        exit 2
    }
}
