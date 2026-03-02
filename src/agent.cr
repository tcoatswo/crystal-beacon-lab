# crystal-beacon-lab — safe telemetry agent
#
# This is intentionally *non-offensive*.
# It periodically POSTs basic host metadata to a configured HTTP endpoint.

require "http/client"
require "json"
require "option_parser"
require "uuid"

struct HostInfo
  include JSON::Serializable

  getter user : String?
  getter hostname : String
  getter os : String
  getter cpu_count : Int32

  def initialize
    @user = ENV["USER"]?
    @hostname = `hostname`.strip
    @os = `uname -s`.strip.downcase
    @cpu_count = System.cpu_count
  end
end

struct Payload
  include JSON::Serializable

  getter agent_id : String
  getter sent_at : String
  getter host : HostInfo

  def initialize(@agent_id : String)
    @sent_at = Time.utc.to_s("%FT%TZ")
    @host = HostInfo.new
  end
end

url = ""
interval = 15
jitter = 0
agent_id = UUID.random.to_s[0, 8]

OptionParser.parse do |parser|
  parser.banner = "Usage: crystal-beacon [--url URL] [--interval SECONDS] [--jitter SECONDS] [--agent-id ID]"

  parser.on("--url URL", "Collector endpoint (e.g., http://127.0.0.1:8080/ingest)") { |v| url = v }
  parser.on("--interval SECONDS", "Send interval in seconds (default: 15)") { |v| interval = v.to_i }
  parser.on("--jitter SECONDS", "Add uniform random jitter +/- SECONDS to sleep interval (default: 0)") { |v| jitter = v.to_i }
  parser.on("--agent-id ID", "Optional stable agent id") { |v| agent_id = v }
  parser.on("-h", "--help", "Show help") do
    puts parser
    exit 0
  end
end

if url.empty?
  STDERR.puts "ERROR: --url is required"
  exit 2
end

if interval <= 0
  STDERR.puts "ERROR: --interval must be > 0"
  exit 2
end

if jitter < 0
  STDERR.puts "ERROR: --jitter must be >= 0"
  exit 2
end

puts "agent_id=#{agent_id} interval=#{interval}s jitter=+/-#{jitter}s url=#{url}"

loop do
  payload = Payload.new(agent_id)

  begin
    body = payload.to_json
    res = HTTP::Client.post(
      url,
      headers: HTTP::Headers{"Content-Type" => "application/json"},
      body: body
    )

    puts "sent_at=#{payload.sent_at} status=#{res.status_code}"
  rescue ex
    STDERR.puts "request_failed=#{ex.message}"
  end

  sleep_seconds = interval

  if jitter > 0
    # Uniform integer jitter in [-jitter, +jitter]
    delta = Random.rand((-jitter)..jitter)
    sleep_seconds = interval + delta
  end

  # Clamp to at least 1s to avoid accidental hammering
  sleep_seconds = 1 if sleep_seconds < 1
  sleep sleep_seconds.seconds
end
