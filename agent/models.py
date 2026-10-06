from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class TaskSpec(BaseModel):
    task_id: str
    task_type: str
    required_cpu: float
    required_ram_mb: int
    execution_duration_sec: float
    max_budget: float
    deadline_sec: float
    base_cost: float
    green_bonus_weight: float = 0.15

class AuctionSpec(BaseModel):
    auction_id: str
    round_number: int
    task: TaskSpec
    auction_type: str = "SECOND_PRICE_SEALED"
    created_at: float
    duration_sec: float
    status: str
    bids: Dict[str, float] = Field(default_factory=dict)

class BidResultSpec(BaseModel):
    auction_id: str
    round_number: int
    task_id: str
    winner_node_id: Optional[str] = None
    clearing_price: float = 0.0
    bids: Dict[str, float] = Field(default_factory=dict)
    profit: float = 0.0
    cost: float = 0.0
    revenue: float = 0.0
    sla_violated: bool = False
    timestamp: float
