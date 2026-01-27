"""
Duke RadChat API Server - Flask backend for web interface
"""

import json
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Flask, request, jsonify, Response, stream_with_context, redirect, session

from dotenv import load_dotenv
load_dotenv()

from flask_cors import CORS

from .chat import create_chat, RadChat, get_available_models

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
CORS(app, supports_credentials=True)

# GitHub OAuth settings
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")
GITHUB_OAUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"

# Session storage (in production, use Redis or similar)
sessions: dict[str, RadChat] = {}


def get_session(session_id: str, token: str = None, model: str = None) -> RadChat:
    """Get or create a chat session."""
    key = f"{session_id}:{token or 'default'}"
    if key not in sessions:
        sessions[key] = create_chat(
            provider_type="github",
            model=model or "openai/gpt-4o-mini",
            token=token,
        )
    return sessions[key]


@app.route("/")
@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "duke-radchat"})


@app.route("/models", methods=["GET"])
def list_models():
    """List available models with function calling support."""
    return jsonify({"models": get_available_models()})


@app.route("/auth/github")
def github_auth():
    """Initiate GitHub OAuth flow."""
    if not GITHUB_CLIENT_ID:
        return jsonify({"error": "GitHub OAuth not configured"}), 500

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "scope": "read:user",
        "state": state,
        "redirect_uri": request.url_root.rstrip("/") + "/auth/callback",
    }

    return redirect(f"{GITHUB_OAUTH_URL}?{urlencode(params)}")


@app.route("/auth/callback")
def github_callback():
    """Handle GitHub OAuth callback."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        return jsonify({"error": "GitHub OAuth not configured"}), 500

    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return jsonify({"error": "No code provided"}), 400

    if state != session.get("oauth_state"):
        return jsonify({"error": "Invalid state"}), 400

    # Exchange code for token
    response = requests.post(
        GITHUB_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
        },
        timeout=30,
    )

    if response.status_code != 200:
        return jsonify({"error": "Failed to get token"}), 500

    data = response.json()
    access_token = data.get("access_token")

    if not access_token:
        return jsonify({"error": data.get("error_description", "No token received")}), 400

    session["github_token"] = access_token
    session.pop("oauth_state", None)

    # Return HTML that posts token to parent window (for popup auth)
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Authentication Complete</title></head>
    <body>
        <script>
            if (window.opener) {
                window.opener.postMessage({type: 'github_auth', success: true}, '*');
                window.close();
            } else {
                window.location.href = '/';
            }
        </script>
        <p>Authentication successful. You can close this window.</p>
    </body>
    </html>
    """


@app.route("/auth/status")
def auth_status():
    """Check authentication status."""
    token = session.get("github_token")
    return jsonify({
        "authenticated": bool(token),
        "oauth_configured": bool(GITHUB_CLIENT_ID),
    })


@app.route("/auth/logout", methods=["POST"])
def logout():
    """Clear authentication."""
    session.pop("github_token", None)
    return jsonify({"status": "logged_out"})


@app.route("/chat", methods=["POST"])
def chat():
    """
    Send a message and get a response.

    Request: {"message": "...", "session_id": "...", "model": "..."}
    Response: {"response": "...", "session_id": "..."}
    """
    data = request.json or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    model = data.get("model")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    # Get token from session or request header
    token = session.get("github_token") or request.headers.get("X-GitHub-Token")
    if not token:
        token = os.environ.get("GITHUB_TOKEN")

    if not token:
        return jsonify({"error": "Authentication required. Use /auth/github to login."}), 401

    chat_session = get_session(session_id, token, model)
    response = chat_session.chat(message)

    return jsonify({
        "response": response,
        "session_id": session_id,
    })


@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    """
    Stream a response token by token.

    Request: {"message": "...", "session_id": "...", "model": "..."}
    Response: Server-Sent Events stream
    """
    data = request.json or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    model = data.get("model")

    if not message:
        return jsonify({"error": "Message is required"}), 400

    token = session.get("github_token") or request.headers.get("X-GitHub-Token")
    if not token:
        token = os.environ.get("GITHUB_TOKEN")

    if not token:
        return jsonify({"error": "Authentication required"}), 401

    chat_session = get_session(session_id, token, model)

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
    token = session.get("github_token") or request.headers.get("X-GitHub-Token")
    key = f"{session_id}:{token or 'default'}"
    if key in sessions:
        del sessions[key]
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
