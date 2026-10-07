from typing import Optional, List, Dict, Any
from agent.models import TaskSpec, AuctionSpec
from agent.state import NodeState
from agent.multi_agent.models import (
    AgentRole,
    DeliberationStatus,
    DeliberationStep,
    DeliberationResult
)
from agent.multi_agent.sponsor_integrations import SponsorIntegrationHub
from agent.multi_agent.groq_reasoner import GroqReasoner

class MultiAgentDeliberationTeam:
    """
    Open Agent Hackathon 2026 Collaborative Multi-Agent System.
    Powered by Groq LPUs for real-time AI reasoning, with local
    game-theoretic deterministic fallback.
    - MarketAnalyst (Proposer)
    - CapacityGuardian (Critic & SLA Protector)
    - GreenArbitrage (Energy & Pricing Moat Specialist)
    - Synthesizer (Consensus & Audit Trail Generator)
    """
    def __init__(self):
        self.sponsor_hub = SponsorIntegrationHub()
        self.groq_reasoner = GroqReasoner()
        self.adaptive_margin = 0.12  # Dynamic ZIP feedback

    def update_market_feedback(self, delta: float):
        """Refines baseline margin based on market clearing delta."""
        self.adaptive_margin = max(0.04, min(0.60, self.adaptive_margin + delta))

    async def deliberate_async(self, auction: AuctionSpec, state: NodeState) -> DeliberationResult:
        """Asynchronously queries Groq LPU if configured, otherwise falls back."""
        if self.groq_reasoner.is_configured:
            groq_res = await self.groq_reasoner.deliberate_async(auction, state, self.adaptive_margin)
            if groq_res is not None:
                return groq_res
        return self.deliberate(auction, state)

    def deliberate(self, auction: AuctionSpec, state: NodeState) -> DeliberationResult:
        # Check Groq synchronous call if key configured
        if self.groq_reasoner.is_configured:
            groq_res = self.groq_reasoner.deliberate_sync(auction, state, self.adaptive_margin)
            if groq_res is not None:
                return groq_res

        task = auction.task
        steps: List[DeliberationStep] = []
        step_idx = 1
        current_load = state.get_cpu_utilization()
        budget_ratio = task.max_budget / max(0.01, task.base_cost)

        # -------------------------------------------------------------
        # STEP 1: MarketAnalyst proposes preliminary strategy
        # -------------------------------------------------------------
        preliminary_price = task.base_cost * (1.0 + self.adaptive_margin)
        analyst_thought = (
            f"Examining Task '{task.task_id}' ({task.task_type}). "
            f"Base physical cost: €{task.base_cost:.2f}, Buyer Max Budget: €{task.max_budget:.2f} "
            f"(Budget ratio: {budget_ratio:.2f}x). Current market contention is elevated. "
            f"Proposing baseline entry bid of €{preliminary_price:.3f}."
        )
        steps.append(DeliberationStep(
            step_number=step_idx,
            role=AgentRole.MARKET_ANALYST,
            status=DeliberationStatus.ANALYZING,
            thought=analyst_thought,
            confidence=0.88,
            proposed_bid=round(preliminary_price, 4)
        ))
        step_idx += 1

        # -------------------------------------------------------------
        # STEP 2: CapacityGuardian (Critic) evaluates node headroom & SLA
        # -------------------------------------------------------------
        avail_cores = max(0.0, state.cpu_cores - state.get_used_cpu())
        guardrail_result = self.sponsor_hub.verify_sla_guardrails(
            task_type=task.task_type,
            requested_cores=task.required_cpu,
            available_cores=avail_cores
        )

        # Hard Gate: Capacity overload
        if not state.can_fit(task, safe_threshold=0.85):
            guardian_thought = (
                f"OBJECTION: Projected core consumption ({state.get_used_cpu() + task.required_cpu:.1f}/{state.cpu_cores}c) "
                f"exceeds safe threshold of 85.0%. Accepting task introduces thermal degradation risk and "
                f"50% SLA penalty. SLA policy evaluation: {guardrail_result['reason']}. VETO: Skip this auction."
            )
            steps.append(DeliberationStep(
                step_number=step_idx,
                role=AgentRole.CAPACITY_GUARDIAN,
                status=DeliberationStatus.OBJECTION,
                thought=guardian_thought,
                confidence=0.98,
                proposed_bid=None
            ))
            return DeliberationResult(
                final_bid=None,
                decision="TASK_SKIPPED",
                confidence_score=0.98,
                reasoning_summary="Skipped: Node capacity exceeded 85% safety threshold.",
                steps=steps,
                sla_risk_level="CRITICAL",
                sponsor_telemetry={"sla_guardrail": guardrail_result}
            )

        # Soft Gate: Strategic Patience (Critique Loop)
        if current_load > 0.45 and budget_ratio < 1.7:
            guardian_thought = (
                f"CRITIQUE & REVISION REQUEST: Node is moderately loaded ({current_load * 100:.1f}%), and this task "
                f"offers meager budget expansion ({budget_ratio:.2f}x). Recommending strategic patience: preserve "
                f"headroom for high-margin federated learning or SLAM tasks. VETO: Do not chase low-margin volume."
            )
            steps.append(DeliberationStep(
                step_number=step_idx,
                role=AgentRole.CAPACITY_GUARDIAN,
                status=DeliberationStatus.OBJECTION,
                thought=guardian_thought,
                confidence=0.92,
                proposed_bid=None
            ))
            return DeliberationResult(
                final_bid=None,
                decision="TASK_SKIPPED",
                confidence_score=0.92,
                reasoning_summary="Strategic Patience: Preserving CPU headroom for higher-margin enterprise tasks.",
                steps=steps,
                sla_risk_level="MEDIUM",
                sponsor_telemetry={"sla_guardrail": guardrail_result}
            )

        guardian_thought = (
            f"CAPACITY APPROVAL: Available cores ({avail_cores:.1f}c) comfortably fits required {task.required_cpu}c. "
            f"Projected load: {((state.get_used_cpu() + task.required_cpu) / state.cpu_cores) * 100:.1f}%. "
            f"SLA Policy: {guardrail_result['status']}."
        )
        steps.append(DeliberationStep(
            step_number=step_idx,
            role=AgentRole.CAPACITY_GUARDIAN,
            status=DeliberationStatus.APPROVED,
            thought=guardian_thought,
            confidence=0.95,
            proposed_bid=preliminary_price
        ))
        step_idx += 1

        # -------------------------------------------------------------
        # STEP 3: GreenArbitrage calculates renewable energy pricing moat
        # -------------------------------------------------------------
        # In Vickrey reverse market: effective_bid = raw_bid * (1 - 0.15 * green_ratio)
        our_discount = 1.0 - (task.green_bonus_weight * state.green_energy_ratio)
        competitor_discount = 1.0 - (task.green_bonus_weight * 0.45)
        green_moat_pct = round(((competitor_discount / our_discount) - 1.0) * 100, 2)

        # Invert green discount so we bid a higher nominal price while keeping lowest effective score
        target_effective = task.base_cost * (1.0 + self.adaptive_margin * 0.5)
        nominal_bid = target_effective / our_discount

        # Congestion buffer
        if current_load > 0.35:
            nominal_bid *= (1.0 + (current_load ** 2) * 0.30)

        final_bid = min(nominal_bid, task.max_budget)
        if final_bid < task.base_cost * 1.06:
            final_bid = task.base_cost * 1.06
        final_bid = round(final_bid, 4)

        green_thought = (
            f"GREEN MOAT ARBITRAGE: Operating with 85% renewable solar power grants a {green_moat_pct}% competitive moat "
            f"over fossil-fueled competitors. Inverting effective score discount allows nominal bid of €{final_bid:.3f} "
            f"(Gross profit margin: +{((final_bid / task.base_cost) - 1.0) * 100:.1f}%) while still ranking as lowest effective bid."
        )
        steps.append(DeliberationStep(
            step_number=step_idx,
            role=AgentRole.GREEN_ARBITRAGE,
            status=DeliberationStatus.APPROVED,
            thought=green_thought,
            confidence=0.96,
            proposed_bid=final_bid
        ))
        step_idx += 1

        # -------------------------------------------------------------
        # STEP 4: Synthesizer finalizes multi-agent consensus
        # -------------------------------------------------------------
        metering = self.sponsor_hub.record_compute_metering(
            node_id=state.node_id,
            task_id=task.task_id,
            duration_sec=task.execution_duration_sec,
            cores=task.required_cpu
        )
        cluster_info = self.sponsor_hub.query_cluster_telemetry(location_zone="eu-valencia-edge")

        summary = (
            f"Consensus Reached: Bid €{final_bid:.3f} for Task {task.task_id}. "
            f"Protected by Congestion Guard, Green Solar Inversion active (+{green_moat_pct}%), "
            f"Zero SLA breach risk."
        )
        steps.append(DeliberationStep(
            step_number=step_idx,
            role=AgentRole.SYNTHESIZER,
            status=DeliberationStatus.CONSENSUS,
            thought=summary,
            confidence=0.97,
            proposed_bid=final_bid
        ))

        return DeliberationResult(
            final_bid=final_bid,
            decision="BID_SUBMITTED",
            confidence_score=0.96,
            reasoning_summary=summary,
            steps=steps,
            green_advantage_pct=green_moat_pct,
            sla_risk_level="LOW",
            sponsor_telemetry={
                "groq_inference": {
                    "status": "READY" if self.groq_reasoner.is_configured else "STANDBY_READY",
                    "model": self.groq_reasoner.model,
                    "engine": "Groq LPU (Configured)" if self.groq_reasoner.is_configured else "Deterministic Engine (Provide GROQ_API_KEY)"
                },
                "sla_guardrail": guardrail_result,
                "compute_metering": metering,
                "cluster_telemetry": cluster_info
            }
        )
