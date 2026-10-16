// SOCKS5 with a username and password. SOCKS5 is on paid plans.
//
// .NET 6+ accepts socks5:// in WebProxy and sends the NetworkCredential as SOCKS5
// username/password auth. It passes the target hostname to the proxy, so the target's
// DNS lookup happens on the proxy side (what other tools call socks5h://).
namespace Node4Examples;

static class Socks5
{
    public static async Task<int> Run(string[] args)
    {
        var endpoint = Env.SocksEndpoint(args.Length > 0 ? args[0] : Env.Gateway);
        using var client = Env.Client(Env.Proxy(endpoint, scheme: "socks5"));
        try
        {
            var ip = await client.GetStringAsync(Env.IpUrl);
            Console.WriteLine($"exit IP over SOCKS5 via {endpoint}: {ip}");
            return 0;
        }
        catch (HttpRequestException e)
        {
            // A SOCKS5 server has no 407. A wrong password, or a plan without SOCKS5, is
            // refused at the connect step, which .NET reports as a proxy tunnel error.
            Console.Error.WriteLine($"SOCKS5 request failed: {e.Message}");
            Console.Error.WriteLine("If the target is reachable, check NODE4_USER/NODE4_PASS and that your plan includes SOCKS5.");
            return 1;
        }
    }
}
