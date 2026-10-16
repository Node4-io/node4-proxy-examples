// Kotlin coroutines + OkHttp through a Node4 gateway.
//
//   export NODE4_USER=... NODE4_PASS=...
//   gradle run --args="rotate 20 10"   # 20 requests, at most 10 at once, new exit per request
//   gradle run --args="sticky 3"       # 3 sessions in parallel, each holding its own exit
//
// Concurrency is capped twice on purpose: a Semaphore limits how many coroutines are in a
// request at once, and the OkHttp dispatcher is capped to the same number. Keep it at or below
// your plan's limit (10 on the free tier; your connection count on Rotating Unmetered).

import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import java.io.IOException
import java.security.SecureRandom
import kotlin.system.exitProcess

const val TARGET = "https://api.ipify.org"

fun main(args: Array<String>) = runBlocking {
    val user = env("NODE4_USER")
    val pass = env("NODE4_PASS")
    if (user.isEmpty() || pass.isEmpty()) {
        System.err.println("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).")
        exitProcess(1)
    }
    val gateway = env("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083")

    try {
        when (args.getOrElse(0) { "rotate" }) {
            "rotate" -> rotate(gateway, user, pass, n = args.getOrNull(1)?.toInt() ?: 20, concurrency = args.getOrNull(2)?.toInt() ?: 10)
            "sticky" -> sticky(gateway, user, pass, sessions = args.getOrNull(1)?.toInt() ?: 3)
            else -> {
                System.err.println("usage: rotate [n] [concurrency] | sticky [sessions]")
                exitProcess(2)
            }
        }
    } catch (e: ProxyAuthException) {
        System.err.println("407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product")
        exitProcess(1)
    }
}

/** n requests, each on its own connection, at most [concurrency] at once. */
suspend fun rotate(gateway: String, user: String, pass: String, n: Int, concurrency: Int) {
    val client = proxyClient(gateway, user, pass, concurrency, keepAlive = false)
    val limit = Semaphore(concurrency)
    val start = System.nanoTime()
    try {
        // A ProxyAuthException escapes coroutineScope and cancels every other request.
        // Any other failure is counted and the rest carry on.
        val results: List<String?> = coroutineScope {
            (1..n).map {
                async {
                    limit.withPermit {
                        try {
                            fetch(client, TARGET)
                        } catch (e: ProxyAuthException) {
                            throw e
                        } catch (e: IOException) {
                            System.err.println(e.message)
                            null
                        }
                    }
                }
            }.awaitAll()
        }
        val exits = results.filterNotNull().toSet()
        val ms = (System.nanoTime() - start) / 1_000_000
        println("$n requests, ${results.count { it == null }} failed, ${exits.size} distinct exits, $concurrency at once, $ms ms")
    } finally {
        client.shutdown()
    }
}

/**
 * Several sticky sessions in parallel. Each session sends 3 requests, each on a NEW connection,
 * and still keeps one exit, because the -session-ID in the username holds it (up to 30 minutes
 * from first use on the rotating gateways; best effort on residential).
 */
suspend fun sticky(gateway: String, user: String, pass: String, sessions: Int) = coroutineScope {
    val random = SecureRandom()
    (1..sessions).map {
        async {
            val id = (1..8).map { "abcdefghijklmnopqrstuvwxyz0123456789"[random.nextInt(36)] }.joinToString("")
            val client = proxyClient(gateway, "$user-session-$id", pass, concurrency = 1, keepAlive = false)
            try {
                val seen = (1..3).map { fetch(client, TARGET) }
                "session $id -> ${seen.joinToString(", ")} (${seen.toSet().size} distinct, expect 1)"
            } finally {
                client.shutdown()
            }
        }
    }.awaitAll().forEach(::println)
}
