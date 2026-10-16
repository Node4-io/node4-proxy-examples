// Shared settings for the examples: credentials and endpoints from the environment.
using System.Net;

namespace Node4Examples;

static class Env
{
    public static readonly string User = Get("NODE4_USER");
    public static readonly string Pass = Get("NODE4_PASS");
    public static readonly string Gateway = Get("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083");
    public static readonly string Static = Get("NODE4_PROXY"); // one of your static proxies, e.g. 203.0.113.10:4443

    public const string IpUrl = "https://api.ipify.org";

    public static void RequireCredentials()
    {
        if (User.Length == 0 || Pass.Length == 0)
        {
            Console.Error.WriteLine("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
            Environment.Exit(1);
        }
    }

    // A WebProxy for host:port. The credentials go in NetworkCredential, not in the URL,
    // so a password containing @ : or / needs no escaping.
    public static WebProxy Proxy(string endpoint, string? user = null, string scheme = "http") =>
        new(new Uri($"{scheme}://{endpoint}"))
        {
            Credentials = new NetworkCredential(user ?? User, Pass),
        };

    // An HttpClient that sends every request through the proxy. The handler pools
    // connections, and a pooled tunnel keeps its exit IP; see Rotate.cs.
    public static HttpClient Client(WebProxy proxy, int maxConnections = 10) =>
        new(new SocketsHttpHandler
        {
            Proxy = proxy,
            UseProxy = true,
            MaxConnectionsPerServer = maxConnections,
        })
        {
            Timeout = TimeSpan.FromSeconds(30),
        };

    // The SOCKS5 port that pairs with an HTTP endpoint (8083->1083, 4443->1443, ...).
    public static string SocksEndpoint(string endpoint)
    {
        var i = endpoint.LastIndexOf(':');
        var (host, port) = (endpoint[..i], endpoint[(i + 1)..]);
        var pairs = new Dictionary<string, string> { ["8082"] = "1082", ["8083"] = "1083", ["8084"] = "1084", ["4443"] = "1443" };
        return $"{host}:{pairs.GetValueOrDefault(port, port)}";
    }

    static string Get(string name, string fallback = "") =>
        Environment.GetEnvironmentVariable(name) is { Length: > 0 } v ? v : fallback;
}
