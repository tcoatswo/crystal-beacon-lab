# crystal-beacon-lab — safe telemetry agent
#
# This is intentionally *non-offensive*.
# It periodically POSTs a minimal JSON payload to a configured HTTP endpoint.

require "http/client"
require "json"
require "option_parser"
require "uuid"

SCHEMA_VERSION = 1
AGENT_VERSION  = "0.2.0"

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

  getter schema_version : Int32
  getter agent_version : String
  getter agent_id : String
  getter sent_at : String
  getter nonce : String
  getter tags : Hash(String, String)
  getter user_agent : String
  getter host : HostInfo

  def initialize(@agent_id : String, @tags : Hash(String, String), @user_agent : String)
    @schema_version = SCHEMA_VERSION
    @agent_version = AGENT_VERSION
    @sent_at = Time.utc.to_s("%FT%TZ")
    @nonce = UUID.random.to_s
    @host = HostInfo.new
  end
end

url = ""
interval = 15
jitter = 0
jitter_mode = "uniform" # uniform|none
agent_id = UUID.random.to_s[0, 8]
beacon_key = ENV["BEACON_KEY"]?

tags = {} of String => String

OptionParser.parse do |parser|
  parser.banner = "Usage: crystal-beacon [--url URL] [--interval SECONDS] [--jitter SECONDS] [--jitter-mode MODE] [--tag k=v] [--agent-id ID]"

  parser.on("--url URL", "Collector endpoint (e.g., http://127.0.0.1:8080/ingest)") { |v| url = v }
  parser.on("--interval SECONDS", "Send interval in seconds (default: 15)") { |v| interval = v.to_i }
  parser.on("--jitter SECONDS", "Add random jitter to sleep interval (default: 0)") { |v| jitter = v.to_i }
  parser.on("--jitter-mode MODE", "Jitter mode: uniform|none (default: uniform)") { |v| jitter_mode = v }
  parser.on("--tag KV", "Add a tag (repeatable): key=value") do |kv|
    parts = kv.split("=", 2)
    if parts.size == 2
      tags[parts[0]] = parts[1]
    else
      STDERR.puts "WARN: ignoring invalid tag '#{kv}'"
    end
  end
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

if jitter_mode != "uniform" && jitter_mode != "none"
  STDERR.puts "ERROR: --jitter-mode must be one of: uniform, none"
  exit 2
end

# Stable-ish UA for correlation experiments
user_agent = "crystal-beacon/#{AGENT_VERSION} (agent_id=#{agent_id})"

puts "agent_id=#{agent_id} interval=#{interval}s jitter=+/-#{jitter}s jitter_mode=#{jitter_mode} url=#{url} tags=#{tags}"

loop do
  payload = Payload.new(agent_id, tags, user_agent)

  begin
    body = payload.to_json
    headers = HTTP::Headers{"Content-Type" => "application/json"}
    headers["User-Agent"] = user_agent
    if beacon_key
      headers["X-Beacon-Key"] = beacon_key
    end

    res = HTTP::Client.post(url, headers: headers, body: body)
    puts "sent_at=#{payload.sent_at} status=#{res.status_code}"
  rescue ex
    STDERR.puts "request_failed=#{ex.message}"
  end

  sleep_seconds = interval
  if jitter > 0 && jitter_mode == "uniform"
    delta = Random.rand((-jitter)..jitter)
    sleep_seconds = interval + delta
  end
  sleep_seconds = 1 if sleep_seconds < 1
  sleep sleep_seconds.seconds
end
