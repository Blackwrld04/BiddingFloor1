import asyncio
from typing import Optional, List, Dict, Any
import httpx
from agent.models import AuctionSpec, BidResultSpec

class CoordinatorClient:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 4.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def register_node(self, registration_payload: Dict[str, Any]) -> bool:
        client = await self.get_client()
        try:
            resp = await client.post("/api/v1/nodes/register", json=registration_payload)
            return resp.status_code == 200
        except Exception as e:
            print(f"[Client] Registration failed: {e}")
            return False

    async def get_active_auction(self) -> Optional[AuctionSpec]:
        client = await self.get_client()
        try:
            resp = await client.get("/api/v1/auctions/active")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "ACTIVE" and data.get("auction"):
                    return AuctionSpec(**data["auction"])
            return None
        except Exception as e:
            print(f"[Client] Get active auction failed: {e}")
            return None

    async def submit_bid(
        self,
        auction_id: str,
        node_id: str,
        bid_price: float,
        reasoning_trace: Optional[str] = None,
        deliberation_steps: Optional[List[Dict[str, Any]]] = None,
        confidence: Optional[float] = None,
        sponsor_telemetry: Optional[Dict[str, Any]] = None
    ) -> bool:
        client = await self.get_client()
        payload = {
            "node_id": node_id,
            "auction_id": auction_id,
            "bid_price": bid_price,
            "reasoning_trace": reasoning_trace,
            "deliberation_steps": deliberation_steps,
            "confidence": confidence,
            "sponsor_telemetry": sponsor_telemetry
        }
        try:
            resp = await client.post(f"/api/v1/auctions/{auction_id}/bid", json=payload)
            return resp.status_code == 200
        except Exception as e:
            print(f"[Client] Bid submission failed for {auction_id}: {e}")
            return False

    async def get_recent_history(self, limit: int = 10) -> List[BidResultSpec]:
        client = await self.get_client()
        try:
            resp = await client.get(f"/api/v1/auctions/history?limit={limit}")
            if resp.status_code == 200:
                return [BidResultSpec(**item) for item in resp.json()]
            return []
        except Exception as e:
            print(f"[Client] History fetch failed: {e}")
            return []
