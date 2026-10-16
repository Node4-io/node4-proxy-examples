// Hold one exit IP across several connections with a session ID in the username.
//
//   export NODE4_USER=... NODE4_PASS=...
//   java StickySession.java
//
// Each loop builds a new HttpClient, so each request opens a new connection, yet the exit
// stays the same because the username carries -session-ID. On the rotating gateways a
// session holds its exit for up to 30 minutes from first use; residential sessions are best
// effort with the same ceiling. A new ID gives you a new exit.
import java.net.Authenticator;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Set;

public class StickySession {
    public static void main(String[] args) throws Exception {
        System.setProperty("jdk.http.auth.tunneling.disabledSchemes", "");
        System.setProperty("jdk.httpclient.auth.retrylimit", "0");

        String user = env("NODE4_USER", ""), pass = env("NODE4_PASS", "");
        if (user.isEmpty() || pass.isEmpty()) {
            System.err.println("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
            System.exit(1);
        }
        String gateway = env("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083");

        // Up to 32 letters and digits, chosen by you.
        byte[] b = new byte[4];
        new SecureRandom().nextBytes(b);
        String sessionId = HexFormat.of().formatHex(b);
        String stickyUser = user + "-session-" + sessionId;

        Set<String> seen = new HashSet<>();
        for (int i = 0; i < 3; i++) {
            HttpClient client = HttpClient.newBuilder()        // new client = new connection
                    .proxy(ProxySelector.of(proxyAddress(gateway)))
                    .authenticator(new Authenticator() {
                        @Override
                        protected PasswordAuthentication getPasswordAuthentication() {
                            if (getRequestorType() != RequestorType.PROXY) return null;
                            return new PasswordAuthentication(stickyUser, pass.toCharArray());
                        }
                    })
                    .connectTimeout(Duration.ofSeconds(15))
                    .build();
            HttpRequest req = HttpRequest.newBuilder(URI.create("https://api.ipify.org"))
                    .timeout(Duration.ofSeconds(30)).build();
            String ip = client.send(req, HttpResponse.BodyHandlers.ofString()).body().trim();
            seen.add(ip);
            System.out.println("session " + sessionId + " -> " + ip);
        }
        System.out.println("distinct exits: " + seen.size() + " (expect 1)");
    }

    // IP literal, because java.net.URI rejects the underscore in the gateway hostname.
    static InetSocketAddress proxyAddress(String endpoint) throws Exception {
        int colon = endpoint.lastIndexOf(':');
        return new InetSocketAddress(
                InetAddress.getByName(endpoint.substring(0, colon)).getHostAddress(),
                Integer.parseInt(endpoint.substring(colon + 1)));
    }

    static String env(String name, String fallback) {
        String v = System.getenv(name);
        return v == null || v.isEmpty() ? fallback : v;
    }
}
