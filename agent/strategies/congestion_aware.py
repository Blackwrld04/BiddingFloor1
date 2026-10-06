from typing import Optional
from agent.models import AuctionSpec, BidResultSpec
from agent.state import NodeState
from agent.strategies.base import BaseBiddingStrategy

class CongestionAwareStrategy(BaseBiddingStrategy):
    """
    Capacity & Green-Aware Bidding Strategy.
    Scales bid price based on node CPU/RAM congestion to avoid SLA breaches,
    and leverages green energy bonus to extract higher clearing prices.
    """
    def __init__(self, base_markup: float = 0.20, congestion_exponent: float = 3.0):
        super().__init__("Congestion_Aware")
        self.base_markup = base_markup
        self.congestion_exponent = congestion_exponent

    def calculate_bid(self, auction: AuctionSpec, state: NodeState) -> Optional[float]:
        task = auction.task
        
        # Hard check: Do not bid if this would trigger severe SLA breach
        if not state.can_fit(task, safe_threshold=0.92):
            return None

        # Calculate projected utilization after accepting this task
        proj_cpu = (state.get_used_cpu() + task.required_cpu) / state.cpu_cores
        proj_ram = (state.get_used_ram() + task.required_ram_mb) / state.ram_mb
        max_load = max(proj_cpu, proj_ram)

        # Exponential congestion markup
        congestion_multiplier = 1.0 + (max_load ** self.congestion_exponent) * 0.85

        # Green Energy Strategic Shading:
        # Since market discounts green bids by (1 - green_weight * green_ratio),
        # we can shade our nominal bid upwards by approximately 1 / (1 - bonus)
        green_advantage = 1.0 / max(0.80, 1.0 - (task.green_bonus_weight * state.green_energy_ratio * 0.6))

        # Final bid calculation
        nominal_bid = task.base_cost * (1.0 + self.base_markup) * congestion_multiplier * green_advantage

        # Ensure we stay within buyer maximum budget
        final_bid = min(nominal_bid, task.max_budget)

        # Never bid below base cost
        if final_bid <= task.base_cost:
            return None

        return round(final_bid, 4)

    def update_feedback(self, outcome: BidResultSpec, state: NodeState):
        # Congestion model relies on local hardware measurements;
        # dynamically adjusts base markup if SLA violations occur
        if outcome.winner_node_id == state.node_id and outcome.sla_violated:
            # Heavily penalize and increase base markup to bid more conservatively
            self.base_markup += 0.05
