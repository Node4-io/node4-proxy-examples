// OkHttp through a Node4 gateway: one request, rotation, a sticky session, and SOCKS5.
//
//   export NODE4_USER=... NODE4_PASS=...
//   mvn -q compile exec:java                         # HTTP proxy
//   mvn -q compile exec:java -Dexec.args=socks       # SOCKS5 (paid plans)
//
// OkHttp needs none of the JDK HttpClient workarounds:
// - It resolves the proxy host itself, so the underscore in gw-rotating_datacenter is fine.
// - proxyAuthenticator is asked before the CONNECT is sent (preemptive), so the JDK's
//   "no Basic auth on tunnels" default does not apply.
//
// Rotation is per connection, and OkHttp pools connections: a shared client keeps reusing the
// same tunnel, so it keeps the same exit. A client with an empty connection pool opens a new
// tunnel per request.
import java.io.IOException;
import java.net.Authenticator;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.Proxy;
import java.security.SecureRandom;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import okhttp3.ConnectionPool;
import okhttp3.Credentials;
import okhttp3.OkHttpClient;
import okhttp3.Protocol;
import okhttp3.Request;
import okhttp3.Response;

public class OkHttpExample {
    static final Request IPIFY = new Request.Builder().url("https://api.ipify.org").build();

    public static void main(String[] args) throws Exception {
        String user = env("NODE4_USER", ""), pass = env("NODE4_PASS", "");
        if (user.isEmpty() || pass.isEmpty()) {
            System.err.println("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
            System.exit(1);
        }
        String gateway = env("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083");

        if (args.length > 0 && args[0].equals("socks")) {
            socks(gateway, user, pass);
            return;
        }

        OkHttpClient shared = httpClient(gateway, user, pass);
        System.out.println("one request        -> " + exitIp(shared));

        Set<String> reused = new HashSet<>();
        for (int i = 0; i < 5; i++) reused.add(exitIp(shared));
        System.out.println("shared client, 5   -> " + reused.size() + " distinct exit(s)");

        // newBuilder() shares the dispatcher and settings. A pool that keeps no idle connections
        // closes each tunnel after use, so every request gets a new one. HTTP/1.1 matters once
        // requests run in parallel: over HTTP/2 OkHttp multiplexes concurrent requests to one
        // site onto a single connection, which is one tunnel and one exit.
        OkHttpClient noPool = shared.newBuilder()
                .connectionPool(new ConnectionPool(0, 1, TimeUnit.SECONDS))
                .protocols(List.of(Protocol.HTTP_1_1))
                .build();
        Set<String> fresh = new HashSet<>();
        for (int i = 0; i < 5; i++) fresh.add(exitIp(noPool));
        System.out.println("no pool, 5         -> " + fresh.size() + " distinct exit(s)");

        byte[] b = new byte[4];
        new SecureRandom().nextBytes(b);
        String sessionId = HexFormat.of().formatHex(b);
        OkHttpClient sticky = httpClient(gateway, user + "-session-" + sessionId, pass).newBuilder()
                .connectionPool(new ConnectionPool(0, 1, TimeUnit.SECONDS))   // new tunnel each time...
                .protocols(List.of(Protocol.HTTP_1_1))
                .build();
        Set<String> held = new HashSet<>();
        for (int i = 0; i < 3; i++) held.add(exitIp(sticky));
        System.out.println("session " + sessionId + ", 3 -> " + held.size() + " distinct exit(s) (expect 1)");  // ...same exit

        shared.dispatcher().executorService().shutdown();
        shared.connectionPool().evictAll();
    }

    static OkHttpClient httpClient(String endpoint, String user, String pass) {
        int colon = endpoint.lastIndexOf(':');
        Proxy proxy = new Proxy(Proxy.Type.HTTP, InetSocketAddress.createUnresolved(
                endpoint.substring(0, colon), Integer.parseInt(endpoint.substring(colon + 1))));
        String credential = Credentials.basic(user, pass);
        return new OkHttpClient.Builder()
                .proxy(proxy)
                .proxyAuthenticator((route, response) -> {
                    // Already sent credentials and still got a 407: wrong login or a product your
                    // plan does not include. Returning null stops OkHttp instead of retrying.
                    if (response.request().header("Proxy-Authorization") != null) return null;
                    return response.request().newBuilder()
                            .header("Proxy-Authorization", credential)
                            .build();
                })
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build();
    }

    static void socks(String gateway, String user, String pass) throws IOException {
        int colon = gateway.lastIndexOf(':');
        String port = gateway.substring(colon + 1);
        port = Map.of("8082", "1082", "8083", "1083", "8084", "1084", "4443", "1443").getOrDefault(port, port);
        // OkHttp hands SOCKS to java.net.Socket, which takes the login from the default
        // Authenticator. The unresolved proxy address makes the proxy resolve hostnames too.
        Authenticator.setDefault(new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                if (!"SOCKS5".equals(getRequestingProtocol())) return null;
                return new PasswordAuthentication(user, pass.toCharArray());
            }
        });
        OkHttpClient client = new OkHttpClient.Builder()
                .proxy(new Proxy(Proxy.Type.SOCKS, InetSocketAddress.createUnresolved(
                        gateway.substring(0, colon), Integer.parseInt(port))))
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build();
        System.out.println("exit IP over SOCKS5 -> " + exitIp(client));
        client.dispatcher().executorService().shutdown();
        client.connectionPool().evictAll();
    }

    static String exitIp(OkHttpClient client) throws IOException {
        try (Response r = client.newCall(IPIFY).execute()) {
            if (r.code() == 407) proxyAuthFailed();          // plain http:// targets
            return r.body().string().trim();
        } catch (IOException e) {
            // For https:// targets the 407 arrives on the CONNECT, and once proxyAuthenticator
            // returns null OkHttp throws this.
            if ("Failed to authenticate with proxy".equals(e.getMessage())) proxyAuthFailed();
            throw e;
        }
    }

    static void proxyAuthFailed() {
        System.err.println("407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product");
        System.exit(1);
    }

    static String env(String name, String fallback) {
        String v = System.getenv(name);
        return v == null || v.isEmpty() ? fallback : v;
    }
}
