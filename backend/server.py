#!/usr/bin/env python3
"""
Dr. Lead Flow Mission Control Server
Real-time WebSocket dashboard for agent orchestration + Voice Integration
"""

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from aiohttp import web
import aiohttp_cors
import websockets
from websockets.server import WebSocketServerProtocol

from voice_pipeline import VoicePipeline, VoiceAgentBridge, VoiceConfig

# Paths
AGENTS_CONFIG = Path.home() / ".hermes" / "openclaw_agents.yaml"
DELEGATE_SCRIPT = Path.home() / "scripts" / "openclaw_delegate.py"

# In-memory state
connected_clients: set = set()
active_tasks: Dict[str, dict] = {}
task_history: List[dict] = []
system_stats = {
    "total_tasks": 0,
    "tokens_today": 0,
    "tokens_lifetime": 0,
    "start_time": datetime.now().isoformat()
}

# Agent mapping to lane names
AGENT_LANES = {
    "main": "MAIN",
    "gary": "COMMS",
    "patty": "CONTENT", 
    "blaze": "OPS",
    "ron": "RESEARCH",
    "codey": "ENGINEERING"
}


def load_agents_config() -> Dict:
    """Load agent registry from YAML."""
    if not AGENTS_CONFIG.exists():
        return {"agents": {}}
    with open(AGENTS_CONFIG, 'r') as f:
        return yaml.safe_load(f)


async def broadcast(message: dict):
    """Broadcast message to all connected clients."""
    if connected_clients:
        msg = json.dumps(message)
        await asyncio.gather(
            *[client.send(msg) for client in connected_clients],
            return_exceptions=True
        )


async def delegate_task(agent_key: str, task: str, context: str = "") -> dict:
    """Delegate task to OpenClaw agent and track it."""
    task_id = f"{agent_key}_{datetime.now().strftime('%H%M%S%f')}"
    
    # Create task record
    task_record = {
        "id": task_id,
        "agent": agent_key,
        "lane": AGENT_LANES.get(agent_key, "MAIN"),
        "task": task,
        "context": context,
        "status": "running",
        "start_time": datetime.now().isoformat(),
        "duration": 0,
        "result": None
    }
    
    active_tasks[task_id] = task_record
    system_stats["total_tasks"] += 1
    
    # Broadcast task started
    await broadcast({
        "type": "task_started",
        "task": task_record
    })
    
    # Run delegation
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", str(DELEGATE_SCRIPT),
            "--agent", agent_key,
            task,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=300
        )
        
        end_time = datetime.now()
        start = datetime.fromisoformat(task_record["start_time"])
        duration = (end_time - start).total_seconds()
        
        result = stdout.decode() if stdout else stderr.decode()
        
        task_record["status"] = "done"
        task_record["duration"] = duration
        task_record["result"] = result[:500] if len(result) > 500 else result
        task_record["end_time"] = end_time.isoformat()
        
        # Move to history
        task_history.append(task_record)
        del active_tasks[task_id]
        
        # Broadcast completion
        await broadcast({
            "type": "task_completed",
            "task": task_record
        })
        
        return task_record
        
    except asyncio.TimeoutError:
        task_record["status"] = "error"
        task_record["error"] = "Timeout"
        await broadcast({"type": "task_error", "task": task_record})
        return task_record
    except Exception as e:
        task_record["status"] = "error"
        task_record["error"] = str(e)
        await broadcast({"type": "task_error", "task": task_record})
        return task_record


async def route_message(message: str) -> str:
    """Route message to appropriate agent based on keywords."""
    msg_lower = message.lower()
    
    # Check for agent name mentions
    if any(x in msg_lower for x in ["gary", "email", "copy", "outreach", "comms"]):
        return "gary"
    elif any(x in msg_lower for x in ["patty", "content", "youtube", "script", "social", "video"]):
        return "patty"
    elif any(x in msg_lower for x in ["blaze", "ads", "meta", "campaign", "roas", "facebook"]):
        return "blaze"
    elif any(x in msg_lower for x in ["ron", "research", "analysis", "competitor", "seo", "audit"]):
        return "ron"
    elif any(x in msg_lower for x in ["codey", "code", "build", "script", "automation", "api"]):
        return "codey"
    else:
        return "main"


