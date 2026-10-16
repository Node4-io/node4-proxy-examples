// Why a reused HttpClient keeps one IP, and how to get a new exit per request.
//
// Rotation is per CONNECTION. An HTTPS request travels inside a CONNECT tunnel, and every
// request sent down that tunnel leaves from the same exit. HttpClient keeps the tunnel
// open (keep-alive), so the first loop usually reports one IP. The other two loops open
// a new connection per request, so each request can get a different exit.
namespace Node4Examples;

static class Rotate
{
    const int N = 5;

    public static async Task<int> Run(string[] args)
    {
        var proxy = Env.Proxy(Env.Gateway);

        // 1. One client, requests in sequence: the pooled tunnel is reused.
        using (var client = Env.Client(proxy))
        {
            var reused = new HashSet<string>();
            for (var i = 0; i < N; i++) reused.Add(await client.GetStringAsync(Env.IpUrl));
            Console.WriteLine($"one HttpClient, {N} requests       -> {reused.Count} distinct exit(s)");
        }

        // 2. Still one long-lived client, but the pool keeps no connection:
        //    PooledConnectionLifetime = Zero closes each connection after its request.
        using (var client = new HttpClient(new SocketsHttpHandler
        {
            Proxy = proxy,
            PooledConnectionLifetime = TimeSpan.Zero,
        }) { Timeout = TimeSpan.FromSeconds(30) })
        {
            var fresh = new HashSet<string>();
            for (var i = 0; i < N; i++) fresh.Add(await client.GetStringAsync(Env.IpUrl));
            Console.WriteLine($"PooledConnectionLifetime = Zero   -> {fresh.Count} distinct exit(s)");
        }

        // 3. Per request: "Connection: close" makes the handler drop that connection.
        using (var client = Env.Client(proxy))
        {
            var fresh = new HashSet<string>();
            for (var i = 0; i < N; i++)
            {
                using var req = new HttpRequestMessage(HttpMethod.Get, Env.IpUrl);
                req.Headers.ConnectionClose = true;
                using var resp = await client.SendAsync(req);
                fresh.Add(await resp.Content.ReadAsStringAsync());
            }
            Console.WriteLine($"Connection: close on each request -> {fresh.Count} distinct exit(s)");
        }
        return 0;
    }
}
