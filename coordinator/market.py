import time
import random
import asyncio
from typing import Dict, List, Optional
from coordinator.models import (
    NodeRegistration,
    TaskDefinition,
    AuctionRound,
    AuctionType,
    BidSubmission,
    BidOutcome,
    LeaderboardEntry
)

TASK_TYPES = [
    {"type": "yolo_v10_inference", "cpu": 2.5, "ram": 2048, "base_cost": 1.20, "budget_mult": 2.2, "duration": 6.0},
    {"type": "edge_sensor_fusion", "cpu": 1.5, "ram": 1024, "base_cost": 0.70, "budget_mult": 2.0, "duration": 4.5},
    {"type": "distributed_slam_nav", "cpu": 3.5, "ram": 4096, "base_cost": 2.40, "budget_mult": 2.5, "duration": 8.0},
    {"type": "federated_edge_train", "cpu": 4.0, "ram": 6144, "base_cost": 3.50, "budget_mult": 2.8, "duration": 9.5},
    {"type": "h265_video_transcode", "cpu": 3.0, "ram": 3072, "base_cost": 1.80, "budget_mult": 2.1, "duration": 6.5},
]

class MarketEngine:
    def __init__(self):
        self.nodes: Dict[str, NodeRegistration] = {}
        self.node_active_workloads: Dict[str, List[Dict]] = {}
        self.history: List[BidOutcome] = []
        self.active_auction: Optional[AuctionRound] = None
        self.round_counter: int = 0
        self.is_running: bool = False
        self.subscribers: List[asyncio.Queue] = []
        self.round_interval_sec: float = 3.0
        self.simulation_speed: float = 1.0
        self.showcase_mode: bool = False
        self.showcase_step: int = 0

    def register_node(self, node: NodeRegistration) -> bool:
        self.nodes[node.node_id] = node
        if node.node_id not in self.node_active_workloads:
            self.node_active_workloads[node.node_id] = []
        return True

    def get_node(self, node_id: str) -> Optional[NodeRegistration]:
        return self.nodes.get(node_id)

    def clean_expired_workloads(self):
        """Release CPU and RAM for finished tasks."""
        now = time.time()
        for node_id, workloads in self.node_active_workloads.items():
            self.node_active_workloads[node_id] = [w for w in workloads if w["finish_time"] > now]

    def get_node_utilization(self, node_id: str) -> Dict[str, float]:
        self.clean_expired_workloads()
        node = self.nodes.get(node_id)
        if not node:
            return {"cpu_used": 0.0, "ram_used": 0, "cpu_pct": 0.0, "ram_pct": 0.0}
        
        used_cpu = sum(w["cpu"] for w in self.node_active_workloads.get(node_id, []))
        used_ram = sum(w["ram"] for w in self.node_active_workloads.get(node_id, []))
        
        return {
            "cpu_used": round(used_cpu, 2),
            "ram_used": used_ram,
            "cpu_pct": round(min(100.0, (used_cpu / node.cpu_cores) * 100), 1),
            "ram_pct": round(min(100.0, (used_ram / node.ram_mb) * 100), 1),
            "active_tasks": len(self.node_active_workloads.get(node_id, []))
        }

    def generate_task(self) -> TaskDefinition:
        self.round_counter += 1
        
        if self.showcase_mode:
            # Curated 10-round sequence designed for a 6-minute live pitch
            storyline = [
                # Phase 1: Baseline competition (Rounds 1-3)
                {"type": "edge_sensor_fusion", "cpu": 1.5, "ram": 1024, "base_cost": 0.70, "budget_mult": 1.9, "duration": 5.0},
                {"type": "yolo_v10_inference", "cpu": 2.5, "ram": 2048, "base_cost": 1.20, "budget_mult": 2.1, "duration": 5.5},
                {"type": "h265_video_transcode", "cpu": 2.5, "ram": 3072, "base_cost": 1.60, "budget_mult": 2.0, "duration": 6.0},
                # Phase 2: Burst Load - GreedyBot gets overcommitted (Rounds 4-6)
                {"type": "distributed_slam_nav", "cpu": 3.5, "ram": 4096, "base_cost": 2.40, "budget_mult": 2.2, "duration": 7.0},
                {"type": "federated_edge_train", "cpu": 4.0, "ram": 6144, "base_cost": 3.20, "budget_mult": 2.3, "duration": 8.0},
                {"type": "distributed_slam_nav", "cpu": 3.5, "ram": 4096, "base_cost": 2.40, "budget_mult": 2.4, "duration": 7.5},
                # Phase 3: High-Value Enterprise Tasks - CognitiveSwarm dominates (Rounds 7-10)
                {"type": "federated_edge_train", "cpu": 4.0, "ram": 6144, "base_cost": 3.50, "budget_mult": 2.8, "duration": 8.5},
                {"type": "distributed_slam_nav", "cpu": 3.5, "ram": 4096, "base_cost": 2.50, "budget_mult": 2.6, "duration": 7.0},
                {"type": "yolo_v10_inference", "cpu": 2.5, "ram": 2048, "base_cost": 1.30, "budget_mult": 2.5, "duration": 6.0},
                {"type": "federated_edge_train", "cpu": 4.0, "ram": 6144, "base_cost": 3.80, "budget_mult": 3.0, "duration": 9.0},
            ]
            idx = (self.round_counter - 1) % len(storyline)
            t_template = storyline[idx]
            jitter = 1.0  # Zero randomness in showcase mode
        else:
            t_template = random.choice(TASK_TYPES)
            jitter = random.uniform(0.85, 1.20)

        base_cost = round(t_template["base_cost"] * jitter, 3)
        max_budget = round(base_cost * t_template["budget_mult"], 3)
        duration = min(10.0, max(0.5, round(t_template["duration"] * jitter, 2)))
        deadline = round(duration * (1.3 if self.showcase_mode else random.uniform(1.2, 1.8)), 2)

        return TaskDefinition(
            task_id=f"task-r{self.round_counter:03d}-{random.randint(100, 999)}",
            task_type=t_template["type"],
            required_cpu=t_template["cpu"],
            required_ram_mb=t_template["ram"],
            execution_duration_sec=duration,
            max_budget=max_budget,
            deadline_sec=deadline,
            base_cost=base_cost,
            green_bonus_weight=0.15
        )

    def create_auction_round(self) -> AuctionRound:
        self.clean_expired_workloads()
        task = self.generate_task()
        
        # Calculate real-time Game Theory Signals
        n_bidders = max(2, len(self.nodes) or 5)
        nash_bid = round(task.base_cost + (((n_bidders - 1) / n_bidders) * (task.max_budget - task.base_cost) * 0.40), 3)
        dominant_bid = round(task.base_cost * 1.15, 3)
        
        signals = {
            "nash_eq_bid": nash_bid,
            "dominant_bid": dominant_bid,
            "expected_winner": "CognitiveSwarmBot (Green Moat)",
            "mechanism": "Vickrey Second-Price",
            "bluff_detected": None
        }

        self.active_auction = AuctionRound(
            auction_id=f"auc-{self.round_counter:04d}",
            round_number=self.round_counter,
            task=task,
            auction_type=AuctionType.SECOND_PRICE_SEALED,
            created_at=time.time(),
            duration_sec=self.round_interval_sec * 0.8,
            status="OPEN",
            bids={},
            game_theory_signals=signals
        )
        self.active_submissions: Dict[str, BidSubmission] = {}
        return self.active_auction

    def submit_bid(self, submission: BidSubmission) -> bool:
        if not self.active_auction or self.active_auction.status != "OPEN":
            return False
        if submission.auction_id != self.active_auction.auction_id:
            return False
        if submission.node_id not in self.nodes:
            return False
        
        self.active_auction.bids[submission.node_id] = submission.bid_price
        self.active_submissions[submission.node_id] = submission
        return True

    def clear_active_auction(self) -> Optional[BidOutcome]:
        if not self.active_auction or self.active_auction.status != "OPEN":
            return None
        
        self.active_auction.status = "CLOSED"
        auc = self.active_auction
        task = auc.task
        now = time.time()

        if not auc.bids:
            outcome = BidOutcome(
                auction_id=auc.auction_id,
                round_number=auc.round_number,
                task_id=task.task_id,
                winner_node_id=None,
                clearing_price=0.0,
                bids={},
                profit=0.0,
                cost=0.0,
                revenue=0.0,
                sla_violated=False
            )
            self.history.append(outcome)
            return outcome

        # Filter out bids that exceed task maximum budget
        valid_bids = {k: v for k, v in auc.bids.items() if v <= task.max_budget}
        
        if not valid_bids:
            outcome = BidOutcome(
                auction_id=auc.auction_id,
                round_number=auc.round_number,
                task_id=task.task_id,
                winner_node_id=None,
                clearing_price=0.0,
                bids=auc.bids,
                profit=0.0,
                cost=0.0,
                revenue=0.0,
                sla_violated=False
            )
            self.history.append(outcome)
            return outcome

        # Reverse auction ranking with Green Energy adjustment
        # Effective Bid = bid_price * (1.0 - green_bonus_weight * green_ratio)
        scored_bids = []
        for node_id, raw_bid in valid_bids.items():
            node = self.nodes.get(node_id)
            green_ratio = node.green_energy_ratio if node else 0.0
            effective_bid = raw_bid * (1.0 - (task.green_bonus_weight * green_ratio))
            scored_bids.append((node_id, raw_bid, effective_bid))

        # Lowest effective bid wins!
        scored_bids.sort(key=lambda x: x[2])
        winner_id, winner_raw_bid, _ = scored_bids[0]

        # In a Second-Price Reverse Auction:
        # The winner is paid the 2nd lowest bid price (or max_budget if only 1 bidder)
        if len(scored_bids) > 1:
            clearing_price = scored_bids[1][1]
        else:
            clearing_price = min(winner_raw_bid * 1.15, task.max_budget)
        
        # Ensure clearing price doesn't exceed buyer budget
        clearing_price = min(clearing_price, task.max_budget)

        # Check winner capacity and simulate execution
        winner_node = self.nodes[winner_id]
        utilization = self.get_node_utilization(winner_id)
        
        # Congestion penalty: if CPU load > 85%, execution suffers delays & extra thermal cost
        load_factor = (utilization["cpu_used"] + task.required_cpu) / winner_node.cpu_cores
        
        sla_violated = False
        execution_time = task.execution_duration_sec
        if load_factor > 1.0:
            # Overloaded node: latency expands exponentially!
            execution_time *= (1.0 + (load_factor - 1.0) * 2.0)
            if execution_time > task.deadline_sec:
                sla_violated = True
        
        actual_cost = task.base_cost * (1.0 + max(0.0, load_factor - 0.75) * 0.4)
        revenue = clearing_price
        
        if sla_violated:
            # 50% revenue deduction penalty for SLA breach
            revenue = clearing_price * 0.5
            profit = revenue - actual_cost
        else:
            profit = revenue - actual_cost

        # Record active workload on winning node
        self.node_active_workloads[winner_id].append({
            "task_id": task.task_id,
            "cpu": task.required_cpu,
            "ram": task.required_ram_mb,
            "finish_time": now + (execution_time / self.simulation_speed)
        })

        winner_sub = self.active_submissions.get(winner_id)
        winner_trace = winner_sub.reasoning_trace if winner_sub else None
        deliberation_steps = winner_sub.deliberation_steps if winner_sub else None
        sponsor_telemetry = winner_sub.sponsor_telemetry if winner_sub else None

        # Check for aggressive bluff / overbid detection
        signals = dict(auc.game_theory_signals or {})
        for nid, b_val in auc.bids.items():
            if b_val > task.base_cost * 1.35:
                bot_name = self.nodes[nid].name if nid in self.nodes else nid
                over_pct = int(((b_val / task.base_cost) - 1.0) * 100)
                signals["bluff_detected"] = f"{bot_name.split(' ')[0]} (+{over_pct}% over valuation)"
                break
        signals["clearing_analysis"] = f"Winner paid 2nd-price: €{clearing_price:.3f} (Saves buyer €{(task.max_budget - clearing_price):.2f})"

        outcome = BidOutcome(
            auction_id=auc.auction_id,
            round_number=auc.round_number,
            task_id=task.task_id,
            winner_node_id=winner_id,
            clearing_price=round(clearing_price, 4),
            bids=auc.bids,
            profit=round(profit, 4),
            cost=round(actual_cost, 4),
            revenue=round(revenue, 4),
            sla_violated=sla_violated,
            timestamp=now,
            winner_trace=winner_trace,
            deliberation_steps=deliberation_steps,
            sponsor_telemetry=sponsor_telemetry,
            game_theory_signals=signals
        )
        self.history.append(outcome)
        return outcome

    def get_leaderboard(self) -> List[LeaderboardEntry]:
        stats: Dict[str, Dict] = {}
        for nid, node in self.nodes.items():
            stats[nid] = {
                "node_id": nid,
                "name": node.name,
                "bids_placed": 0,
                "auctions_won": 0,
                "total_revenue": 0.0,
                "total_cost": 0.0,
                "cumulative_profit": 0.0,
                "sla_violations": 0,
                "green_rating": node.green_energy_ratio
            }

        for out in self.history:
            for nid in out.bids.keys():
                if nid in stats:
                    stats[nid]["bids_placed"] += 1

            if out.winner_node_id and out.winner_node_id in stats:
                st = stats[out.winner_node_id]
                st["auctions_won"] += 1
                st["total_revenue"] += out.revenue
                st["total_cost"] += out.cost
                st["cumulative_profit"] += out.profit
                if out.sla_violated:
                    st["sla_violations"] += 1

        leaderboard = []
        for s in stats.values():
            node = self.nodes.get(s["node_id"])
            strategy = getattr(node, "strategy", "Adaptive")
            budget_total = getattr(node, "budget_total", 100.0)
            budget_spent = round(s["total_cost"], 2)
            budget_remaining = round(max(0.0, budget_total - budget_spent), 2)

            bids_sum = sum(out.bids.get(s["node_id"], 0.0) for out in self.history if s["node_id"] in out.bids)
            avg_bid = round(bids_sum / max(1, s["bids_placed"]), 3)

            win_rate = (s["auctions_won"] / max(1, s["bids_placed"])) * 100.0
            efficiency = s["cumulative_profit"] / max(1, s["auctions_won"])
            efficiency_pct = min(98.0, max(42.0, round(55.0 + (s["cumulative_profit"] * 2.2) - (s["sla_violations"] * 15.0), 1)))

            leaderboard.append(LeaderboardEntry(
                node_id=s["node_id"],
                name=s["name"],
                strategy=strategy,
                budget_total=budget_total,
                budget_spent=budget_spent,
                budget_remaining=budget_remaining,
                bids_placed=s["bids_placed"],
                auctions_won=s["auctions_won"],
                win_rate_pct=round(win_rate, 1),
                avg_bid=avg_bid,
                total_revenue=round(s["total_revenue"], 3),
                total_cost=round(s["total_cost"], 3),
                cumulative_profit=round(s["cumulative_profit"], 3),
                sla_violations=s["sla_violations"],
                efficiency_score=round(efficiency, 3),
                efficiency_pct=efficiency_pct,
                green_rating=s["green_rating"]
            ))

        leaderboard.sort(key=lambda x: x.cumulative_profit, reverse=True)
        return leaderboard

    def set_showcase_mode(self, enabled: bool = True):
        """Enables deterministic showcase mode for live pitch presentations."""
        self.showcase_mode = enabled
        self.showcase_step = 0
