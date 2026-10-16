//! The smallest working example: one request through the rotating gateway.
//!
//!     cargo run --bin basic

use node4_examples::{builder, env, get_text, proxy};

#[tokio::main]
async fn main() {
    let env = env();
    let client = builder(proxy("http", &env.gateway, &env.user, &env.pass)).build().unwrap();
    println!("exit IP: {}", get_text(&client, "https://api.ipify.org").await);
}
