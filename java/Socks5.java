// SOCKS5 with java.net.Proxy and HttpURLConnection. SOCKS5 is on paid plans.
//
//   export NODE4_USER=... NODE4_PASS=...
//   java Socks5.java
//
// Do NOT use java.net.http.HttpClient for SOCKS: it ignores SOCKS proxies returned by a
// ProxySelector and connects DIRECTLY, so requests leave from your own IP with no error.
// HttpURLConnection, plain Sockets, and libraries built on them (OkHttp) do honour
// java.net.Proxy(Proxy.Type.SOCKS, ...).
//
// SOCKS5 username/password comes from the default java.net.Authenticator, which the JDK
// asks with protocol "SOCKS5". The target hostname is sent to the proxy unresolved, so the
// proxy does the DNS lookup (the equivalent of socks5h://).
import java.io.InputStream;
import java.net.Authenticator;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.Proxy;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;

public class Socks5 {
    public static void main(String[] args) throws Exception {
        String user = env("NODE4_USER", ""), pass = env("NODE4_PASS", "");
        if (user.isEmpty() || pass.isEmpty()) {
            System.err.println("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
            System.exit(1);
        }
        // NODE4_PROXY (static IP:4443) wins if set, otherwise the gateway. Either way use the
        // SOCKS5 port that pairs with the HTTP one (8083 -> 1083, 4443 -> 1443, ...).
        String endpoint = socksEndpoint(env("NODE4_PROXY", env("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083")));
        int colon = endpoint.lastIndexOf(':');
        String host = endpoint.substring(0, colon);
        int port = Integer.parseInt(endpoint.substring(colon + 1));

        // The default Authenticator is JVM-wide. Answer only SOCKS requests for this proxy, so
        // these credentials are never offered to a web server's 401.
        Authenticator.setDefault(new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                if (!"SOCKS5".equals(getRequestingProtocol())) return null;
                return new PasswordAuthentication(user, pass.toCharArray());
            }
        });

        // A hostname works here (SOCKS never builds a java.net.URI from the proxy host), so the
        // underscore in the gateway name is fine.
        Proxy proxy = new Proxy(Proxy.Type.SOCKS, new InetSocketAddress(host, port));
        HttpURLConnection conn = (HttpURLConnection) URI.create("https://api.ipify.org").toURL().openConnection(proxy);
        conn.setConnectTimeout(15_000);
        conn.setReadTimeout(30_000);
        try (InputStream in = conn.getInputStream()) {
            String ip = new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
            System.out.println("exit IP over SOCKS5 (" + endpoint + "): " + ip);
        } catch (java.net.SocketException e) {
            // A rejected SOCKS login or a plan without SOCKS5 shows up here, not as a 407.
            System.err.println("SOCKS5 failed: " + e.getMessage()
                    + "\nCheck NODE4_USER/NODE4_PASS and that your plan includes SOCKS5 (the free tier is HTTP(S) only).");
            System.exit(1);
        }
    }

    static String socksEndpoint(String httpEndpoint) {
        int colon = httpEndpoint.lastIndexOf(':');
        String port = httpEndpoint.substring(colon + 1);
        Map<String, String> pairs = Map.of("8082", "1082", "8083", "1083", "8084", "1084", "4443", "1443");
        return httpEndpoint.substring(0, colon) + ":" + pairs.getOrDefault(port, port);
    }

    static String env(String name, String fallback) {
        String v = System.getenv(name);
        return v == null || v.isEmpty() ? fallback : v;
    }
}
