# Shared settings for the examples: credentials and endpoints from the environment.
require "net/http"

module Node4
  USER = ENV.fetch("NODE4_USER", "")
  PASS = ENV.fetch("NODE4_PASS", "")
  GATEWAY = ENV.fetch("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083")
  STATIC = ENV.fetch("NODE4_PROXY", "") # one of your static proxies, e.g. 203.0.113.10:4443

  abort "Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies)." if USER.empty? || PASS.empty?

  AUTH_HINT = "407 from the proxy: check NODE4_USER/NODE4_PASS and that your plan includes this product".freeze

  module_function

  # Split "host:port" into ["host", port].
  def host_port(endpoint)
    host, port = endpoint.split(":", 2)
    [host, Integer(port)]
  end

  # A Net::HTTP object for the target URI that goes through a Node4 proxy.
  # Net::HTTP takes the proxy host, port, user and password as separate arguments,
  # so nothing is parsed as a URL: the underscore in the gateway hostname and special
  # characters in the password need no escaping.
  def http_for(uri, endpoint: GATEWAY, user: USER)
    p_host, p_port = host_port(endpoint)
    http = Net::HTTP.new(uri.host, uri.port, p_host, p_port, user, PASS)
    http.use_ssl = uri.scheme == "https"
    http.open_timeout = 15
    http.read_timeout = 30
    http
  end

  # GET a URI through the proxy on a new connection and return the response.
  # For an https:// target a 407 arrives as an exception from the CONNECT step; it is
  # turned into a clear message here because retrying cannot fix it.
  def get(uri, **opts)
    http_for(uri, **opts).request(Net::HTTP::Get.new(uri))
  rescue Net::HTTPClientException => e
    raise e unless e.message.start_with?("407")
    abort AUTH_HINT
  end

  # The SOCKS5 port that pairs with an HTTP endpoint (8083->1083, 4443->1443, ...).
  def socks_endpoint(endpoint)
    host, port = endpoint.split(":", 2)
    pairs = { "8082" => "1082", "8083" => "1083", "8084" => "1084", "4443" => "1443" }
    "#{host}:#{pairs.fetch(port, port)}"
  end
end
