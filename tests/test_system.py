import pytest
from coordinator.models import NodeRegistration, TaskDefinition, BidSubmission, AuctionRound, AuctionType
from coordinator.market import MarketEngine
from agent.state import NodeState
from agent.models import TaskSpec, AuctionSpec
from agent.strategies.hybrid_master import CognitiveHybridMasterStrategy
from agent.strategies.zip_adaptive import ZipAdaptiveStrategy

def test_vickrey_second_price_clearing():
    market = MarketEngine()
    # Register two identical nodes
    node1 = NodeRegistration(node_id="node_a", name="Node A", cpu_cores=8, ram_mb=16384, green_energy_ratio=0.5)
    node2 = NodeRegistration(node_id="node_b", name="Node B", cpu_cores=8, ram_mb=16384, green_energy_ratio=0.5)
    market.register_node(node1)
    market.register_node(node2)

    # Create auction
    auction = market.create_auction_round()
    cost = auction.task.base_cost
    
    # Node A bids cost * 1.15, Node B bids cost * 1.35
    market.submit_bid(BidSubmission(node_id="node_a", auction_id=auction.auction_id, bid_price=round(cost * 1.15, 4)))
    market.submit_bid(BidSubmission(node_id="node_b", auction_id=auction.auction_id, bid_price=round(cost * 1.35, 4)))

    outcome = market.clear_active_auction()
    assert outcome is not None
    assert outcome.winner_node_id == "node_a"
    # Second-price reverse auction: winner is paid the 2nd lowest price (Node B's bid)
    expected_clearing = min(round(cost * 1.35, 4), auction.task.max_budget)
    assert outcome.clearing_price == expected_clearing
    assert outcome.profit > 0

def test_green_energy_advantage():
    market = MarketEngine()
    # Node Green has 85% solar, Node Dirty has 30% grid
    node_green = NodeRegistration(node_id="node_green", name="Green Node", cpu_cores=8, ram_mb=16384, green_energy_ratio=0.85)
    node_dirty = NodeRegistration(node_id="node_dirty", name="Dirty Node", cpu_cores=8, ram_mb=16384, green_energy_ratio=0.30)
    market.register_node(node_green)
    market.register_node(node_dirty)

    auction = market.create_auction_round()
    cost = auction.task.base_cost
    # Dirty bids cost * 1.08, Green bids cost * 1.15
    # Dirty effective: (1.08 * cost) * (1 - 0.15 * 0.30) = cost * 1.0314
    # Green effective: (1.15 * cost) * (1 - 0.15 * 0.85) = cost * 1.0033
    # Green effective bid is LOWER even though raw bid is 7% higher!
    dirty_bid = round(cost * 1.08, 4)
    green_bid = round(cost * 1.15, 4)
    market.submit_bid(BidSubmission(node_id="node_green", auction_id=auction.auction_id, bid_price=green_bid))
    market.submit_bid(BidSubmission(node_id="node_dirty", auction_id=auction.auction_id, bid_price=dirty_bid))

    outcome = market.clear_active_auction()
    assert outcome.winner_node_id == "node_green"
    # In 2nd price auction, winner gets paid 2nd lowest bid (or max budget)
    assert outcome.clearing_price == dirty_bid
    assert outcome.profit > 0

def test_congestion_gating():
    state = NodeState(node_id="test_node", cpu_cores=4.0, ram_mb=8192)
    # Simulate high load (3.6 out of 4.0 cores used = 90%)
    state.active_tasks.append({
        "task_id": "heavy_task",
        "cpu": 3.6,
        "ram": 4096,
        "finish_time": 9999999999.0
    })

    task = TaskSpec(
        task_id="new_task",
        task_type="yolo",
        required_cpu=1.0,
        required_ram_mb=1024,
        execution_duration_sec=3.0,
        max_budget=5.0,
        deadline_sec=4.0,
        base_cost=2.0
    )

    # Congestion gate must reject this task to prevent SLA breach
    assert state.can_fit(task, safe_threshold=0.85) is False

