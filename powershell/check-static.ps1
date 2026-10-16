# Check a list of static proxies, 10 at a time: is each one up, fast, and leaving from its own IP?
#
#   .\check-static.ps1 proxies.txt      # one IP:PORT per line (export from your Proxies page)
#   $env:NODE4_PROXY = '203.0.113.10:4443'; .\check-static.ps1
#
# Lines in IP:PORT:USER:PASS form (the API's txt export) are accepted; only IP:PORT is
# used, the credentials come from NODE4_USER / NODE4_PASS. Works on 5.1 and 7.
param([string]$Path)
. "$PSScriptRoot/_env.ps1"; if (-not $Node4Ready) { exit 1 }

if ($Path) {
    $endpoints = Get-Content $Path | Where-Object { $_.Trim() -and -not $_.StartsWith('#') } |
        ForEach-Object { ($_.Trim().Split(':')[0..1]) -join ':' }
} elseif ($Node4Static) {
    $endpoints = @($Node4Static)
} else {
    [Console]::Error.WriteLine('Pass a file of IP:PORT lines, or set NODE4_PROXY.')
    exit 1
}

$check = {
    param($Endpoint, $Cred, $Url)
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $ip = (Invoke-RestMethod $Url -Proxy "http://$Endpoint" -ProxyCredential $Cred -DisableKeepAlive -TimeoutSec 20).Trim()
        $status = if ($ip -eq $Endpoint.Split(':')[0]) { 'OK' } else { "MISMATCH exit=$ip" }
    } catch {
        $status = if ("$($_.Exception.Message)" -match '407') { 'FAIL 407 (check credentials)' } else { "FAIL $($_.Exception.GetType().Name)" }
    }
    [pscustomobject]@{ Proxy = $Endpoint; Status = $status; Seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2) }
}

# A runspace pool runs the checks in parallel on both Windows PowerShell 5.1 and PowerShell 7.
$pool = [RunspaceFactory]::CreateRunspacePool(1, 10)
$pool.Open()
$cred = Get-Node4Credential
$jobs = foreach ($ep in $endpoints) {
    $ps = [PowerShell]::Create().AddScript($check).AddArgument($ep).AddArgument($cred).AddArgument($IpUrl)
    $ps.RunspacePool = $pool
    [pscustomobject]@{ PS = $ps; Handle = $ps.BeginInvoke() }
}
$results = foreach ($j in $jobs) { $j.PS.EndInvoke($j.Handle); $j.PS.Dispose() }
$pool.Close()

$results | Format-Table -AutoSize
$bad = @($results | Where-Object Status -ne 'OK').Count
"$(@($results).Count - $bad)/$(@($results).Count) healthy"
if ($bad) { exit 1 }
