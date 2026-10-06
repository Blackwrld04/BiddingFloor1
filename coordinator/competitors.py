import math
import random
from typing import Dict, Optional, List
from coordinator.models import TaskDefinition, NodeRegistration

class CompetitorBot:
    def __init__(
        self,
        node_id: str,
        name: str,
        strategy: str,
        cpu_cores: float = 6.0,
        green_ratio: float = 0.5,
        budget: float = 100.0
    ):
        self.node_id = node_id
        self.name = name
        self.strategy = strategy
        self.cpu_cores = cpu_cores
        self.green_ratio = green_ratio
        self.budget = budget
        self.spent = 0.0
        self.wins = 0
        self.bids_history: List[float] = []

    def get_registration(self) -> NodeRegistration:
        return NodeRegistration(
            node_id=self.node_id,
            name=self.name,
            cpu_cores=self.cpu_cores,
            ram_mb=12288,
            hardware_type="standard_edge_server",
            location_zone="eu-valencia-edge",
            green_energy_ratio=self.green_ratio,
            base_cost_per_core_sec=0.05,
            strategy=self.strategy,
            budget_total=self.budget
        )

    def remaining_budget(self) -> float:
        return max(0.0, self.budget - self.spent)

    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        raise NotImplementedError

    def record_outcome(self, clearing_price: float, won: bool, all_bids: Dict[str, float]):
        if won:
            self.wins += 1
            # In reverse auction, node receives clearing_price as revenue


class NashBot(CompetitorBot):
    """
    1. Nash Equilibrium Bot
    Assumes all competing nodes are rational in a reverse auction setting.
    Bids at the calculated symmetric Nash equilibrium, balancing win probability
    against margin. Safe, consistent, never catastrophically overbids.
    """
    def __init__(self, node_id: str = "node_nash_01", name: str = "NashBot (Nash Eq.)"):
        super().__init__(node_id, name, strategy="Nash Equilibrium", cpu_cores=8.0, green_ratio=0.55)

    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        if self.remaining_budget() < task.base_cost:
            return None
        
        # Symmetric Nash reverse auction equilibrium approximation with n=5 bidders:
        # b = cost + (n-1)/n * (max_budget - cost) * markup_factor
        n = 5
        spread = max(0.1, task.max_budget - task.base_cost)
        nash_markup = ((n - 1) / n) * 0.40
        bid = task.base_cost + (spread * nash_markup)
        
        # Add slight jitter for game realism
        bid *= random.uniform(0.98, 1.02)
        return min(round(bid, 4), task.max_budget)


class DominantStrategyBot(CompetitorBot):
    """
    2. Dominant Strategy Bot
    Bids its true economic valuation every round. In a Vickrey second-price auction,
    truthful valuation bidding is the weakly dominant strategy.
    """
    def __init__(self, node_id: str = "node_dominant_02", name: str = "DominantBot (Truthful)"):
        super().__init__(node_id, name, strategy="Dominant Strategy", cpu_cores=6.0, green_ratio=0.50)

    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        if self.remaining_budget() < task.base_cost:
            return None
        
        # Dominant strategy in Vickrey: bid true valuation (base cost + normal operating margin 15%)
        true_valuation = task.base_cost * 1.15
        return min(round(true_valuation, 4), task.max_budget)


