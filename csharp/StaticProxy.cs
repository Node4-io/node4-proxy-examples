// One request through a static proxy. Traffic leaves from the exact IP you connect to.
namespace Node4Examples;

static class StaticProxy
{
    public static async Task<int> Run(string[] args)
    {
        var endpoint = args.Length > 0 ? args[0] : Env.Static;
        if (endpoint.Length == 0)
        {
            Console.Error.WriteLine("Set NODE4_PROXY to one of your static proxies (IP:4443), or pass it as an argument.");
            return 1;
        }
        using var client = Env.Client(Env.Proxy(endpoint));
        var ip = (await client.GetStringAsync(Env.IpUrl)).Trim();
        var ok = ip == endpoint.Split(':')[0];
        Console.WriteLine($"{endpoint} -> exit {ip} ({(ok ? "OK" : "MISMATCH")})");
        return ok ? 0 : 1;
    }
}
