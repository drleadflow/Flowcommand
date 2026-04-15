#!/usr/bin/env python3
"""
Voice Pipeline Integration
LiveKit + Cartesia + Deepgram for real-time voice conversations
"""

import asyncio
import json
import os
from typing import Optional
from dataclasses import dataclass
import websockets

@dataclass
class VoiceConfig:
    livekit_url: str = "wss://superagent-9p7whlmp.livekit.cloud"
    livekit_api_key: str = "APIE5hYXHSRRZ3b"
    livekit_api_secret: str = "6ZnyXZcUofNpjna6guMUD8etSfokwSnlwy4LYIuptjCA"
    cartesia_api_key: str = "sk_car_8VuTGjSecSF1MhsS35o2u4"
    deepgram_api_key: Optional[str] = None

class VoicePipeline:
    """Real-time voice conversation handler."""
    
    def __init__(self, config: VoiceConfig = None):
        self.config = config or VoiceConfig()
        self.active_sessions: dict = {}
        
    async def create_room(self, agent_name: str = "main") -> dict:
        """Create a LiveKit room for voice session."""
        import jwt
        import time
        
        # Generate LiveKit token
        token_payload = {
            "exp": int(time.time()) + 3600,
            "iss": self.config.livekit_api_key,
            "nbf": int(time.time()) - 10,
            "sub": "drleadflow_voice",
            "video": {"roomJoin": True, "room": f"mission-control-{agent_name}"},
            "metadata": json.dumps({"agent": agent_name})
        }
        
        token = jwt.encode(
            token_payload,
            self.config.livekit_api_secret,
            algorithm="HS256"
        )
        
        room_url = f"{self.config.livekit_url}?token={token}"
        
        return {
            "room_url": room_url,
            "token": token,
            "agent": agent_name,
            "expires_in": 3600
        }
    
    async def text_to_speech(self, text: str, voice_id: str = "agent_001") -> bytes:
        """Convert text to speech using Cartesia."""
        import aiohttp
        
        url = "https://api.cartesia.ai/tts/bytes"
        headers = {
            "Cartesia-Version": "2024-06-10",
            "X-API-Key": self.config.cartesia_api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "transcript": text,
            "model_id": "sonic-english",
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {"container": "mp3", "encoding": "mp3", "sample_rate": 44100}
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    error = await resp.text()
                    raise Exception(f"TTS failed: {error}")
    
    async def stream_tts(self, text: str, websocket, voice_id: str = "agent_001"):
        """Stream TTS audio chunks."""
        audio = await self.text_to_speech(text, voice_id)
        await websocket.send(json.dumps({
            "type": "audio",
            "data": audio.hex()
        }))

class VoiceAgentBridge:
    """Bridge between voice input and OpenClaw agents."""
    
    AGENT_VOICES = {
        "main": "79a125e8-cd45-4c13-8a67-188112f4c226",
        "gary": "21m00Tcm4TlvDq8ikWAM",  # Calm male
        "patty": "XB0fDUnXU5powFXDhCwa",  # Warm female  
        "blaze": "CwhRBWXzGAHq8TQ4Fs17",  # Energetic male
        "ron": "AZnzlk1XvdvUeBnXmlld",    # Analytical male
        "codey": "MF3mGyEYCl7XYWbV9V6O"   # Precise male
    }
    
    def __init__(self):
        self.pipeline = VoicePipeline()
        self.router = AgentVoiceRouter()
        
    async def handle_voice_session(self, websocket, room_info: dict):
        """Handle a complete voice session."""
        session_id = room_info.get("agent", "main")
        
        try:
            async for message in websocket:
                data = json.loads(message)
                
                if data.get("type") == "transcript":
                    # Got speech-to-text result
                    transcript = data.get("text", "")
                    
                    # Route to appropriate agent
                    agent_key = self.router.route(transcript)
                    voice_id = self.AGENT_VOICES.get(agent_key, self.AGENT_VOICES["main"])
                    
                    # Delegate to OpenClaw
                    result = await self.delegate_to_agent(agent_key, transcript)
                    
                    # Convert response to speech
                    if result:
                        await self.pipeline.stream_tts(result, websocket, voice_id)
                        
        except websockets.exceptions.ConnectionClosed:
            pass
    
    async def delegate_to_agent(self, agent_key: str, task: str) -> str:
        """Send task to OpenClaw agent."""
        import subprocess
        
        delegate_script = os.path.expanduser("~/scripts/openclaw_delegate.py")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", delegate_script,
                "--agent", agent_key,
                task,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            
            result = stdout.decode() if stdout else stderr.decode()
            
            # Parse JSON result
            try:
                json_result = json.loads(result)
                if "payloads" in json_result and len(json_result["payloads"]) > 0:
                    return json_result["payloads"][0].get("text", result)
            except:
                pass
            
            return result[:500] if len(result) > 500 else result
            
        except Exception as e:
            return f"Error: {str(e)}"

class AgentVoiceRouter:
    """Route voice commands to appropriate agent."""
    
    def route(self, text: str) -> str:
        """Determine which agent should handle this."""
        text_lower = text.lower()
        
        # Check for direct agent names
        if any(name in text_lower for name in ["gary", "comms", "email", "outreach"]):
            return "gary"
        elif any(name in text_lower for name in ["patty", "content", "youtube", "social"]):
            return "patty"
        elif any(name in text_lower for name in ["blaze", "ops", "ads", "meta", "campaign"]):
            return "blaze"
        elif any(name in text_lower for name in ["ron", "research", "analysis", "competitor"]):
            return "ron"
        elif any(name in text_lower for name in ["codey", "code", "build", "automation"]):
            return "codey"
        elif "everyone" in text_lower or "all agents" in text_lower:
            return "main"  # Broadcast
        else:
            return "main"