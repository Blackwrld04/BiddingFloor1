from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import time

class AuctionType(str, Enum):
    SECOND_PRICE_SEALED = "SECOND_PRICE_SEALED"  # Vickrey
    FIRST_PRICE_SEALED = "FIRST_PRICE_SEALED"

class TaskDefinition(BaseModel):
    task_id: str
    task_type: str = "edge_inference"
    required_cpu: float = Field(ge=0.1, le=8.0, description="CPU cores needed")
    required_ram_mb: int = Field(ge=128, le=16384, description="RAM in MB needed")
    execution_duration_sec: float = Field(ge=0.5, le=10.0, description="Run duration in seconds")
    max_budget: float = Field(gt=0, description="Maximum budget buyer is willing to pay")
    deadline_sec: float = Field(gt=0, description="Relative deadline from round completion")
    base_cost: float = Field(gt=0, description="Base physical compute cost to run task")
    green_bonus_weight: float = Field(default=0.15, description="Bonus factor for green/renewable nodes")

class AuctionRound(BaseModel):
    auction_id: str
    round_number: int
    task: TaskDefinition
    auction_type: AuctionType = AuctionType.SECOND_PRICE_SEALED
    created_at: float = Field(default_factory=time.time)
    duration_sec: float = 2.0
    status: str = "OPEN"  # OPEN, CLOSED
    bids: Dict[str, float] = Field(default_factory=dict)  # node_id -> bid_price

class NodeRegistration(BaseModel):
    node_id: str
    name: str
    cpu_cores: float = 8.0
    ram_mb: int = 16384
    hardware_type: str = "edge_compute_node"
    location_zone: str = "eu-valencia-edge"
    green_energy_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    base_cost_per_core_sec: float = 0.05

class BidSubmission(BaseModel):
    node_id: str
    auction_id: str
    bid_price: float = Field(gt=0)
    promised_sla_sec: Optional[float] = None
    reasoning_trace: Optional[str] = None
    deliberation_steps: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float] = None
    sponsor_telemetry: Optional[Dict[str, Any]] = None

class BidOutcome(BaseModel):
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
    timestamp: float = Field(default_factory=time.time)
    winner_trace: Optional[str] = None
    deliberation_steps: Optional[List[Dict[str, Any]]] = None
    sponsor_telemetry: Optional[Dict[str, Any]] = None

class LeaderboardEntry(BaseModel):
    node_id: str
    name: str
    bids_placed: int = 0
    auctions_won: int = 0
    win_rate_pct: float = 0.0
    total_revenue: float = 0.0
    total_cost: float = 0.0
    cumulative_profit: float = 0.0
    sla_violations: int = 0
    efficiency_score: float = 0.0  # profit per auction won
    green_rating: float = 0.0
