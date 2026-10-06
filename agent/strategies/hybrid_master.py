from typing import Optional
from agent.models import AuctionSpec, BidResultSpec
from agent.state import NodeState
from agent.strategies.base import BaseBiddingStrategy
from agent.strategies.zip_adaptive import ZipAdaptiveStrategy

class CognitiveHybridMasterStrategy(BaseBiddingStrategy):
    """
    Cognitive Hybrid Swarm Strategy (Grand Champion).
    1. Green Moat Inversion:
       Since our node is 85% renewable, the coordinator awards a 12.75% score discount!
       We invert this discount to submit nominal bids that yield 14-25% gross profit
       while remaining the lowest effective bid on the leaderboard.
    2. Dynamic Congestion Gating:
       Refuses low-margin tasks when load > 60%, preventing SLA degradation.
    3. ZIP Feedback Loops:
       Adapts target margin based on market clearing delta.
    """
    def __init__(self):
        super().__init__("Cognitive_Hybrid_Master")
        self.zip_engine = ZipAdaptiveStrategy(
            initial_margin=0.08,
            min_margin=0.04,
            max_margin=0.60,
            learning_rate=0.15
        )
        self.last_bid_price: Optional[float] = None
        self.last_auction_id: Optional[str] = None

    def calculate_bid(self, auction: AuctionSpec, state: NodeState) -> Optional[float]:
        task = auction.task
        current_load = state.get_cpu_utilization()

        # Gate 1: Hard SLA Safety Guard
        # If adding this task pushes CPU or RAM above 85%, DO NOT BID.
        if not state.can_fit(task, safe_threshold=0.85):
            return None

        # Gate 2: Strategic Headroom
        # If load > 55% and task budget is meager (<1.7x cost), preserve cores
        # for high-margin federated training or SLAM tasks
        budget_ratio = task.max_budget / max(0.01, task.base_cost)
        if current_load > 0.55 and budget_ratio < 1.7:
            return None

        # 3. Base Adaptive Margin from ZIP
        margin = self.zip_engine.margin

        # 4. Green Moat Inversion
        # In market: effective_bid = raw_bid * (1.0 - 0.15 * green_ratio)
        # Our discount factor: 1.0 - 0.15 * 0.85 = 0.8725
        # We target an effective bid that beats standard competitors (who bid ~1.05 * 0.94 = 0.987)
        # Target effective bid:
        target_effective = task.base_cost * (1.0 + margin * 0.5)

        # Invert our green discount to get nominal raw bid
        our_discount_factor = 1.0 - (task.green_bonus_weight * state.green_energy_ratio)
        nominal_raw_bid = target_effective / our_discount_factor

        # 5. Congestion scaling if moderately loaded
        if current_load > 0.40:
            congestion_multiplier = 1.0 + (current_load ** 2) * 0.35
            nominal_raw_bid *= congestion_multiplier

        final_bid = min(nominal_raw_bid, task.max_budget)

        # Ensure we always earn at least marginal cost + 6%
        if final_bid < task.base_cost * 1.06:
            final_bid = task.base_cost * 1.06

        self.last_bid_price = round(final_bid, 4)
        self.last_auction_id = auction.auction_id
        return self.last_bid_price

    def update_feedback(self, outcome: BidResultSpec, state: NodeState):
        self.zip_engine.update_feedback(outcome, state)
