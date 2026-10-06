from typing import Optional
from agent.models import AuctionSpec, BidResultSpec
from agent.state import NodeState
from agent.strategies.base import BaseBiddingStrategy

class ZipAdaptiveStrategy(BaseBiddingStrategy):
    """
    Zero-Intelligence Plus (ZIP) Game-Theoretic Strategy.
    Dynamically adjusts target profit margin based on market clearing feedback.
    """
    def __init__(
        self,
        initial_margin: float = 0.25,
        min_margin: float = 0.08,
        max_margin: float = 0.95,
        learning_rate: float = 0.12,
        momentum: float = 0.05
    ):
        super().__init__("ZIP_Adaptive")
        self.margin = initial_margin
        self.min_margin = min_margin
        self.max_margin = max_margin
        self.learning_rate = learning_rate
        self.momentum = momentum
        self.last_bid_price: Optional[float] = None
        self.last_auction_id: Optional[str] = None

    def calculate_bid(self, auction: AuctionSpec, state: NodeState) -> Optional[float]:
        task = auction.task
        
        # Base physical cost
        base_cost = task.base_cost
        
        # Calculate raw bid with current adaptive margin
        target_bid = base_cost * (1.0 + self.margin)
        
        # Cap at maximum task budget
        final_bid = min(target_bid, task.max_budget)
        
        # Avoid bidding below base cost
        if final_bid < base_cost * (1.0 + self.min_margin):
            return None

        self.last_bid_price = round(final_bid, 4)
        self.last_auction_id = auction.auction_id
        return self.last_bid_price

    def update_feedback(self, outcome: BidResultSpec, state: NodeState):
        if outcome.auction_id != self.last_auction_id or self.last_bid_price is None:
            return

        our_id = state.node_id
        won = (outcome.winner_node_id == our_id)
        
        if won:
            # We won! If clearing price was well above our bid (Vickrey surplus),
            # we can cautiously expand our margin to extract higher surplus.
            surplus = outcome.clearing_price - self.last_bid_price
            if surplus > 0:
                self.margin += self.learning_rate * 0.5 * (surplus / max(1.0, outcome.cost))
            else:
                self.margin += self.momentum
        else:
            # We lost! If another node bid lower than us, our margin was too greedy.
            if outcome.winner_node_id and outcome.clearing_price > 0:
                delta = outcome.clearing_price - self.last_bid_price
                # Lower margin proportionally
                adjustment = abs(delta) / max(1.0, outcome.cost)
                self.margin -= self.learning_rate * adjustment
            else:
                # Nobody won (budgets too high)
                self.margin -= self.momentum

        # Clip margin within safe boundaries
        self.margin = max(self.min_margin, min(self.max_margin, self.margin))
