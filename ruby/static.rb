# One request through a static proxy. Traffic leaves from the exact IP you connect to.
#
#   NODE4_PROXY=203.0.113.10:4443 ruby static.rb
require_relative "_env"

abort "Set NODE4_PROXY to one of your static proxies, e.g. 203.0.113.10:4443." if Node4::STATIC.empty?

uri = URI("https://api.ipify.org")
ip = Node4.get(uri, endpoint: Node4::STATIC).body.strip
expected = Node4.host_port(Node4::STATIC).first
puts "#{Node4::STATIC} -> exit IP #{ip} (#{ip == expected ? "OK" : "MISMATCH"})"
