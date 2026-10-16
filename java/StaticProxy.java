// One request through a static Node4 proxy (dedicated or shared datacenter).
//
//   export NODE4_USER=... NODE4_PASS=... NODE4_PROXY=203.0.113.10:4443
//   java StaticProxy.java
//
// Static proxies are plain IPs, so the underscore problem from the gateways does not apply.
// Basic auth on CONNECT tunnels still has to be re-enabled (see BasicHttpClient.java).
// Traffic leaves from the exact IP you connect to; this checks that it does.
import java.io.IOException;
import java.net.Authenticator;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class StaticProxy {
    public static void main(String[] args) throws Exception {
        System.setProperty("jdk.http.auth.tunneling.disabledSchemes", "");
        System.setProperty("jdk.httpclient.auth.retrylimit", "0");

        String user = env("NODE4_USER"), pass = env("NODE4_PASS"), proxy = env("NODE4_PROXY");
        if (user.isEmpty() || pass.isEmpty()) {
            System.err.println("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
            System.exit(1);
        }
        if (proxy.isEmpty()) {
            System.err.println("Set NODE4_PROXY to one of your static proxies, e.g. 203.0.113.10:4443.");
            System.exit(1);
        }
        int colon = proxy.lastIndexOf(':');
        String ip = proxy.substring(0, colon);
        int port = Integer.parseInt(proxy.substring(colon + 1));

        HttpClient client = HttpClient.newBuilder()
                .proxy(ProxySelector.of(new InetSocketAddress(ip, port)))
                .authenticator(new Authenticator() {
                    @Override
                    protected PasswordAuthentication getPasswordAuthentication() {
                        if (getRequestorType() != RequestorType.PROXY) return null;
                        return new PasswordAuthentication(user, pass.toCharArray());
                    }
                })
                .connectTimeout(Duration.ofSeconds(15))
                .build();

        HttpRequest req = HttpRequest.newBuilder(URI.create("https://api.ipify.org"))
                .timeout(Duration.ofSeconds(30))
                .build();
        try {
            String exit = client.send(req, HttpResponse.BodyHandlers.ofString()).body().trim();
            System.out.println(proxy + " -> exit IP " + exit + (exit.equals(ip) ? " (matches)" : " (MISMATCH)"));
        } catch (IOException e) {
            if (String.valueOf(e.getMessage()).contains("too many authentication attempts")) {
                System.err.println("407 from the proxy: check NODE4_USER/NODE4_PASS and that this IP is on your account");
                System.exit(1);
            }
            throw e;
        }
    }

    static String env(String name) {
        String v = System.getenv(name);
        return v == null ? "" : v;
    }
}
