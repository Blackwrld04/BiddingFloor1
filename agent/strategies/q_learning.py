import random
from typing import Dict, Tuple, Optional
from agent.models import AuctionSpec, BidResultSpec
from agent.state import NodeState
from agent.strategies.base import BaseBiddingStrategy

class QLearningBiddingStrategy(BaseBiddingStrategy):
    """
    Reinforcement Learning (Q-Learning) Agent for Edge Resource Auctions.
    Learns the optimal markup action for different market and node load states.
    """
    ACTIONS = [1.10, 1.20, 1.35, 1.55, 1.85, 2.20]  # Markup multipliers

    def __init__(
        self,
        learning_rate: float = 0.15,
        discount_factor: float = 0.85,
        epsilon: float = 0.15,
        epsilon_decay: float = 0.99
    ):
        super().__init__("Q_Learning_Agent")
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.q_table: Dict[Tuple[str, str], Dict[float, float]] = {}
        
        self.last_state: Optional[Tuple[str, str]] = None
        self.last_action: Optional[float] = None
        self.last_auction_id: Optional[str] = None

    def _get_state(self, auction: AuctionSpec, state: NodeState) -> Tuple[str, str]:
        # Dimension 1: Node Load
        load = state.get_cpu_utilization()
        if load < 0.40:
            load_bucket = "LOW"
        elif load < 0.75:
            load_bucket = "MED"
        else:
            load_bucket = "HIGH"

        # Dimension 2: Task Budget Ratio
        ratio = auction.task.max_budget / max(0.1, auction.task.base_cost)
        if ratio < 1.8:
            budget_bucket = "TIGHT"
        elif ratio < 2.3:
            budget_bucket = "NORMAL"
        else:
            budget_bucket = "RICH"

        return (load_bucket, budget_bucket)

    def _ensure_state_initialized(self, s: Tuple[str, str]):
        if s not in self.q_table:
            self.q_table[s] = {a: 0.0 for a in self.ACTIONS}

    def calculate_bid(self, auction: AuctionSpec, state: NodeState) -> Optional[float]:
        # Safe threshold
        if not state.can_fit(auction.task, safe_threshold=0.90):
            return None

        s = self._get_state(auction, state)
        self._ensure_state_initialized(s)

        # Epsilon-Greedy Action Selection
        if random.random() < self.epsilon:
            action = random.choice(self.ACTIONS)
        else:
            # Pick action with maximum Q-value
            action = max(self.q_table[s].items(), key=lambda x: x[1])[0]

        self.last_state = s
        self.last_action = action
        self.last_auction_id = auction.auction_id

        # Calculate bid
        bid = auction.task.base_cost * action
        final_bid = min(bid, auction.task.max_budget)
        return round(final_bid, 4)

    def update_feedback(self, outcome: BidResultSpec, state: NodeState):
        if (
            self.last_state is None
            or self.last_action is None
            or outcome.auction_id != self.last_auction_id
        ):
            return

        our_id = state.node_id
        won = (outcome.winner_node_id == our_id)

        # Compute immediate reward
        if won:
            if outcome.sla_violated:
                reward = -abs(outcome.profit) - 1.0  # Penalize SLA degradation
            else:
                reward = outcome.profit  # Positive profit utility
        else:
            reward = 0.0

        s = self.last_state
        a = self.last_action
        
        # Max future Q estimate
        max_future_q = max(self.q_table[s].values()) if s in self.q_table else 0.0
        
        # Bellman update
        old_val = self.q_table[s][a]
        self.q_table[s][a] = old_val + self.lr * (reward + self.gamma * max_future_q - old_val)

        # Decay exploration
        self.epsilon = max(0.02, self.epsilon * self.epsilon_decay)
