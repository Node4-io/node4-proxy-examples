// Hold one exit IP across several connections with a session ID in the username.
//
// On the rotating gateways a session holds its exit for up to 30 minutes from first use.
// Use a new ID to get a new exit. Residential sessions are best effort with the same ceiling.
using System.Security.Cryptography;

namespace Node4Examples;

static class Sticky
{
    public static async Task<int> Run(string[] args)
    {
        var sessionId = Convert.ToHexString(RandomNumberGenerator.GetBytes(4)).ToLowerInvariant();
        var proxy = Env.Proxy(Env.Gateway, user: $"{Env.User}-session-{sessionId}");

        var seen = new HashSet<string>();
        for (var i = 0; i < 3; i++)
        {
            // A new HttpClient each time means a new connection, yet the exit stays the same.
            using var client = Env.Client(proxy);
            var ip = await client.GetStringAsync(Env.IpUrl);
            seen.Add(ip);
            Console.WriteLine($"session {sessionId} -> {ip}");
        }
        Console.WriteLine($"distinct exits: {seen.Count} (expect 1)");
        return 0;
    }
}
