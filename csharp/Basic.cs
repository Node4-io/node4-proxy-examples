// One request through the rotating gateway.
namespace Node4Examples;

static class Basic
{
    public static async Task<int> Run(string[] args)
    {
        using var client = Env.Client(Env.Proxy(Env.Gateway));
        var ip = await client.GetStringAsync(Env.IpUrl);
        Console.WriteLine($"exit IP via {Env.Gateway}: {ip}");
        return 0;
    }
}
