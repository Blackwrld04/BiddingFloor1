from typing import Optional
from agent.models import AuctionSpec, BidResultSpec
from agent.state import NodeState
from agent.strategies.base import BaseBiddingStrategy
from agent.multi_agent.team import MultiAgentDeliberationTeam
from agent.multi_agent.models import DeliberationResult

class MultiAgentReasoningStrategy(BaseBiddingStrategy):
    """
    Veles Hack 2026 Challenge 4 Autonomous Bidding Strategy:
    Full Multi-Agent Deliberation & Explainable Consensus.
    """
    def __init__(self):
        super().__init__("MultiAgent_Reasoning_Team")
        self.team = MultiAgentDeliberationTeam()
        self.last_deliberation: Optional[DeliberationResult] = None
        self.last_bid_price: Optional[float] = None
        self.last_auction_id: Optional[str] = None

    async def calculate_bid_async(self, auction: AuctionSpec, state: NodeState) -> Optional[float]:
        deliberation = await self.team.deliberate_async(auction, state)
        self.last_deliberation = deliberation
        self.last_bid_price = deliberation.final_bid
        self.last_auction_id = auction.auction_id
        return deliberation.final_bid

    def calculate_bid(self, auction: AuctionSpec, state: NodeState) -> Optional[float]:
        deliberation = self.team.deliberate(auction, state)
        self.last_deliberation = deliberation
        self.last_bid_price = deliberation.final_bid
        self.last_auction_id = auction.auction_id
        return deliberation.final_bid

    def update_feedback(self, outcome: BidResultSpec, state: NodeState):
        if outcome.auction_id != self.last_auction_id:
            return
        won = (outcome.winner_node_id == state.node_id)
        if won:
            # We won: slight profit margin expansion
            self.team.update_market_feedback(+0.02)
        else:
            # Lost to a lower bid: adapt margin slightly downward
            self.team.update_market_feedback(-0.015)
