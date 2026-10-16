# SOCKS5 with the socksify gem (bundle install first). SOCKS5 is on paid plans.
#
# socksify sends the target hostname to the proxy (socks5h behaviour), so DNS lookups
# do not leave your machine.
require "bundler/setup"
require "socksify/http"
require_relative "_env"

host, port = Node4.host_port(Node4.socks_endpoint(Node4::GATEWAY))
uri = URI("https://api.ipify.org")

http = Net::HTTP.socks_proxy(host, port, username: Node4::USER, password: Node4::PASS).new(uri.host, uri.port)
http.use_ssl = true
http.open_timeout = 15
http.read_timeout = 30
begin
  puts "exit IP over SOCKS5: #{http.request(Net::HTTP::Get.new(uri)).body.strip}"
rescue SOCKSError::NotAllowed, SOCKSError::ServerFailure => e
  # SOCKS5 has no 407. Wrong credentials, or a plan without SOCKS5 (the free tier),
  # come back as a refused connection. Like a 407, retrying will not help.
  abort "SOCKS5 refused (#{e.message}): check NODE4_USER/NODE4_PASS and that your plan includes SOCKS5"
end