class BayesianBot(CompetitorBot):
    """
    3. Bayesian Bot
    Maintains a probability distribution over competitor bid markups.
    Updates beliefs after every round using Bayes' rule (conjugate Gaussian update).
    Maximizes expected utility EU = P(win) * (Clearing_Est - Cost).
    """
    def __init__(self, node_id: str = "node_bayesian_03", name: str = "BayesianBot (Belief Opt)"):
        super().__init__(node_id, name, strategy="Bayesian Updating", cpu_cores=8.0, green_ratio=0.60)
        # Prior belief about competitor markups: Mean 1.30, Std 0.20
        self.beliefs = {"mean": 1.30, "std": 0.20}

    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        if self.remaining_budget() < task.base_cost:
            return None

        # Approximate CDF using normal approximation to find bid that maximizes expected utility
        best_bid = task.base_cost * 1.18
        best_eu = -1.0

        for candidate_markup in [1.08, 1.12, 1.16, 1.20, 1.25, 1.32, 1.40]:
            candidate_bid = task.base_cost * candidate_markup
            if candidate_bid > task.max_budget:
                continue

            # Win probability: competitor markup is higher than candidate markup
            # z-score relative to prior belief distribution
            z = (candidate_markup - self.beliefs["mean"]) / max(0.05, self.beliefs["std"])
            # P(competitor > candidate) = 1 - CDF(z)
            # Using erf approximation for normal CDF
            cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            p_win = max(0.05, min(0.95, (1.0 - cdf) ** 3))

            margin = candidate_bid - task.base_cost
            eu = p_win * margin
            if eu > best_eu:
                best_eu = eu
                best_bid = candidate_bid

        return min(round(best_bid, 4), task.max_budget)

    def record_outcome(self, clearing_price: float, won: bool, all_bids: Dict[str, float]):
        super().record_outcome(clearing_price, won, all_bids)
        competitor_bids = [b for nid, b in all_bids.items() if nid != self.node_id and b > 0]
        if competitor_bids and clearing_price > 0:
            observed_markup = clearing_price / max(0.1, competitor_bids[0])
            alpha = 0.30  # Learning rate
            self.beliefs["mean"] = (1.0 - alpha) * self.beliefs["mean"] + (alpha * observed_markup)


class AggressiveBluffBot(CompetitorBot):
    """
    4. Aggressive / Bluffing Bot
    Overbids strategically or pushes prices to scare competitors out of the arena.
    Captures contested high-margin workloads, but burns budget faster.
    """
    def __init__(self, node_id: str = "node_aggro_04", name: str = "AggroBot (Bluffing)"):
        super().__init__(node_id, name, strategy="Aggressive Bluffing", cpu_cores=6.0, green_ratio=0.35)

    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        if self.remaining_budget() < task.base_cost:
            return None

        # Strategically pushes higher markup (+35% to +60%) to test market tolerance
        markup = random.uniform(1.35, 1.60)
        bid = task.base_cost * markup
        return min(round(bid, 4), task.max_budget)


class FrugalSniperBot(CompetitorBot):
    """
    5. Frugal / Sniping Bot
    Waits, observes cluster congestion, enters selectively with precision bids.
    Conservative budget management, targets high-margin or low-contention resources.
    """
    def __init__(self, node_id: str = "node_frugal_05", name: str = "FrugalBot (Sniper)"):
        super().__init__(node_id, name, strategy="Frugal Sniper", cpu_cores=6.0, green_ratio=0.45)

    def calculate_bid(self, task: TaskDefinition, current_utilization: Dict[str, float]) -> Optional[float]:
        if self.remaining_budget() < task.base_cost:
            return None

        # Skips auction when node load is high to preserve thermal and memory safety
        if current_utilization.get("cpu_pct", 0) > 65.0:
            return None

        # Precision low-margin snipe (+6% to +11%)
        markup = random.uniform(1.06, 1.11)
        bid = task.base_cost * markup
        return min(round(bid, 4), task.max_budget)


def create_default_competitors() -> List[CompetitorBot]:
    return [
        NashBot("node_nash_01", "NashBot (Nash Eq.)"),
        DominantStrategyBot("node_dominant_02", "DominantBot (Truthful)"),
        BayesianBot("node_bayesian_03", "BayesianBot (Belief Opt)"),
        AggressiveBluffBot("node_aggro_04", "AggroBot (Bluffing)"),
        FrugalSniperBot("node_frugal_05", "FrugalBot (Sniper)")
    ]
