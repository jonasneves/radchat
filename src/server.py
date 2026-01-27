"""
Duke RadChat API Server - Flask backend for web interface
"""

import json
import os
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS

from .chat import create_chat, RadChat

app = Flask(__name__)
CORS(app)

# Session storage (in production, use Redis or similar)
sessions: dict[str, RadChat] = {}


def get_session(session_id: str) -> RadChat:
    """Get or create a chat session."""
    if session_id not in sessions:
        sessions[session_id] = create_chat()
    return sessions[session_id]


@app.route("/")
@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "duke-radchat"})


@app.route("/chat", methods=["POST"])
def chat():
    """
    Send a message and get a response.

    Request: {"message": "...", "session_id": "..."}
    Response: {"response": "...", "session_id": "..."}
    """
    data = request.json or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    chat_session = get_session(session_id)
    response = chat_session.chat(message)

    return jsonify({
        "response": response,
        "session_id": session_id,
    })


@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    """
    Stream a response token by token.

    Request: {"message": "...", "session_id": "..."}
    Response: Server-Sent Events stream
    """
    data = request.json or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    chat_session = get_session(session_id)

    def generate():
        for chunk in chat_session.chat_stream(message):
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/sessions/<session_id>", methods=["DELETE"])
def clear_session(session_id: str):
    """Clear a chat session."""
    if session_id in sessions:
        del sessions[session_id]
    return jsonify({"status": "cleared", "session_id": session_id})


@app.route("/tools", methods=["GET"])
def list_tools():
    """List available tools."""
    from .tools.phone_catalog import PHONE_CATALOG_TOOLS
    from .tools.acr_criteria import ACR_CRITERIA_TOOLS

    return jsonify({
        "phone_catalog": [t["name"] for t in PHONE_CATALOG_TOOLS],
        "acr_criteria": [t["name"] for t in ACR_CRITERIA_TOOLS],
    })


def main():
    """Run the server."""
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
