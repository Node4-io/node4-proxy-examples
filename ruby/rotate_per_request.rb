# Why a reused connection keeps one IP, and how to get a new exit per request.
#
# Rotation is per CONNECTION. An HTTPS request travels inside a CONNECT tunnel, and every
# request sent down that tunnel leaves from the same exit. Net::HTTP#start keeps the
# tunnel open for everything inside the block, so the first loop reports one IP. The
# second loop opens a fresh connection per request, so each one can get a different exit.
require_relative "_env"

uri = URI("https://api.ipify.org")

reused = []
Node4.http_for(uri).start do |http|
  5.times { reused << http.request(Net::HTTP::Get.new(uri)).body.strip }
end
puts "one started session, 5 requests -> #{reused.uniq.size} distinct exit(s)"

# Net::HTTP#request outside a start block opens and closes its own connection.
fresh = Array.new(5) { Node4.get(uri).body.strip }
puts "new connection each time        -> #{fresh.uniq.size} distinct exit(s)"
