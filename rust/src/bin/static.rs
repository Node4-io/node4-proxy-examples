//! One request through a static proxy. Traffic leaves from the exact IP you connect to.
//!
//!     NODE4_PROXY=203.0.113.10:4443 cargo run --bin static

use node4_examples::{builder, env, get_text, proxy};

#[tokio::main]
async fn main() {
    let env = env();
    if env.static_proxy.is_empty() {
        eprintln!("Set NODE4_PROXY to one of your static proxies, e.g. 203.0.113.10:4443.");
        std::process::exit(1);
    }
    let client = builder(proxy("http", &env.static_proxy, &env.user, &env.pass)).build().unwrap();
    let ip = get_text(&client, "https://api.ipify.org").await;
    let expected = env.static_proxy.split(':').next().unwrap_or_default();
    let status = if ip == expected { "OK" } else { "MISMATCH" };
    println!("{} -> exit IP {ip} ({status})", env.static_proxy);
}
