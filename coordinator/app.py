import asyncio
import json
from contextlib import asynccontextmanager
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import os

from coordinator.models import (
    NodeRegistration,
    BidSubmission,
    AuctionRound,
    BidOutcome,
    LeaderboardEntry
)
from coordinator.market import MarketEngine
from coordinator.competitors import create_default_competitors

market = MarketEngine()
competitors = create_default_competitors()
connected_websockets: List[WebSocket] = []

async def broadcast_event(event_type: str, data: Any):
    if not connected_websockets:
        return
    message = json.dumps({"type": event_type, "data": data})
    disconnected = []
    for ws in connected_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in connected_websockets:
            connected_websockets.remove(ws)

async def simulation_loop():
    """Background loop that executes auction rounds and simulates competitor bids."""
    # Register default competitor bots
    for comp in competitors:
        market.register_node(comp.get_registration())

    while True:
        if market.is_running:
            try:
                # 1. Open new auction round
                auction = market.create_auction_round()
                await broadcast_event("AUCTION_OPENED", auction.model_dump())

                # 2. Competitor bots calculate and submit bids
                for comp in competitors:
                    util = market.get_node_utilization(comp.node_id)
                    bid = comp.calculate_bid(auction.task, util)
                    if bid is not None:
                        sub = BidSubmission(
                            node_id=comp.node_id,
                            auction_id=auction.auction_id,
                            bid_price=bid
                        )
                        market.submit_bid(sub)
                        await broadcast_event("BID_RECEIVED", sub.model_dump())

                # 3. Wait for bids window
                duration = max(0.5, market.round_interval_sec / market.simulation_speed)
                await asyncio.sleep(duration)

                # 4. Clear auction and announce outcome
                outcome = market.clear_active_auction()
                if outcome:
                    for comp in competitors:
                        comp.record_outcome(outcome.clearing_price, outcome.winner_node_id == comp.node_id, outcome.bids)
                    await broadcast_event("AUCTION_CLEARED", {
                        "outcome": outcome.model_dump(),
                        "leaderboard": [lb.model_dump() for lb in market.get_leaderboard()],
                        "nodes_utilization": {
                            nid: market.get_node_utilization(nid) for nid in market.nodes.keys()
                        }
                    })

            except Exception as e:
                print(f"[Coordinator Loop Error] {e}")

        await asyncio.sleep(0.5 / market.simulation_speed)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background loop
    task = asyncio.create_task(simulation_loop())
    market.is_running = True
    yield
    market.is_running = False
    task.cancel()

