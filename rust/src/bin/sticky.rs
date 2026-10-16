//! Hold one exit IP across several connections with a session ID in the username.
//!
//!     cargo run --bin sticky
//!
//! On the rotating gateways a session holds its exit for up to 30 minutes from first use.
//! Use a new ID to get a new exit. Residential sessions are best effort with the same ceiling.

use std::collections::HashSet;

use node4_examples::{builder, env, get_text, proxy, session_id};

#[tokio::main]
async fn main() {
    let env = env();
    let id = session_id();
    let user = format!("{}-session-{id}", env.user);
    let mut seen = HashSet::new();
    for _ in 0..3 {
        // A new client each time means a new connection, yet the exit stays the same.
        let client = builder(proxy("http", &env.gateway, &user, &env.pass)).build().unwrap();
        let ip = get_text(&client, "https://api.ipify.org").await;
        println!("session {id} -> {ip}");
        seen.insert(ip);
    }
    println!("distinct exits: {} (expect 1)", seen.len());
}
