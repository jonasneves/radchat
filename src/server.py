"""
Duke RadChat API Server - Flask backend for web interface
"""

import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import Flask, request, jsonify, Response, stream_with_context, redirect, session, send_from_directory

from dotenv import load_dotenv
load_dotenv()

from flask_cors import CORS

from .chat import create_chat, RadChat, get_available_models

STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
CORS(app, supports_credentials=True)

# Duke OIDC settings
DUKE_CLIENT_ID = os.environ.get("DUKE_CLIENT_ID", "radchat")
DUKE_CLIENT_SECRET = os.environ.get("DUKE_CLIENT_SECRET")
DUKE_OAUTH_URL = "https://oauth.oit.duke.edu/oidc/authorize"
DUKE_TOKEN_URL = "https://oauth.oit.duke.edu/oidc/token"
DUKE_USERINFO_URL = "https://oauth.oit.duke.edu/oidc/userinfo"

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
def index():
    """Serve the web UI."""
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files."""
    return send_from_directory(STATIC_DIR, filename)


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "duke-radchat"})


@app.route("/models", methods=["GET"])
def list_models():
    """List available models with function calling support."""
    return jsonify({"models": get_available_models()})


@app.route("/auth/duke")
def duke_auth():
    """Initiate Duke OIDC flow."""
    if not DUKE_CLIENT_SECRET:
        return jsonify({"error": "Duke OAuth not configured"}), 500

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = {
        "client_id": DUKE_CLIENT_ID,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "redirect_uri": request.url_root.rstrip("/") + "/auth/callback",
    }

    return redirect(f"{DUKE_OAUTH_URL}?{urlencode(params)}")


@app.route("/auth/callback")
def duke_callback():
    """Handle Duke OIDC callback."""
    if not DUKE_CLIENT_SECRET:
        return jsonify({"error": "Duke OAuth not configured"}), 500

    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        return jsonify({"error": request.args.get("error_description", error)}), 400

    if not code:
        return jsonify({"error": "No code provided"}), 400

    if state != session.get("oauth_state"):
        return jsonify({"error": "Invalid state"}), 400

    # Exchange code for token
    redirect_uri = request.url_root.rstrip("/") + "/auth/callback"
    response = requests.post(
        DUKE_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "client_id": DUKE_CLIENT_ID,
            "client_secret": DUKE_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )

    if response.status_code != 200:
        return jsonify({"error": "Failed to get token", "details": response.text}), 500

    data = response.json()
    access_token = data.get("access_token")
    id_token = data.get("id_token")

    if not access_token:
        return jsonify({"error": data.get("error_description", "No token received")}), 400

    # Get user info
    userinfo_response = requests.get(
        DUKE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )

    user_info = {}
    if userinfo_response.status_code == 200:
        user_info = userinfo_response.json()

    session["duke_token"] = access_token
    session["duke_user"] = user_info
    session.pop("oauth_state", None)

    # Return HTML that posts token to parent window (for popup auth)
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Authentication Complete</title></head>
    <body>
        <script>
            if (window.opener) {
                window.opener.postMessage({type: 'duke_auth', success: true}, '*');
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
    token = session.get("duke_token")
    user = session.get("duke_user", {})
    return jsonify({
        "authenticated": bool(token),
        "oauth_configured": bool(DUKE_CLIENT_SECRET),
        "user": {
            "name": user.get("name"),
            "email": user.get("email"),
            "netid": user.get("dukeNetID"),
        } if token else None,
    })


@app.route("/auth/logout", methods=["POST"])
def logout():
    """Clear authentication."""
    session.pop("duke_token", None)
    session.pop("duke_user", None)
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

    # Get GitHub token for API access (from env or header)
    token = os.environ.get("GH_MODELS_TOKEN") or request.headers.get("X-GitHub-Token")

    if not token:
        return jsonify({"error": "GitHub token not configured. Set GH_MODELS_TOKEN environment variable."}), 401

    # Check Duke auth for user access control
    if not session.get("duke_token"):
        return jsonify({"error": "Authentication required. Use /auth/duke to login."}), 401

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

    # Get GitHub token for API access (from env or header)
    token = os.environ.get("GH_MODELS_TOKEN") or request.headers.get("X-GitHub-Token")

    if not token:
        return jsonify({"error": "GitHub token not configured"}), 401

    # Check Duke auth for user access control
    if not session.get("duke_token"):
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
    token = os.environ.get("GH_MODELS_TOKEN") or request.headers.get("X-GitHub-Token")
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
    import logging
    import click

    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "true").lower() == "true"

    # Suppress default Flask startup banner
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    click.disable_unicode_literals_warning = True

    print(f" * Running on http://localhost:{port}")
    print(" * Press CTRL+C to quit")
    if debug:
        print(" * Debug mode: on")

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
