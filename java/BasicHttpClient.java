// One request through a Node4 rotating gateway with java.net.http.HttpClient (JDK 11+).
//
//   export NODE4_USER=... NODE4_PASS=...
//   java BasicHttpClient.java
//
// Three JDK details make this work:
//
// 1. HTTPS through a proxy uses a CONNECT tunnel, and the JDK refuses Basic proxy auth on
//    tunnels by default (jdk.http.auth.tunneling.disabledSchemes=Basic). Clear it before the
//    first HttpClient is built. Without it every https:// request comes back as a bare 407.
//
// 2. The gateway hostname has an underscore (gw-rotating_datacenter). java.net.URI rejects
//    it, and HttpClient builds a URI from the proxy host when it answers the 407 challenge, so
//    a hostname fails with "URISyntaxException: Illegal character in hostname". Resolve the
//    gateway first and give HttpClient the IP address as a string.
//
// 3. On a 407 the JDK re-sends the same credentials up to 3 more times. A 407 means wrong
//    credentials or a product your plan does not include, so retrying only adds failed
//    logins. jdk.httpclient.auth.retrylimit=0 makes it give up after one attempt.
import java.io.IOException;
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

public class BasicHttpClient {
    public static void main(String[] args) throws Exception {
        // Both are read once, when HttpClient first loads, so set them before building one
        // (or pass them as -D options on the command line).
        System.setProperty("jdk.http.auth.tunneling.disabledSchemes", "");
        System.setProperty("jdk.httpclient.auth.retrylimit", "0");

        String user = env("NODE4_USER", "");
        String pass = env("NODE4_PASS", "");
        if (user.isEmpty() || pass.isEmpty()) {
            System.err.println("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
            System.exit(1);
        }
        String gateway = env("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083");

        HttpClient client = HttpClient.newBuilder()
                .proxy(ProxySelector.of(proxyAddress(gateway)))
                .authenticator(proxyAuth(user, pass))
                .connectTimeout(Duration.ofSeconds(15))
                .build();

        HttpRequest req = HttpRequest.newBuilder(URI.create("https://api.ipify.org"))
                .timeout(Duration.ofSeconds(30))
                .build();
        try {
            HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
            System.out.println("status " + resp.statusCode() + ", exit IP " + resp.body().trim());
        } catch (IOException e) {
            if (isProxyAuthFailure(e)) {
                System.err.println("407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product");
                System.exit(1);
            }
            throw e;
        }
    }

    /** host:port to an address HttpClient can use, with the host as an IP literal. */
    static InetSocketAddress proxyAddress(String endpoint) throws IOException {
        int colon = endpoint.lastIndexOf(':');
        String host = endpoint.substring(0, colon);
        int port = Integer.parseInt(endpoint.substring(colon + 1));
        return new InetSocketAddress(InetAddress.getByName(host).getHostAddress(), port);
    }

    /** Answers the proxy's 407 challenge, and never a target site's 401. */
    static Authenticator proxyAuth(String user, String pass) {
        return new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                if (getRequestorType() != RequestorType.PROXY) return null;
                return new PasswordAuthentication(user, pass.toCharArray());
            }
        };
    }

    /** With retrylimit=0, rejected proxy credentials surface as this IOException. */
    static boolean isProxyAuthFailure(IOException e) {
        return String.valueOf(e.getMessage()).contains("too many authentication attempts");
    }

    static String env(String name, String fallback) {
        String v = System.getenv(name);
        return v == null || v.isEmpty() ? fallback : v;
    }
}
