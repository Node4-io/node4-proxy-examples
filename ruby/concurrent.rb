# Many requests at once with a fixed pool of threads, plus retry with backoff.
#
#   CONCURRENCY=10 N=20 ruby concurrent.rb
#
# On Rotating Unmetered you buy concurrent connections, so keep CONCURRENCY at or below
# your plan's connection count. Each request opens its own connection, so each one can
# leave from a different exit, and each retry gets a new exit too.
#
# 403/429/5xx from the target: back off and retry on a new connection.
# 407 from the proxy: wrong credentials or a product your plan does not include. Never retried.
require_relative "_env"

CONCURRENCY = Integer(ENV.fetch("CONCURRENCY", "10"))
N = Integer(ENV.fetch("N", "20"))
URL = URI(ENV.fetch("URL", "https://api.ipify.org"))
RETRY_ON = %w[403 429 500 502 503 504].freeze
NETWORK_ERRORS = [Net::OpenTimeout, Net::ReadTimeout, Errno::ECONNRESET, Errno::ECONNREFUSED,
                  EOFError, OpenSSL::SSL::SSLError, SocketError].freeze

class ProxyAuthError < StandardError; end

def fetch(uri, attempts: 4)
  attempts.times do |i|
    reason =
      begin
        res = Node4.http_for(uri).request(Net::HTTP::Get.new(uri))
        raise ProxyAuthError, Node4::AUTH_HINT if res.code == "407"
        return res.body.strip unless RETRY_ON.include?(res.code)

        "HTTP #{res.code}"
      rescue Net::HTTPClientException => e
        # For an https:// target a 407 arrives as an exception from the CONNECT step.
        raise ProxyAuthError, Node4::AUTH_HINT if e.message.start_with?("407")

        e.message
      rescue *NETWORK_ERRORS => e
        e.class.name
      end
    raise "gave up after #{attempts} attempts (#{reason})" if i == attempts - 1

    delay = [30, 2**(i + 1)].min + rand
    warn format("attempt %d: %s, retrying in %.1fs", i + 1, reason, delay)
    sleep delay
  end
end

queue = Queue.new
N.times { queue << URL }
queue.close

results = Queue.new
started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
workers = Array.new(CONCURRENCY) do
  Thread.new do
    while (uri = queue.pop)
      begin
        results << [:ok, fetch(uri)]
      rescue ProxyAuthError => e
        queue.clear # stop: every other request would fail the same way
        results << [:auth, e.message]
      rescue StandardError => e
        results << [:fail, e.message]
      end
    end
  end
end
workers.each(&:join)

all = Array.new(results.size) { results.pop }
ok = all.select { |kind, _| kind == :ok }.map(&:last)
secs = Process.clock_gettime(Process::CLOCK_MONOTONIC) - started
puts format("%d/%d ok, %d distinct exits, concurrency %d, %.1fs", ok.size, N, ok.uniq.size, CONCURRENCY, secs)
abort Node4::AUTH_HINT if all.any? { |kind, _| kind == :auth }
