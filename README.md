# RadChat

Radiology assistant with phone directory lookup and ACR imaging criteria. Uses GitHub Models API and Duke NetID authentication.

## Setup

```bash
make install
cp .env.example .env
# Edit .env with your credentials
```

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

GitHub Actions with Cloudflare Tunnel. Required secrets:

| Secret | Description |
|--------|-------------|
| `GH_MODELS_TOKEN` | GitHub token (Models API + repo for auto-restart) |
| `DUKE_CLIENT_SECRET` | Duke OAuth client secret |
| `FLASK_SECRET_KEY` | Session encryption key |
| `TUNNEL_TOKEN` | Cloudflare tunnel token |

Trigger: Actions → Deploy → Run workflow
