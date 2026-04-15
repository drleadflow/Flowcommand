# Dr. Lead Flow | Mission Control

Real-time AI agent orchestration dashboard with voice integration.

## Architecture

```
┌─────────────┐     WebSocket      ┌──────────────┐     Subprocess     ┌─────────────┐
│   Frontend  │◄──────────────────►│   Backend    │◄─────────────────►│  OpenClaw   │
│  (Kanban)   │                    │   Server     │                   │   Agents    │
└─────────────┘                    └──────────────┘                   └─────────────┘
                                         │
                                         │ REST API
                                         ▼
                                  ┌──────────────┐
                                  │ LiveKit Room │
                                  │   (Voice)    │
                                  └──────────────┘
```

## Deployment to Railway

1. **Push to GitHub:**
```bash
cd ~/drleadflow-mission-control
git init
git add .
git commit -m "Initial Mission Control"
git remote add origin https://github.com/YOUR_USERNAME/drleadflow-mission-control.git
git push -u origin main
```

2. **Connect Railway:**
- Go to [railway.app](https://railway.app)
- New Project → Deploy from GitHub repo
- Select `drleadflow-mission-control`
- Railway auto-detects `railway.yaml`

3. **Environment Variables:**
Already configured in `railway.yaml`, but you can override in Railway dashboard:
- `LIVEKIT_URL` - Your LiveKit Cloud URL
- `LIVEKIT_API_KEY` - LiveKit API key
- `LIVEKIT_API_SECRET` - LiveKit API secret
- `CARTESIA_API_KEY` - Cartesia API key

4. **Deploy:**
Railway auto-deploys on every push.

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start backend
python backend/server.py

# Start frontend (separate terminal)
cd frontend
python3 -m http.server 3000

# Open http://localhost:3000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/api/health` | System status |
| POST | `/api/voice/room` | Create voice room |
| WS | `/api/voice/ws/{agent}` | Voice WebSocket |
| WS | `ws://host:8765` | Dashboard WebSocket |

## Agents

| Agent | Lane | Voice | Role |
|-------|------|-------|------|
| main | MAIN | Default | Coordinator |
| gary | COMMS | Calm male | Email/Outreach |
| patty | CONTENT | Warm female | Content/YouTube |
| blaze | OPS | Energetic male | Ads/Operations |
| ron | RESEARCH | Analytical male | Research/SEO |
| codey | ENGINEERING | Precise male | Code/Automation |

## Voice Pipeline

- **LiveKit** - WebRTC rooms for real-time audio
- **Cartesia** - Text-to-speech with distinct agent voices
- **Deepgram** - Speech-to-text (optional, STT can be client-side)

## License
MIT
