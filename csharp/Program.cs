// Node4 proxy examples for .NET.
//
//   export NODE4_USER=... NODE4_PASS=...
//   dotnet run -- basic
//
// Each command lives in its own file in this folder.
using Node4Examples;

var commands = new Dictionary<string, (string Help, Func<string[], Task<int>> Run)>
{
    ["basic"] = ("one request through the rotating gateway", Basic.Run),
    ["static"] = ("one request through a static proxy (NODE4_PROXY=IP:4443)", StaticProxy.Run),
    ["sticky"] = ("one exit IP across several connections with -session-ID", Sticky.Run),
    ["rotate"] = ("a reused HttpClient keeps one exit; a new connection gets a new one", Rotate.Run),
    ["socks5"] = ("SOCKS5 with username and password (paid plans)", Socks5.Run),
    ["concurrent"] = ("capped concurrency with retry and backoff that stops on 407", Concurrent.Run),
};

if (args.Length == 0 || !commands.TryGetValue(args[0], out var cmd))
{
    Console.Error.WriteLine("usage: dotnet run -- <command>\n");
    foreach (var (name, c) in commands)
        Console.Error.WriteLine($"  {name,-11} {c.Help}");
    return 2;
}

Env.RequireCredentials();
return await cmd.Run(args[1..]);
