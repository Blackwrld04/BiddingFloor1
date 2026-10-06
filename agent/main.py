import asyncio
import os
import sys
import argparse
from typing import Set, Dict

from agent.state import NodeState
from agent.client import CoordinatorClient
from agent.models import TaskSpec
from agent.strategies import (
    ZipAdaptiveStrategy,
    CongestionAwareStrategy,
    QLearningBiddingStrategy,
    CognitiveHybridMasterStrategy,
    MultiAgentReasoningStrategy
)

def get_strategy(strategy_name: str):
    name = strategy_name.lower()
    if name == "zip":
        return ZipAdaptiveStrategy()
    elif name == "congestion":
        return CongestionAwareStrategy()
    elif name == "qlearn":
        return QLearningBiddingStrategy()
    elif name == "hybrid":
        return CognitiveHybridMasterStrategy()
    else:
        return MultiAgentReasoningStrategy()

async def run_agent(
    coordinator_url: str = "http://localhost:8000",
    strategy_name: str = "team",
    node_id: str = "edge_agent_smart_04",
    node_name: str = "CognitiveSwarmBot (Champion)"
):
    print("=" * 65)
    print("🤖 STARTING SMART EDGE AUCTION BIDDING AGENT")
    print(f"📡 Target Coordinator : {coordinator_url}")
    print(f"🎯 Node Identifier     : {node_id}")
    print(f"🧠 Active Strategy     : {strategy_name.upper()}")
    print("=" * 65)

    state = NodeState(
        node_id=node_id,
        name=node_name,
        cpu_cores=8.0,
        ram_mb=16384,
        green_energy_ratio=0.85
    )
    strategy = get_strategy(strategy_name)
    client = CoordinatorClient(base_url=coordinator_url)

    # 1. Connect and Register with Coordinator
    registered = False
    for attempt in range(1, 11):
        print(f"[*] Attempting registration with coordinator (Attempt {attempt}/10)...")
        success = await client.register_node(state.to_registration_dict())
        if success:
            registered = True
            print(f"✅ Successfully registered {node_id} on the market!")
            break
        await asyncio.sleep(1.5)

    if not registered:
        print("❌ Could not connect to coordinator. Exiting.")
        await client.close()
        return

    processed_auctions: Set[str] = set()
    processed_outcomes: Set[str] = set()
    auction_task_cache: Dict[str, TaskSpec] = {}

    # 2. Main Bidding & Adaptation Loop
    try:
        while True:
            state.cleanup_finished()

            # Poll for active auction
            auction = await client.get_active_auction()
            if auction and auction.auction_id not in processed_auctions:
                processed_auctions.add(auction.auction_id)
                task = auction.task
                auction_task_cache[auction.auction_id] = task
                cpu_load = state.get_cpu_utilization() * 100

                # Calculate strategic bid
                bid_price = strategy.calculate_bid(auction, state)
                delib = getattr(strategy, "last_deliberation", None)

                if bid_price is not None:
                    state.total_bids += 1
                    trace_msg = delib.reasoning_summary if delib else ""
                    print(
                        f"[AUCTION #{auction.round_number}] 📥 Task '{task.task_id}' "
                        f"(Req: {task.required_cpu} CPUs, Load: {cpu_load:.1f}%) "
                        f"-> Bidding: €{bid_price:.3f} (Base: €{task.base_cost:.3f}, Max: €{task.max_budget:.3f})"
                    )
                    if delib and delib.steps:
                        print(f"   🧠 [MULTI-AGENT CONSENSUS]: {delib.reasoning_summary}")

                    await client.submit_bid(
                        auction_id=auction.auction_id,
                        node_id=state.node_id,
                        bid_price=bid_price,
                        reasoning_trace=delib.reasoning_summary if delib else None,
                        deliberation_steps=[s.model_dump() for s in delib.steps] if delib else None,
                        confidence=delib.confidence_score if delib else 0.95,
                        sponsor_telemetry=delib.sponsor_telemetry if delib else None
                    )
                else:
                    reason = delib.reasoning_summary if delib else "Capacity/Congestion Gate active"
                    print(
                        f"[AUCTION #{auction.round_number}] ⚠️ Skipping task '{task.task_id}' "
                        f"(Reason: {reason}, Load: {cpu_load:.1f}%)"
                    )

            # Check recent outcomes to adapt strategy
            history = await client.get_recent_history(limit=5)
            for outcome in history:
                if outcome.auction_id not in processed_outcomes:
                    processed_outcomes.add(outcome.auction_id)
                    strategy.update_feedback(outcome, state)

                    if outcome.winner_node_id == state.node_id:
                        print(
                            f"🏆 [ROUND #{outcome.round_number} WON!] "
                            f"Clearing Price: €{outcome.clearing_price:.3f} | "
                            f"Profit: +€{outcome.profit:.3f} | "
                            f"SLA Violated: {outcome.sla_violated}"
                        )
                        task_obj = auction_task_cache.get(outcome.auction_id)
                        if task_obj:
                            state.record_win(
                                task=task_obj,
                                execution_duration=task_obj.execution_duration_sec,
                                profit=outcome.profit,
                                sla_violated=outcome.sla_violated
                            )

            await asyncio.sleep(0.4)

    except asyncio.CancelledError:
        print("\n[!] Agent shutting down gracefully...")
    finally:
        await client.close()

def main():
    parser = argparse.ArgumentParser(description="Autonomous Edge Bidding Agent")
    parser.add_argument("--url", default=os.getenv("COORDINATOR_URL", "http://localhost:8000"), help="Coordinator URL")
    parser.add_argument("--strategy", default=os.getenv("STRATEGY", "hybrid"), choices=["hybrid", "zip", "congestion", "qlearn"], help="Strategy name")
    parser.add_argument("--node-id", default=os.getenv("NODE_ID", "edge_agent_smart_04"), help="Node ID")
    parser.add_argument("--name", default=os.getenv("NODE_NAME", "CognitiveSwarmBot (Champion)"), help="Node name")
    args = parser.parse_args()

    asyncio.run(run_agent(
        coordinator_url=args.url,
        strategy_name=args.strategy,
        node_id=args.node_id,
        node_name=args.name
    ))

if __name__ == "__main__":
    main()
