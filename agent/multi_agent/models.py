from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import time

class AgentRole(str, Enum):
    MARKET_ANALYST = "MARKET_ANALYST"
    CAPACITY_GUARDIAN = "CAPACITY_GUARDIAN"
    GREEN_ARBITRAGE = "GREEN_ARBITRAGE"
    SYNTHESIZER = "SYNTHESIZER"

class DeliberationStatus(str, Enum):
    ANALYZING = "ANALYZING"
    OBJECTION = "OBJECTION"
    REVISING = "REVISING"
    APPROVED = "APPROVED"
    CONSENSUS = "CONSENSUS"

class DeliberationStep(BaseModel):
    step_number: int
    role: AgentRole
    status: DeliberationStatus
    thought: str
    confidence: float = Field(ge=0.0, le=1.0)
    proposed_bid: Optional[float] = None
    timestamp: float = Field(default_factory=time.time)

class DeliberationResult(BaseModel):
    final_bid: Optional[float] = None
    decision: str  # "BID_SUBMITTED" or "TASK_SKIPPED"
    confidence_score: float = 0.0
    reasoning_summary: str
    steps: List[DeliberationStep] = Field(default_factory=list)
    green_advantage_pct: float = 0.0
    sla_risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    sponsor_telemetry: Dict[str, Any] = Field(default_factory=dict)
