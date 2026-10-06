from abc import ABC, abstractmethod
from typing import Optional
from agent.models import TaskSpec, AuctionSpec, BidResultSpec
from agent.state import NodeState

class BaseBiddingStrategy(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def calculate_bid(self, auction: AuctionSpec, state: NodeState) -> Optional[float]:
        """
        Calculates the bid price for the given auction.
        Returns None if the agent decides not to bid.
        """
        pass

    @abstractmethod
    def update_feedback(self, outcome: BidResultSpec, state: NodeState):
        """
        Updates internal models/weights based on round clearing results.
        """
        pass
