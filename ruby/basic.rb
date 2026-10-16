# The smallest working example: one request through the rotating gateway with Net::HTTP.
require "json"
require_relative "_env"

uri = URI("https://api.ipify.org?format=json")
res = Node4.get(uri)
abort "HTTP #{res.code}" unless res.is_a?(Net::HTTPSuccess)
puts "exit IP: #{JSON.parse(res.body)["ip"]}"
