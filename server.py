
import asyncio
import sys
import os
import json
from pathlib import Path
from typing import List, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add project root to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.loop import AgentLoop4
from mcp_servers.multi_mcp import MultiMCP
from core.utils import set_event_callback

app = FastAPI(title="SamyakAgent API")

# Allow CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── WebSocket Manager ───────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Convert to JSON string once
        text = json.dumps(message, default=str)
        for connection in self.active_connections:
            try:
                await connection.send_text(text)
            except Exception:
                pass # Handle disconnected clients gracefully

manager = ConnectionManager()

# ─── Global State ───────────────────────────────────────────────────

class GlobalState:
    agent_loop: AgentLoop4 = None
    multi_mcp: MultiMCP = None
    is_running: bool = False

state = GlobalState()

# ─── Event Callback ─────────────────────────────────────────────────

def handle_backend_event(event_type: str, data: dict):
    """Bridge backend events to WebSockets"""
    # We need to schedule this on the event loop
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": event_type, "data": data}),
                loop
            )
    except RuntimeError:
        pass # No event loop running

# Register callback
set_event_callback(handle_backend_event)

# ─── Startup/Shutdown ──────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    print("🚀 Starting SamyakAgent Backend...")
    state.multi_mcp = MultiMCP()
    await state.multi_mcp.start()
    
    state.agent_loop = AgentLoop4(multi_mcp=state.multi_mcp)

@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 Shutting down...")
    if state.multi_mcp:
        await state.multi_mcp.stop()

# ─── API Endpoints ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str

@app.get("/health")
async def health_check():
    return {"status": "ok", "agent_ready": state.agent_loop is not None}

@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We just keep the connection open to listen
            # Currently frontend doesn't send messages here, just receives
            data = await websocket.receive_text()
            # Optional: handle ping/pong
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def run_agent_task(query: str):
    """Background task to run the agent loop"""
    if state.is_running:
        await manager.broadcast({"type": "error", "data": {"message": "Agent already running"}})
        return

    state.is_running = True
    await manager.broadcast({"type": "status", "data": {"status": "running"}})
    
    try:
        # Run the agent loop
        context = await state.agent_loop.run(
            query=query,
            file_manifest=[],
            globals_schema={},
            uploaded_files=[]
        )
        
        # Extract final answer
        summary = context.get_execution_summary()
        final_answer = summary.get("final_outputs", "No final output found.")
        
        await manager.broadcast({
            "type": "finish", 
            "data": {
                "success": True, 
                "output": final_answer
            }
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        await manager.broadcast({
            "type": "finish", 
            "data": {
                "success": False, 
                "error": str(e)
            }
        })
    finally:
        state.is_running = False
        await manager.broadcast({"type": "status", "data": {"status": "idle"}})

@app.post("/api/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    if state.is_running:
        return {"status": "error", "message": "Agent is busy"}
    
    background_tasks.add_task(run_agent_task, request.message)
    return {"status": "accepted", "message": "Agent started"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
