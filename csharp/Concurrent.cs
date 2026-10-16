// Many requests at once, capped to your connection count, with retry and backoff.
//
//   dotnet run -- concurrent [requests] [concurrency]     (defaults 20 and 10)
//
// SemaphoreSlim caps how many requests are in flight, and MaxConnectionsPerServer caps
// the tunnels the handler opens. On Rotating Unmetered keep both at or below your plan's
// connection count. Each attempt sends "Connection: close", so a retry opens a new
// connection that can leave from a different exit.
//
// 403, 429, 5xx, timeouts: back off and retry.
// 407: wrong username or password, or a product your plan does not include. Retrying
// cannot fix that, and repeated bad logins look like abuse, so everything stops.
using System.Collections.Concurrent;
using System.Net;

namespace Node4Examples;

static class Concurrent
{
    static readonly HashSet<HttpStatusCode> RetryOn =
    [
        HttpStatusCode.Forbidden, HttpStatusCode.TooManyRequests, HttpStatusCode.InternalServerError,
        HttpStatusCode.BadGateway, HttpStatusCode.ServiceUnavailable, HttpStatusCode.GatewayTimeout,
    ];

    sealed class ProxyAuthException() : Exception(
        "407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product");

    public static async Task<int> Run(string[] args)
    {
        var total = args.Length > 0 ? int.Parse(args[0]) : 20;
        var concurrency = args.Length > 1 ? int.Parse(args[1]) : 10;

        using var client = Env.Client(Env.Proxy(Env.Gateway), maxConnections: concurrency);
        using var gate = new SemaphoreSlim(concurrency);
        using var stop = new CancellationTokenSource();

        var exits = new ConcurrentDictionary<string, int>();
        var failed = 0;
        var authFailed = 0;
        var started = DateTime.UtcNow;

        async Task One()
        {
            await gate.WaitAsync();
            try
            {
                var ip = await FetchWithRetry(client, Env.IpUrl, stop.Token);
                exits.AddOrUpdate(ip, 1, (_, n) => n + 1);
            }
            catch (ProxyAuthException e)
            {
                if (Interlocked.Exchange(ref authFailed, 1) == 0) Console.Error.WriteLine(e.Message);
                stop.Cancel(); // no point sending the rest with bad credentials
                Interlocked.Increment(ref failed);
            }
            catch (OperationCanceledException) when (stop.IsCancellationRequested)
            {
                Interlocked.Increment(ref failed);
            }
            catch (Exception e)
            {
                Console.Error.WriteLine($"failed: {e.Message}");
                Interlocked.Increment(ref failed);
            }
            finally
            {
                gate.Release();
            }
        }

        await Task.WhenAll(Enumerable.Range(0, total).Select(_ => One()));

        Console.WriteLine($"{total} requests, {failed} failed, {exits.Count} distinct exits, " +
                          $"concurrency {concurrency}, {(DateTime.UtcNow - started).TotalSeconds:F1}s");
        return failed == 0 ? 0 : 1;
    }

    static async Task<string> FetchWithRetry(HttpClient client, string url, CancellationToken ct, int attempts = 4)
    {
        for (var attempt = 1; ; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            string reason;
            try
            {
                using var req = new HttpRequestMessage(HttpMethod.Get, url);
                req.Headers.ConnectionClose = true; // the next attempt gets a new connection
                using var resp = await client.SendAsync(req, ct);
                if (resp.StatusCode == HttpStatusCode.ProxyAuthenticationRequired)
                    throw new ProxyAuthException(); // plain-http targets get the 407 as a response
                if (!RetryOn.Contains(resp.StatusCode))
                {
                    resp.EnsureSuccessStatusCode();
                    return (await resp.Content.ReadAsStringAsync(ct)).Trim();
                }
                reason = $"HTTP {(int)resp.StatusCode}";
            }
            catch (HttpRequestException e) when (e.StatusCode == HttpStatusCode.ProxyAuthenticationRequired
                                                 || e.Message.Contains("407"))
            {
                // https targets get the 407 as an exception from the CONNECT step.
                throw new ProxyAuthException();
            }
            catch (HttpRequestException e)
            {
                reason = e.HttpRequestError.ToString();
            }
            catch (TaskCanceledException) when (!ct.IsCancellationRequested)
            {
                reason = "timeout";
            }

            if (attempt == attempts) throw new Exception($"gave up after {attempts} attempts ({reason})");
            var delay = TimeSpan.FromSeconds(Math.Min(30, Math.Pow(2, attempt)) + Random.Shared.NextDouble());
            Console.Error.WriteLine($"attempt {attempt}: {reason}, retrying in {delay.TotalSeconds:F1}s");
            await Task.Delay(delay, ct);
        }
    }
}
