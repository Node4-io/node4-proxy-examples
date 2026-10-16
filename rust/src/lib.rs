//! Shared settings for the examples: credentials and endpoints from the environment.

use std::error::Error as _;
use std::time::Duration;

pub const AUTH_HINT: &str =
    "407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product";

pub struct Env {
    pub user: String,
    pub pass: String,
    /// Rotating or residential gateway, `host:port`.
    pub gateway: String,
    /// One of your static proxies, `IP:4443` (may be empty).
    pub static_proxy: String,
}

/// Read NODE4_USER, NODE4_PASS, NODE4_GATEWAY and NODE4_PROXY, or exit with a hint.
pub fn env() -> Env {
    let get = |k: &str| std::env::var(k).unwrap_or_default();
    let (user, pass) = (get("NODE4_USER"), get("NODE4_PASS"));
    if user.is_empty() || pass.is_empty() {
        eprintln!("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).");
        std::process::exit(1);
    }
    let gateway = Some(get("NODE4_GATEWAY"))
        .filter(|g| !g.is_empty())
        .unwrap_or_else(|| "gw-rotating_datacenter.node4.io:8083".to_string());
    Env { user, pass, gateway, static_proxy: get("NODE4_PROXY") }
}

/// A proxy for `scheme://endpoint` with the credentials set separately, so the
/// username and password need no percent-encoding.
pub fn proxy(scheme: &str, endpoint: &str, user: &str, pass: &str) -> reqwest::Proxy {
    reqwest::Proxy::all(format!("{scheme}://{endpoint}"))
        .expect("valid proxy URL")
        .basic_auth(user, pass)
}

/// A client builder that sends everything through the given proxy.
pub fn builder(proxy: reqwest::Proxy) -> reqwest::ClientBuilder {
    reqwest::Client::builder()
        .proxy(proxy)
        .connect_timeout(Duration::from_secs(15))
        .timeout(Duration::from_secs(30))
}

/// The SOCKS5 port that pairs with an HTTP endpoint (8083->1083, 4443->1443, ...).
pub fn socks_endpoint(endpoint: &str) -> String {
    let (host, port) = endpoint.rsplit_once(':').expect("endpoint is host:port");
    let port = match port {
        "8082" => "1082",
        "8083" => "1083",
        "8084" => "1084",
        "4443" => "1443",
        other => other,
    };
    format!("{host}:{port}")
}

/// True when the proxy refused the credentials. For an https:// target the 407
/// arrives as a connect error from the CONNECT step, not as a response, so walk the
/// error chain. Retrying cannot fix this.
pub fn is_proxy_auth_error(err: &reqwest::Error) -> bool {
    let mut cur: Option<&dyn std::error::Error> = Some(err);
    while let Some(e) = cur {
        let msg = e.to_string().to_lowercase();
        if msg.contains("407") || msg.contains("proxy authentication required") || msg.contains("proxy authorization required") {
            return true;
        }
        cur = e.source();
    }
    false
}

/// Print a short reason for a failed request and exit.
pub fn fail(err: reqwest::Error) -> ! {
    let mut msg = err.to_string();
    let mut src = err.source();
    while let Some(e) = src {
        msg.push_str(&format!(": {e}"));
        src = e.source();
    }
    if is_proxy_auth_error(&err) {
        eprintln!("{AUTH_HINT}");
    } else if msg.contains("SOCKS error: connection not allowed") {
        // SOCKS5 has no 407. Wrong credentials, or a plan without SOCKS5 (the free tier),
        // come back as a refused connection. Like a 407, retrying will not help.
        eprintln!("SOCKS5 refused: check NODE4_USER/NODE4_PASS and that your plan includes SOCKS5");
    } else {
        eprintln!("request failed: {msg}");
    }
    std::process::exit(1);
}

/// GET a URL and return the trimmed body, exiting with a clear message on failure.
pub async fn get_text(client: &reqwest::Client, url: &str) -> String {
    let resp = client.get(url).send().await.unwrap_or_else(|e| fail(e));
    if resp.status() == reqwest::StatusCode::PROXY_AUTHENTICATION_REQUIRED {
        eprintln!("{AUTH_HINT}");
        std::process::exit(1);
    }
    resp.text().await.unwrap_or_else(|e| fail(e)).trim().to_string()
}

/// A short random ID for a sticky session (letters and digits, up to 32 allowed).
pub fn session_id() -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};
    let mut h = RandomState::new().build_hasher();
    h.write_u128(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos());
    format!("{:08x}", h.finish() as u32)
}
