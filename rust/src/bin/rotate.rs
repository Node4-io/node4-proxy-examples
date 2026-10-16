//! Why a reused client keeps one IP, and how to get a new exit per request.
//!
//!     cargo run --bin rotate
//!
//! Rotation is per CONNECTION. An HTTPS request travels inside a CONNECT tunnel, and every
//! request sent down that tunnel leaves from the same exit. A default reqwest::Client keeps
//! idle tunnels in a pool and reuses them, so the first loop reports one IP. With
//! pool_max_idle_per_host(0) nothing is kept, every request opens its own connection, and
//! each one can get a different exit.

use std::collections::HashSet;

use node4_examples::{builder, env, get_text, proxy};

const URL: &str = "https://api.ipify.org";

#[tokio::main]
async fn main() {
    let env = env();
    let p = || proxy("http", &env.gateway, &env.user, &env.pass);

    let pooled = builder(p()).build().unwrap();
    let mut reused = HashSet::new();
    for _ in 0..5 {
        reused.insert(get_text(&pooled, URL).await);
    }
    println!("default client, 5 requests      -> {} distinct exit(s)", reused.len());

    let unpooled = builder(p()).pool_max_idle_per_host(0).build().unwrap();
    let mut fresh = HashSet::new();
    for _ in 0..5 {
        fresh.insert(get_text(&unpooled, URL).await);
    }
    println!("pool_max_idle_per_host(0), 5 req -> {} distinct exit(s)", fresh.len());
}
