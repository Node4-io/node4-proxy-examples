//! Many requests at once, capped by a semaphore, with retry and backoff.
//!
//!     CONCURRENCY=10 N=20 cargo run --release --bin concurrent
//!
//! On Rotating Unmetered you buy concurrent connections, so keep CONCURRENCY at or below
//! your plan's connection count. The client keeps no idle connections, so every request
//! (and every retry) opens its own connection and can leave from a different exit.
//!
//! 403/429/5xx from the target: back off and retry on a new connection.
//! 407 from the proxy: wrong credentials or a product your plan does not include. Never retried.

use std::collections::HashSet;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use node4_examples::{builder, env, is_proxy_auth_error, proxy, AUTH_HINT};
use reqwest::StatusCode;
use tokio::sync::Semaphore;
use tokio::task::JoinSet;

enum Failure {
    Auth,
    GaveUp(String),
}

fn retryable(status: StatusCode) -> bool {
    matches!(status.as_u16(), 403 | 429 | 500 | 502 | 503 | 504)
}

fn jitter() -> Duration {
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().subsec_nanos();
    Duration::from_millis(u64::from(nanos % 1000))
}

async fn fetch(client: &reqwest::Client, url: &str, attempts: u32) -> Result<String, Failure> {
    for attempt in 1..=attempts {
        let reason = match client.get(url).send().await {
            Ok(r) if r.status() == StatusCode::PROXY_AUTHENTICATION_REQUIRED => return Err(Failure::Auth),
            Ok(r) if !retryable(r.status()) => {
                return r.text().await.map(|t| t.trim().to_string()).map_err(|e| Failure::GaveUp(e.to_string()))
            }
            Ok(r) => format!("HTTP {}", r.status().as_u16()),
            Err(e) if is_proxy_auth_error(&e) => return Err(Failure::Auth),
            Err(e) => e.to_string(),
        };
        if attempt == attempts {
            return Err(Failure::GaveUp(format!("gave up after {attempts} attempts ({reason})")));
        }
        let delay = Duration::from_secs(2u64.pow(attempt).min(30)) + jitter();
        eprintln!("attempt {attempt}: {reason}, retrying in {:.1}s", delay.as_secs_f32());
        tokio::time::sleep(delay).await;
    }
    unreachable!()
}

#[tokio::main]
async fn main() {
    let env = env();
    let num = |k: &str, d: usize| std::env::var(k).ok().and_then(|v| v.parse().ok()).unwrap_or(d);
    let concurrency = num("CONCURRENCY", 10);
    let n = num("N", 20);
    let url: Arc<str> = std::env::var("URL").unwrap_or_else(|_| "https://api.ipify.org".into()).into();

    // pool_max_idle_per_host(0): no keep-alive, a new connection (and exit) per request.
    let client = builder(proxy("http", &env.gateway, &env.user, &env.pass))
        .pool_max_idle_per_host(0)
        .build()
        .unwrap();
    let sem = Arc::new(Semaphore::new(concurrency));
    let auth_failed = Arc::new(AtomicBool::new(false));
    let start = Instant::now();

    let mut tasks = JoinSet::new();
    for _ in 0..n {
        let (client, sem, url, auth_failed) = (client.clone(), sem.clone(), url.clone(), auth_failed.clone());
        tasks.spawn(async move {
            let _permit = sem.acquire_owned().await.unwrap();
            if auth_failed.load(Ordering::Relaxed) {
                return Err(Failure::Auth); // stop: every other request would fail the same way
            }
            let result = fetch(&client, &url, 4).await;
            if matches!(result, Err(Failure::Auth)) {
                auth_failed.store(true, Ordering::Relaxed);
            }
            result
        });
    }

    let (mut ok, mut exits) = (0, HashSet::new());
    while let Some(joined) = tasks.join_next().await {
        match joined.unwrap() {
            Ok(ip) => {
                ok += 1;
                exits.insert(ip);
            }
            Err(Failure::GaveUp(reason)) => eprintln!("{reason}"),
            Err(Failure::Auth) => {}
        }
    }
    println!(
        "{ok}/{n} ok, {} distinct exits, concurrency {concurrency}, {:.1}s",
        exits.len(),
        start.elapsed().as_secs_f32()
    );
    if auth_failed.load(Ordering::Relaxed) {
        eprintln!("{AUTH_HINT}");
        std::process::exit(1);
    }
}