async def handle_client(websocket: WebSocketServerProtocol, path: str):
    """Handle WebSocket client connection."""
    connected_clients.add(websocket)
    print(f"Client connected. Total: {len(connected_clients)}")
    
    # Send initial state
    config = load_agents_config()
    await websocket.send(json.dumps({
        "type": "init",
        "agents": config.get("agents", {}),
        "active_tasks": list(active_tasks.values()),
        "task_history": task_history[-20:],  # Last 20
        "system_stats": system_stats,
        "lanes": AGENT_LANES
    }))
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "delegate":
                    agent = data.get("agent")
                    task = data.get("task")
                    context = data.get("context", "")
                    
                    if not agent:
                        # Auto-route based on task content
                        agent = await route_message(task)
                    
                    # Start delegation in background
                    asyncio.create_task(delegate_task(agent, task, context))
                    
                elif msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                    
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON"
                }))
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)
        print(f"Client disconnected. Total: {len(connected_clients)}")


# Initialize voice system
voice_bridge = VoiceAgentBridge()

async def http_handler(request):
    """Handle HTTP requests for health checks."""
    return web.Response(
        text=json.dumps({
            "status": "ok",
            "version": "1.0.0",
            "agents": list(AGENT_LANES.keys()),
            "active_tasks": len(active_tasks),
            "connected_clients": len(connected_clients),
            "system_stats": system_stats
        }),
        content_type="application/json"
    )

async def voice_room_handler(request):
    """Create a voice room for agent."""
    data = await request.json()
    agent = data.get("agent", "main")
    
    try:
        room_info = await voice_bridge.pipeline.create_room(agent)
        return web.json_response({
            "success": True,
            "room_url": room_info["room_url"],
            "token": room_info["token"],
            "agent": agent
        })
    except Exception as e:
        return web.json_response({
            "success": False,
            "error": str(e)
        }, status=500)

async def voice_websocket_handler(request):
    """WebSocket handler for voice sessions."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    room_info = {
        "agent": request.match_info.get("agent", "main"),
        "session_id": datetime.now().isoformat()
    }
    
    await voice_bridge.handle_voice_session(ws, room_info)
    return ws

async def run_http_server(port: int = 8080):
    """Run HTTP server for REST API."""
    app = web.Application()
    
    # CORS setup
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # Routes
    app.router.add_get("/", http_handler)
    app.router.add_get("/api/health", http_handler)
    app.router.add_post("/api/voice/room", voice_room_handler)
    app.router.add_get("/api/voice/ws/{agent}", voice_websocket_handler)
    
    # Add CORS to all routes
    for route in list(app.router.routes()):
        cors.add(route)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    
    print(f"HTTP API running on http://0.0.0.0:{port}")
    await site.start()

async def main():
    """Start both WebSocket and HTTP servers."""
    from aiohttp import web
    
    # Railway provides PORT env var - must use it
    port = int(os.environ.get("PORT", 8080))
    
    ws_host = os.environ.get("WS_HOST", "0.0.0.0")
    ws_port = int(os.environ.get("WS_PORT", 8765))
    http_port = port  # Use Railway's PORT for HTTP
    
    print(f"Starting Mission Control servers:")
    print(f"  WebSocket: ws://{ws_host}:{ws_port}")
    print(f"  HTTP API:  http://0.0.0.0:{http_port}")
    
    # Run both servers
    await asyncio.gather(
        run_http_server(http_port),
        websockets.serve(handle_client, ws_host, ws_port),
        return_exceptions=True
    )


if __name__ == "__main__":
    asyncio.run(main())
