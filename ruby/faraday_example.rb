# Faraday with a proxy (bundle install first; see the Gemfile).
#
# Faraday takes the proxy as a URL, so percent-encode the username and password:
# a password containing @, : or / otherwise breaks the URL.
require "bundler/setup"
require "erb"
require "faraday"
require "faraday/net_http_persistent"
require_relative "_env"

enc = ->(s) { ERB::Util.url_encode(s) }
proxy = "http://#{enc.call(Node4::USER)}:#{enc.call(Node4::PASS)}@#{Node4::GATEWAY}"
opts = { url: "https://api.ipify.org", proxy: proxy, request: { timeout: 30 } }

# Default adapter (Net::HTTP): a new connection, and so a possible new exit, per request.
conn = Faraday.new(**opts)
fresh = Array.new(3) { conn.get("/").body.strip }
puts "net_http            -> #{fresh.join(", ")} (#{fresh.uniq.size} distinct)"

# Persistent adapter: keeps the tunnel open, so requests share one exit.
persistent = Faraday.new(**opts) { |f| f.adapter :net_http_persistent }
kept = Array.new(3) { persistent.get("/").body.strip }
puts "net_http_persistent -> #{kept.join(", ")} (#{kept.uniq.size} distinct)"
