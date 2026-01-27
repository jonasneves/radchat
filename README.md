# RadChat

Radiology assistant with Claude tool calling for phone directory lookup and ACR imaging criteria.

## Setup

```bash
make install
export ANTHROPIC_API_KEY=your_key
```

## Usage

```bash
make cli      # Interactive chat
make server   # API server (port 5000)
```

## Tools

| Tool | Description |
|------|-------------|
| `search_phone_directory` | Find reading rooms, scheduling, procedures |
| `get_reading_room_contact` | Get contact for modality + body region |
| `get_procedure_contact` | VIR/procedure requests |
| `search_acr_criteria` | Imaging appropriateness by clinical scenario |
| `get_acr_topic_details` | Detailed appropriateness scores (1-9) |

## API

```bash
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "CT reading room number?"}'
```

## Deploy

Uses Cloudflare Tunnel via GitHub Actions. Set secrets:
- `ANTHROPIC_API_KEY`
- `TUNNEL_TOKEN` (from `make setup-tunnel`)
- `APP_ID` / `APP_PRIVATE_KEY` (for auto-restart)

Trigger: Actions → Deploy → Run workflow
