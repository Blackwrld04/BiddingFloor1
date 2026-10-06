import random
from typing import Dict, Optional
from coordinator.models import TaskDefinition, NodeRegistration

class CompetitorBot:
    def __init__(self, node_id: str, name: str, cpu_cores: float = 6.0, green_ratio: float = 0.5):
        self.node_id = node_id
        self.name = name
        self.cpu_cores = cpu_cores
        self.green_ratio = green_ratio

    def get_registration(self) -> NodeRegistration:
        return NodeRegistration(
            node_id=self.node_id,
            name=self.name,
            cpu_cores=self.cpu_cores,
            ram_mb=12288,
            hardware_type="standard_edge_server",
            location_zone="eu-valencia-edge",
            green_energy_ratio=self.green_ratio,
            base_cost_per_core_sec=0.05
        )

    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        raise NotImplementedError

class RandomBot(CompetitorBot):
    """Bids wildly with volatile markup, uncalibrated to market value."""
    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        markup = random.uniform(1.10, 1.85)
        bid = task.base_cost * markup
        return min(round(bid, 4), task.max_budget)

class GreedyUnderCutter(CompetitorBot):
    """
    Bids aggressively low margin (+5% to +8%).
    When CPU load is overloaded (>90%), its queue backs up and it starts dropping bids.
    """
    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        # Saturated node drops bids due to queue congestion
        if current_utilization.get("cpu_pct", 0) > 90.0:
            if random.random() < 0.70:
                return None  # Dropped bid due to thermal throttling/queue saturation

        markup = random.uniform(1.05, 1.09)
        bid = task.base_cost * markup
        return min(round(bid, 4), task.max_budget)

class StaticMarginBot(CompetitorBot):
    """Rigidly bids a fixed 22% margin, failing to adapt to market dynamics."""
    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        bid = task.base_cost * 1.22
        return min(round(bid, 4), task.max_budget)

def create_default_competitors() -> list[CompetitorBot]:
    return [
        RandomBot("node_random_01", "RandomBot (Chaos)", cpu_cores=6.0, green_ratio=0.30),
        GreedyUnderCutter("node_greedy_02", "GreedyBot (LowMargin)", cpu_cores=6.0, green_ratio=0.40),
        StaticMarginBot("node_static_03", "StaticBot (Fixed22%)", cpu_cores=8.0, green_ratio=0.50)
    ]
