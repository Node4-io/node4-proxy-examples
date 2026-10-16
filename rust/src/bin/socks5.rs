//! SOCKS5 through the gateway's SOCKS5 port (8083 -> 1083). SOCKS5 is on paid plans.
//!
//!     cargo run --bin socks5
//!
//! socks5h:// makes the proxy resolve hostnames, so DNS lookups do not leave your machine.
//! Needs reqwest's "socks" feature (see Cargo.toml).

use node4_examples::{builder, env, get_text, proxy, socks_endpoint};

#[tokio::main]
async fn main() {
    let env = env();
    let endpoint = socks_endpoint(&env.gateway);
    let client = builder(proxy("socks5h", &endpoint, &env.user, &env.pass)).build().unwrap();
    println!("exit IP over SOCKS5: {}", get_text(&client, "https://api.ipify.org").await);
}
