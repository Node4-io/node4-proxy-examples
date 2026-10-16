# Hold one exit IP across several connections with a session ID in the username.
#
# On the rotating gateways a session holds its exit for up to 30 minutes from first use.
# Use a new ID to get a new exit. Residential sessions are best effort with the same ceiling.
require "securerandom"
require_relative "_env"

session_id = SecureRandom.alphanumeric(8) # up to 32 letters and digits
user = "#{Node4::USER}-session-#{session_id}"
uri = URI("https://api.ipify.org")

seen = Array.new(3) do
  # A new Net::HTTP connection each time, yet the exit stays the same.
  ip = Node4.get(uri, user: user).body.strip
  puts "session #{session_id} -> #{ip}"
  ip
end
puts "distinct exits: #{seen.uniq.size} (expect 1)"