def test_hybrid_strategy_bidding():
    strategy = CognitiveHybridMasterStrategy()
    state = NodeState(node_id="smart_agent", cpu_cores=8.0, ram_mb=16384, green_energy_ratio=0.85)
    
    task = TaskSpec(
        task_id="t1",
        task_type="inference",
        required_cpu=2.0,
        required_ram_mb=2048,
        execution_duration_sec=3.0,
        max_budget=4.0,
        deadline_sec=4.5,
        base_cost=1.5
    )
    auction = AuctionSpec(
        auction_id="auc_1",
        round_number=1,
        task=task,
        created_at=100.0,
        duration_sec=2.0,
        status="OPEN"
    )

    bid = strategy.calculate_bid(auction, state)
    assert bid is not None
    assert bid >= task.base_cost
    assert bid <= task.max_budget

def test_multi_agent_deliberation_consensus():
    from agent.strategies.multi_agent_team import MultiAgentReasoningStrategy
    from agent.multi_agent.models import AgentRole, DeliberationStatus

    strategy = MultiAgentReasoningStrategy()
    state = NodeState(node_id="smart_agent_04", cpu_cores=8.0, ram_mb=16384, green_energy_ratio=0.85)

    task = TaskSpec(
        task_id="task_consensus_01",
        task_type="yolo_inference",
        required_cpu=2.0,
        required_ram_mb=2048,
        execution_duration_sec=3.0,
        max_budget=5.0,
        deadline_sec=5.0,
        base_cost=1.8
    )
    auction = AuctionSpec(
        auction_id="auc_consensus",
        round_number=1,
        task=task,
        created_at=100.0,
        duration_sec=2.0,
        status="OPEN"
    )

    bid = strategy.calculate_bid(auction, state)
    assert bid is not None
    assert bid >= task.base_cost
    assert bid <= task.max_budget

    delib = strategy.last_deliberation
    assert delib is not None
    assert delib.decision == "BID_SUBMITTED"
    assert delib.confidence_score >= 0.85
    assert len(delib.steps) >= 3

    roles = [s.role for s in delib.steps]
    assert AgentRole.MARKET_ANALYST in roles
    assert AgentRole.CAPACITY_GUARDIAN in roles
    assert AgentRole.GREEN_ARBITRAGE in roles
    assert AgentRole.SYNTHESIZER in roles

    # Sponsor telemetry verification (NVIDIA NeMo, Meterless, Zetaris)
    assert "nvidia_guardrail" in delib.sponsor_telemetry
    assert "meterless_metering" in delib.sponsor_telemetry
    assert "zetaris_telemetry" in delib.sponsor_telemetry
    assert delib.sponsor_telemetry["nvidia_guardrail"]["status"] == "COMPLIANT"

def test_multi_agent_capacity_guardian_objection():
    from agent.strategies.multi_agent_team import MultiAgentReasoningStrategy
    from agent.multi_agent.models import AgentRole, DeliberationStatus

    strategy = MultiAgentReasoningStrategy()
    state = NodeState(node_id="overloaded_node", cpu_cores=4.0, ram_mb=8192, green_energy_ratio=0.85)
    # Simulate 3.6 of 4.0 cores in use = 90% load
    state.active_tasks.append({
        "task_id": "heavy_sim",
        "cpu": 3.6,
        "ram": 4096,
        "finish_time": 9999999999.0
    })

    task = TaskSpec(
        task_id="task_fail",
        task_type="slam_mapping",
        required_cpu=1.0,
        required_ram_mb=1024,
        execution_duration_sec=4.0,
        max_budget=6.0,
        deadline_sec=4.5,
        base_cost=2.0
    )
    auction = AuctionSpec(
        auction_id="auc_overload",
        round_number=2,
        task=task,
        created_at=100.0,
        duration_sec=2.0,
        status="OPEN"
    )

    bid = strategy.calculate_bid(auction, state)
    # Capacity guardian must veto the bid to avoid thermal SLA penalty
    assert bid is None
    delib = strategy.last_deliberation
    assert delib is not None
    assert delib.decision == "TASK_SKIPPED"
    assert delib.sla_risk_level == "CRITICAL"

    objection_steps = [s for s in delib.steps if s.status == DeliberationStatus.OBJECTION]
    assert len(objection_steps) >= 1
    assert objection_steps[0].role == AgentRole.CAPACITY_GUARDIAN

