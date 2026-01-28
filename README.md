# RadChat

Radiology assistant with phone directory lookup and ACR imaging criteria. Uses GitHub Models API and Duke NetID authentication.

## Setup

```bash
make install
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `GH_MODELS_TOKEN` | Yes | GitHub token for Models API |
| `DUKE_CLIENT_ID` | Yes | Duke OAuth client ID |
| `DUKE_CLIENT_SECRET` | Yes | Duke OAuth client secret |
| `ANTHROPIC_API_KEY` | No | Enables Claude Sonnet/Opus models |
| `FLASK_SECRET_KEY` | Yes | Session encryption (generate with `openssl rand -hex 32`) |

## Development

```bash
make preview        # Local server (port 5000)
make preview-remote # Local + ngrok tunnel
```

## Tools

| Tool | Description |
|------|-------------|
| Phone Directory | Reading rooms, scheduling, procedures |
| ACR Criteria | Imaging appropriateness scores (1-9) |

## Deploy

GitHub Actions with Cloudflare Tunnel.

| Secret | Required | Description |
|--------|----------|-------------|
| `GH_MODELS_TOKEN` | Yes | GitHub token (Models API + repo for auto-restart) |
| `DUKE_CLIENT_SECRET` | Yes | Duke OAuth client secret |
| `FLASK_SECRET_KEY` | Yes | Session encryption key |
| `TUNNEL_TOKEN` | Yes | Cloudflare tunnel token |
| `ANTHROPIC_API_KEY` | No | Enables Claude models |

Trigger: Actions → Deploy → Run workflow
