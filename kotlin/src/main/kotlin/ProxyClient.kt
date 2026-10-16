// OkHttp set up for a Node4 gateway, plus a suspending fetch with retries.

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.Callback
import okhttp3.ConnectionPool
import okhttp3.Credentials
import okhttp3.Dispatcher
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Proxy
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resumeWithException
import kotlin.random.Random

/** The proxy rejected the login: wrong credentials, or a product your plan does not include. Never retried. */
class ProxyAuthException : IOException("407 from the proxy")

val RETRY_ON = setOf(403, 429, 500, 502, 503, 504)

fun env(name: String, fallback: String = ""): String = System.getenv(name)?.takeIf { it.isNotEmpty() } ?: fallback

/**
 * An OkHttp client that sends every request through [endpoint] (host:port).
 *
 * - OkHttp resolves the proxy host itself, so the underscore in gw-rotating_datacenter is fine.
 * - [concurrency] caps OkHttp's own dispatcher too. Its default is 5 requests per target host,
 *   which would silently queue anything above 5 when every request goes to one site.
 * - keepAlive = false empties the connection pool AND turns off HTTP/2, so each request opens
 *   its own tunnel and can leave from a different exit. HTTP/2 matters: OkHttp multiplexes
 *   concurrent requests to one site over a single HTTP/2 connection, which means one tunnel
 *   and one exit no matter how small the pool is. With keepAlive = true, requests share
 *   tunnels and exits.
 */
fun proxyClient(endpoint: String, user: String, pass: String, concurrency: Int, keepAlive: Boolean): OkHttpClient {
    val host = endpoint.substringBeforeLast(':')
    val port = endpoint.substringAfterLast(':').toInt()
    val credential = Credentials.basic(user, pass)
    val builder = OkHttpClient.Builder()
        .proxy(Proxy(Proxy.Type.HTTP, InetSocketAddress.createUnresolved(host, port)))
        .proxyAuthenticator { _, response ->
            // Already sent the login and still got a 407: stop instead of retrying it.
            if (response.request.header("Proxy-Authorization") != null) null
            else response.request.newBuilder().header("Proxy-Authorization", credential).build()
        }
        .dispatcher(Dispatcher().apply { maxRequests = concurrency; maxRequestsPerHost = concurrency })
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
    if (!keepAlive) {
        builder.connectionPool(ConnectionPool(0, 1, TimeUnit.SECONDS))
        builder.protocols(listOf(Protocol.HTTP_1_1))
    }
    return builder.build()
}

/** Lets the JVM exit right away instead of waiting for OkHttp's idle threads. */
fun OkHttpClient.shutdown() {
    dispatcher.executorService.shutdown()
    connectionPool.evictAll()
}

/** Suspends until the call completes; cancelling the coroutine cancels the call. */
suspend fun Call.await(): Response = suspendCancellableCoroutine { cont ->
    enqueue(object : Callback {
        override fun onResponse(call: Call, response: Response) {
            cont.resume(response) { _ -> response.close() }
        }

        override fun onFailure(call: Call, e: IOException) {
            cont.resumeWithException(e)
        }
    })
    cont.invokeOnCancellation { cancel() }
}

/**
 * GET [url] and return the body. 403/429/5xx and network errors back off and retry; on a
 * keepAlive = false client each retry is a new connection, so it can leave from a different
 * exit. A 407 throws [ProxyAuthException] at once.
 */
suspend fun fetch(client: OkHttpClient, url: String, attempts: Int = 4): String {
    val request = Request.Builder().url(url).build()
    var reason = ""
    for (attempt in 1..attempts) {
        try {
            client.newCall(request).await().use { r ->
                if (r.code == 407) throw ProxyAuthException()
                if (r.code !in RETRY_ON) return withContext(Dispatchers.IO) { r.body!!.string().trim() }
                reason = "HTTP ${r.code}"
            }
        } catch (e: ProxyAuthException) {
            throw e
        } catch (e: IOException) {
            // For https:// targets the 407 comes back on the CONNECT, and OkHttp reports it like this.
            if (e.message == "Failed to authenticate with proxy") throw ProxyAuthException()
            reason = e.javaClass.simpleName
        }
        if (attempt < attempts) {
            val wait = minOf(30_000L, 1000L shl (attempt - 1)) + Random.nextLong(1000)
            System.err.println("attempt $attempt: $reason, retrying in ${wait / 1000.0}s")
            delay(wait)
        }
    }
    throw IOException("gave up after $attempts attempts ($reason)")
}
