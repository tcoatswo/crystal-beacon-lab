from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)


@app.post("/ingest")
def ingest():
    data = request.get_json(force=True, silent=True) or {}
    # For a real deployment, validate schema + auth. This is a local lab collector.
    received_at = datetime.utcnow().isoformat() + "Z"
    return jsonify({"ok": True, "received_at": received_at, "echo": data}), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
