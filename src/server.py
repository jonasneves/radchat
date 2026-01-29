"""
Duke RadChat API Server - Flask backend for web interface
"""

import hashlib
import json
import os
import secrets
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from threading import Lock
from urllib.parse import urlencode

import requests
from flask import Flask, request, jsonify, Response, stream_with_context, redirect, session, send_from_directory, make_response

from dotenv import load_dotenv
load_dotenv()

from flask_cors import CORS

from .chat import create_chat, RadChat, get_available_models

STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR))

# Session configuration
SESSION_MAX_SIZE = 100  # Maximum sessions to keep
SESSION_TTL = 3600  # Session TTL in seconds (1 hour)


def get_file_hash(filepath: Path) -> str:
    """Generate a short hash of file contents for cache busting."""
    if not filepath.exists():
        return "0"
    content = filepath.read_bytes()
    return hashlib.md5(content).hexdigest()[:8]


# Cache file hashes (recomputed on each server start)
_file_hashes: dict[str, str] = {}


def get_static_hash(filename: str) -> str:
    """Get cached hash for a static file."""
    # In debug mode, always recompute hashes
    if app.debug or filename not in _file_hashes:
        _file_hashes[filename] = get_file_hash(STATIC_DIR / filename)
    return _file_hashes[filename]


app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
CORS(app, supports_credentials=True)

# Duke OIDC settings
DUKE_CLIENT_ID = os.environ.get("DUKE_CLIENT_ID", "radchat")
DUKE_CLIENT_SECRET = os.environ.get("DUKE_CLIENT_SECRET")
DUKE_OAUTH_URL = "https://oauth.oit.duke.edu/oidc/authorize"
DUKE_TOKEN_URL = "https://oauth.oit.duke.edu/oidc/token"
DUKE_USERINFO_URL = "https://oauth.oit.duke.edu/oidc/userinfo"

# Session storage with TTL eviction (in production, use Redis or similar)
class SessionStore:
    """LRU session store with TTL eviction."""

    def __init__(self, max_size: int = SESSION_MAX_SIZE, ttl: int = SESSION_TTL):
        self._sessions: OrderedDict[str, tuple[RadChat, float]] = OrderedDict()
        self._lock = Lock()
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key: str) -> RadChat | None:
        with self._lock:
            if key in self._sessions:
                chat, created_at = self._sessions[key]
                if time.time() - created_at < self._ttl:
                    # Move to end (most recently used)
                    self._sessions.move_to_end(key)
                    return chat
                # Expired, remove it
                del self._sessions[key]
            return None

    def set(self, key: str, chat: RadChat) -> None:
        with self._lock:
            # Evict oldest if at capacity
            while len(self._sessions) >= self._max_size:
                self._sessions.popitem(last=False)
            self._sessions[key] = (chat, time.time())

    def delete_prefix(self, prefix: str) -> int:
        """Delete all sessions matching prefix. Returns count deleted."""
        with self._lock:
            keys_to_delete = [k for k in self._sessions if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._sessions[key]
            return len(keys_to_delete)


sessions = SessionStore()


def get_session(session_id: str, token: str = None, model: str = None) -> RadChat:
    """Get or create a chat session."""
    # Determine provider type based on model
    provider_type = "anthropic" if model and model.startswith("claude-") else "github"
    key = f"{session_id}:{model or 'default'}"

    chat = sessions.get(key)
    if chat is None:
        chat = create_chat(
            provider_type=provider_type,
            model=model or "openai/gpt-4.1-mini",
            token=token,
        )
        sessions.set(key, chat)
    return chat


def _render_index_html() -> str:
    """Render index.html with cache-busted URLs."""
    html_path = STATIC_DIR / "index.html"
    html = html_path.read_text()

    # Inject version hashes for cache busting
    css_hash = get_static_hash("styles.css")
    app_hash = get_static_hash("app.js")
    marked_hash = get_static_hash("marked.min.js")

    html = html.replace('href="/static/styles.css"', f'href="/static/styles.css?v={css_hash}"')
    html = html.replace('src="/static/app.js"', f'src="/static/app.js?v={app_hash}"')
    html = html.replace('src="/static/marked.min.js"', f'src="/static/marked.min.js?v={marked_hash}"')

    return html


# Cached rendered HTML (cleared on debug mode)
_cached_html: str | None = None


@app.route("/")
def index():
    """Serve the web UI with cache-busted static file URLs."""
    global _cached_html

    # In debug mode, always re-render; otherwise use cache
    if app.debug or _cached_html is None:
        _cached_html = _render_index_html()

    response = make_response(_cached_html)
    response.headers["Content-Type"] = "text/html"
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@app.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files with cache headers."""
    response = make_response(send_from_directory(STATIC_DIR, filename))
    # If version query param is present, cache for 1 year (immutable)
    if request.args.get("v"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "public, max-age=3600"
    return response


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

    try:
        chat_session = get_session(session_id, token, model)
    except Exception as e:
        return jsonify({"error": f"Failed to create session: {str(e)}"}), 500

    def generate():
        try:
            for chunk in chat_session.chat_stream(message):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_msg = str(e)
            if "rate" in error_msg.lower() or "too many" in error_msg.lower():
                yield f"data: {json.dumps({'error': 'Rate limit exceeded. Please wait a moment and try again.'})}\n\n"
            else:
                yield f"data: {json.dumps({'error': error_msg})}\n\n"
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
    """Clear all chat sessions for a given session ID."""
    prefix = f"{session_id}:"
    count = sessions.delete_prefix(prefix)
    return jsonify({"status": "cleared", "session_id": session_id, "cleared": count})


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

    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "true").lower() == "true"

    # Suppress default Flask startup banner
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)

    print(f" * Running on http://localhost:{port}")
    print(" * Press CTRL+C to quit")
    if debug:
        print(" * Debug mode: on")

    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    main()
