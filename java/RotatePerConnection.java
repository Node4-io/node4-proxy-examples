// Why a reused HttpClient keeps one IP, and how to get a new exit per request.
//
//   export NODE4_USER=... NODE4_PASS=...
//   java RotatePerConnection.java
//
// Rotation is per CONNECTION. An HTTPS request travels inside a CONNECT tunnel, and every
// request sent down that tunnel leaves from the same exit. HttpClient pools connections and
// keeps them alive, so the first loop usually reports one exit. The second loop builds a new
// HttpClient per request: each has its own pool, so each request opens a new tunnel and can
// get a different exit. (Closing the old clients matters; on JDK 21+ HttpClient is
// AutoCloseable. On JDK 11-20, drop the try-with-resources and let the client be collected.)
import java.net.Authenticator;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashSet;
import java.util.Set;

public class RotatePerConnection {
    static String user, pass;
    static InetSocketAddress gateway;
    static final URI TARGET = URI.create("https://api.ipify.org");

    public static void main(String[] args) throws Exception {
        System.setProperty("jdk.http.auth.tunneling.disabledSchemes", "");
        System.setProperty("jdk.httpclient.auth.retrylimit", "0");

        user = env("NODE4_USER", "");
        pass = env("NODE4_PASS", "");
        if (user.isEmpty() || pass.isEmpty()) {
            System.err.println("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
            System.exit(1);
        }
        gateway = proxyAddress(env("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083"));
        int n = 5;

        Set<String> reused = new HashSet<>();
        try (HttpClient client = newClient()) {
            for (int i = 0; i < n; i++) reused.add(exitIp(client));
        }
        System.out.println("one HttpClient, " + n + " requests -> " + reused.size() + " distinct exit(s)");

        Set<String> fresh = new HashSet<>();
        for (int i = 0; i < n; i++) {
            try (HttpClient client = newClient()) {          // new client = new connection = new exit
                fresh.add(exitIp(client));
            }
        }
        System.out.println("new HttpClient each time -> " + fresh.size() + " distinct exit(s)");
    }

    static HttpClient newClient() {
        return HttpClient.newBuilder()
                .proxy(ProxySelector.of(gateway))
                .authenticator(new Authenticator() {
                    @Override
                    protected PasswordAuthentication getPasswordAuthentication() {
                        if (getRequestorType() != RequestorType.PROXY) return null;
                        return new PasswordAuthentication(user, pass.toCharArray());
                    }
                })
                .connectTimeout(Duration.ofSeconds(15))
                .build();
    }

    static String exitIp(HttpClient client) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(TARGET).timeout(Duration.ofSeconds(30)).build();
        return client.send(req, HttpResponse.BodyHandlers.ofString()).body().trim();
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
