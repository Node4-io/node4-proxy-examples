// Many requests at once through a Node4 gateway, capped to a fixed number of connections,
// with backoff that retries from a new exit and never retries a 407.
//
//   export NODE4_USER=... NODE4_PASS=...
//   java ConcurrentFetcher.java                 # 40 requests, 10 workers, new connection per request
//   java ConcurrentFetcher.java 20 5 reuse      # 20 requests, 5 workers, keep each worker's tunnel open
//
// Each worker owns one HttpClient and sends one request at a time, so the number of open
// connections never exceeds the worker count. Keep it at or below your plan's limit
// (10 on the free tier; your connection count on Rotating Unmetered).
//
// "fresh" (the default) gives every request its own connection, so each can leave from a
// different exit. "reuse" keeps one tunnel per worker: fewer handshakes, but each worker keeps
// its exit until a retry replaces its client.
//
// Retries: 403/429/5xx and network errors back off (1s, 2s, 4s ... plus jitter) and retry on a
// NEW connection, so the retry can leave from a different exit. Retrying down the same tunnel
// would retry from the same IP. A 407 means wrong credentials or a product your plan does not
// include: every worker stops, because more attempts only add failed logins.
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
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentFetcher {
    static final Set<Integer> RETRY_ON = Set.of(403, 429, 500, 502, 503, 504);
    static final int MAX_ATTEMPTS = 4;

    static String user, pass;
    static InetSocketAddress gateway;
    static final AtomicBoolean authFailed = new AtomicBoolean();

    /** Thrown when the proxy rejects the credentials. Never retried. */
    static class ProxyAuthException extends IOException {
        ProxyAuthException() { super("407 from the proxy"); }
    }

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
        int n = args.length > 0 ? Integer.parseInt(args[0]) : 40;
        int workers = args.length > 1 ? Integer.parseInt(args[1]) : 10;
        boolean fresh = args.length < 3 || !args[2].equals("reuse");
        URI target = URI.create(env("TARGET_URL", "https://api.ipify.org"));

        AtomicInteger next = new AtomicInteger();
        AtomicInteger failed = new AtomicInteger();
        Map<String, Integer> exits = new ConcurrentHashMap<>();
        long start = System.nanoTime();

        ExecutorService pool = Executors.newFixedThreadPool(workers);
        for (int w = 0; w < workers; w++) {
            pool.submit(() -> {
                HttpClient client = null;
                try {
                    while (next.getAndIncrement() < n && !authFailed.get()) {
                        if (client == null || fresh) {
                            if (client != null) client.close();
                            client = newClient();
                        }
                        try {
                            Fetched f = fetchWithRetry(client, target);
                            client = f.client;  // a retry may have replaced it
                            exits.merge(f.body.trim(), 1, Integer::sum);
                        } catch (ProxyAuthException e) {
                            authFailed.set(true);
                            client = null;      // fetchWithRetry closed it
                        } catch (Exception e) {
                            failed.incrementAndGet();
                            System.err.println("gave up: " + e.getMessage());
                            client = null;
                        }
                    }
                } finally {
                    if (client != null) client.close();
                }
            });
        }
        pool.shutdown();
        pool.awaitTermination(10, TimeUnit.MINUTES);

        if (authFailed.get()) {
            System.err.println("407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product");
            System.exit(1);
        }
        System.out.printf("%d requests, %d failed, %d distinct exits, %d workers, %s, %d ms%n",
                n, failed.get(), exits.size(), workers, fresh ? "fresh" : "reuse",
                (System.nanoTime() - start) / 1_000_000);
    }

    record Fetched(HttpClient client, String body) {}

    /**
     * Sends one request, retrying on a new connection when the answer is worth retrying.
     * Returns the client that succeeded (a retry replaces it). On failure the client is closed.
     */
    static Fetched fetchWithRetry(HttpClient client, URI target) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(target).timeout(Duration.ofSeconds(30)).build();
        for (int attempt = 1; ; attempt++) {
            String reason;
            try {
                HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
                if (resp.statusCode() == 407) throw new ProxyAuthException();
                if (!RETRY_ON.contains(resp.statusCode())) return new Fetched(client, resp.body());
                reason = "HTTP " + resp.statusCode();
            } catch (IOException e) {
                if (e instanceof ProxyAuthException || String.valueOf(e.getMessage()).contains("too many authentication attempts")) {
                    client.close();
                    throw new ProxyAuthException();
                }
                reason = e.getClass().getSimpleName();
            }
            client.close();          // drop the tunnel so a retry can leave from a different exit
            if (attempt == MAX_ATTEMPTS || authFailed.get()) {
                throw new IOException("after " + attempt + " attempts (" + reason + ")");
            }
            long delay = Math.min(30_000, 1000L << (attempt - 1)) + ThreadLocalRandom.current().nextLong(1000);
            System.err.printf("attempt %d: %s, retrying on a new connection in %.1fs%n", attempt, reason, delay / 1000.0);
            Thread.sleep(delay);
            client = newClient();
        }
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

    // IP literal, because java.net.URI rejects the underscore in the gateway hostname.
    static InetSocketAddress proxyAddress(String endpoint) throws IOException {
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