app = FastAPI(
    title="CoGNETs Smart Edge Resource Auction Coordinator",
    description="Veles Hack 2026 Challenge 4 - Autonomous Edge Resource Scheduling & Auction Testbed",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    css_dir = os.path.join(static_dir, "css")
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    js_dir = os.path.join(static_dir, "js")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Smart Edge Resource Auctions Coordinator Running</h1><p>Visit /docs for API documentation.</p>")

@app.api_route("/documentation", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/docs.html", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def serve_documentation():
    docs_path = os.path.join(static_dir, "docs.html")
    if os.path.exists(docs_path):
        return FileResponse(docs_path)
    return HTMLResponse("<h1>Documentation</h1><p>Documentation file not found.</p>")

@app.api_route("/presentation.pdf", methods=["GET", "HEAD"])
async def serve_presentation():
    pdf_path = os.path.join(static_dir, "presentation.pdf")
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, media_type="application/pdf", filename="CognitiveSwarm_VelesHack_Presentation.pdf")
    return HTMLResponse("<h1>Presentation PDF Not Found</h1>", status_code=404)

@app.post("/api/v1/nodes/register", response_model=Dict[str, Any])
async def register_node(node: NodeRegistration):
    success = market.register_node(node)
    await broadcast_event("NODE_REGISTERED", node.model_dump())
    return {
        "status": "success",
        "message": f"Node {node.node_id} successfully registered with {node.cpu_cores} cores.",
        "node": node
    }

@app.get("/api/v1/nodes", response_model=Dict[str, Any])
async def list_nodes():
    return {
        "count": len(market.nodes),
        "nodes": list(market.nodes.values()),
        "telemetry": {nid: market.get_node_utilization(nid) for nid in market.nodes}
    }

@app.get("/api/v1/nodes/{node_id}/telemetry")
async def get_node_telemetry(node_id: str):
    if node_id not in market.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = market.nodes[node_id]
    util = market.get_node_utilization(node_id)
    return {
        "node": node,
        "utilization": util
    }

@app.get("/api/v1/auctions/active")
async def get_active_auction():
    if not market.active_auction or market.active_auction.status != "OPEN":
        return {"status": "NO_ACTIVE_AUCTION", "auction": None}
    return {
        "status": "ACTIVE",
        "auction": market.active_auction
    }

@app.post("/api/v1/auctions/{auction_id}/bid")
async def submit_bid(auction_id: str, bid: BidSubmission):
    if not market.active_auction or market.active_auction.auction_id != auction_id:
        raise HTTPException(status_code=400, detail="Auction not active or ID mismatch")
    
    if bid.node_id not in market.nodes:
        raise HTTPException(status_code=403, detail="Node must be registered before bidding")

    accepted = market.submit_bid(bid)
    if not accepted:
        raise HTTPException(status_code=400, detail="Bid rejected (auction might be closed)")

    await broadcast_event("BID_RECEIVED", {
        "auction_id": auction_id,
        "node_id": bid.node_id,
        "bid_price": bid.bid_price,
        "reasoning_trace": bid.reasoning_trace,
        "deliberation_steps": bid.deliberation_steps,
        "confidence": bid.confidence,
        "sponsor_telemetry": bid.sponsor_telemetry
    })
    return {"status": "BID_ACCEPTED", "auction_id": auction_id, "node_id": bid.node_id}

@app.get("/api/v1/auctions/history", response_model=List[BidOutcome])
async def get_history(limit: int = 50):
    return market.history[-limit:]

@app.get("/api/v1/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard():
    return market.get_leaderboard()

@app.post("/api/v1/simulation/start")
async def start_sim():
    market.is_running = True
    return {"status": "RUNNING"}

@app.post("/api/v1/simulation/pause")
async def pause_sim():
    market.is_running = False
    return {"status": "PAUSED"}

@app.post("/api/v1/simulation/speed")
async def set_speed(speed: float = 1.0):
    market.simulation_speed = max(0.2, min(5.0, speed))
    return {"status": "SPEED_UPDATED", "speed": market.simulation_speed}

@app.post("/api/v1/simulation/reset")
async def reset_sim():
    market.history.clear()
    market.round_counter = 0
    market.showcase_mode = False
    market.node_active_workloads = {nid: [] for nid in market.nodes}
    await broadcast_event("SIMULATION_RESET", {})
    return {"status": "RESET_COMPLETE"}

@app.get("/api/v1/config/groq/status")
async def get_groq_status():
    from agent.multi_agent.groq_reasoner import GroqReasoner
    r = GroqReasoner()
    return {
        "is_configured": r.is_configured,
        "model": r.model,
        "engine": "Groq Tensor Streaming Processor" if r.is_configured else "Deterministic Fallback Engine"
    }

@app.post("/api/v1/config/groq")
async def set_groq_config(req: Request):
    data = await req.json()
    key = data.get("api_key", "").strip()
    model = data.get("model", "llama-3.3-70b-versatile").strip()
    if not key or len(key) < 8:
        raise HTTPException(status_code=400, detail="Invalid Groq API key format.")
    
    os.environ["GROQ_API_KEY"] = key
    os.environ["GROQ_MODEL"] = model
    
    env_content = f"GROQ_API_KEY={key}\nGROQ_MODEL={model}\nGROQ_TIMEOUT_SEC=4.0\nSAMPLE_MODE=true\n"
    with open(".env", "w") as f:
        f.write(env_content)
    
    return {
        "status": "SUCCESS",
        "message": "Groq LPU active",
        "model": model,
        "is_configured": True
    }

@app.post("/api/v1/simulation/demo-preset")
async def launch_demo_preset():
    market.history.clear()
    market.round_counter = 0
    market.node_active_workloads = {nid: [] for nid in market.nodes}
    market.set_showcase_mode(True)
    market.simulation_speed = 1.0
    market.is_running = True
    await broadcast_event("SIMULATION_RESET", {})
    return {"status": "LIVE_MARKET_STARTED", "mode": "SHOWCASE_GOLDEN_DEMO"}

@app.websocket("/api/v1/ws/arena")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        # Send initial state
        init_payload = {
            "type": "INIT_STATE",
            "data": {
                "nodes": [n.model_dump() for n in market.nodes.values()],
                "leaderboard": [lb.model_dump() for lb in market.get_leaderboard()],
                "history": [h.model_dump() for h in market.history[-20:]],
                "active_auction": market.active_auction.model_dump() if market.active_auction else None,
                "is_running": market.is_running,
                "speed": market.simulation_speed
            }
        }
        await websocket.send_text(json.dumps(init_payload))
        while True:
            # Keepalive listener
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
    except Exception:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
