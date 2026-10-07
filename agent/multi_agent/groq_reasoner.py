import os
import time
import json
import logging
from typing import Optional, Dict, Any, List
import httpx
from dotenv import load_dotenv

from agent.models import AuctionSpec
from agent.state import NodeState
from agent.multi_agent.models import (
    AgentRole,
    DeliberationStatus,
    DeliberationStep,
    DeliberationResult
)
from agent.multi_agent.sponsor_integrations import SponsorIntegrationHub

load_dotenv()
logger = logging.getLogger("GroqReasoner")

SYSTEM_PROMPT = """You are the Multi-Agent Reasoning Brain for CognitiveSwarm, an autonomous AI edge bidding agent participating in a decentralized reverse auction market (Second-Price Vickrey mechanism with Green Energy weighting).

You must simulate the collaborative deliberation of four distinct agent roles:
1. MARKET_ANALYST: Analyzes task resource specs (CPU, RAM, deadline), base hardware cost, and buyer max budget. Formulates entry bid proposal based on market contention.
2. CAPACITY_GUARDIAN (Critic & SLA Protector): Assesses node headroom.
   - VETO RULE: If (current_used_cpu + task_required_cpu) / total_cores > 0.85 (85% threshold), MUST raise an OBJECTION and VETO the task (decision="TASK_SKIPPED", final_bid=null, status="OBJECTION") to prevent thermal throttling and 50% SLA penalties.
   - STRATEGIC PATIENCE RULE: If current load > 45% and buyer budget ratio (max_budget / base_cost) < 1.7x, raise an OBJECTION to conserve cores for high-margin enterprise workloads.
   - Otherwise, APPROVE.
3. GREEN_ARBITRAGE: Operating with 85% renewable solar power grants a competitive discount in effective scoring: Effective_Bid = Raw_Bid * (1 - 0.15 * Green_Ratio). Invert this discount to bid a higher nominal price (+15% to +25% margin) while still winning as the lowest effective bidder on the floor.
4. SYNTHESIZER: Unifies multi-agent signals into an explainable consensus. Emits the final bid (or null if skipped), confidence score, risk assessment, and summary.

You MUST respond strictly with valid JSON conforming to this schema:
{
  "decision": "BID_SUBMITTED" or "TASK_SKIPPED",
  "final_bid": <float or null>,
  "confidence_score": <float between 0.80 and 1.0>,
  "reasoning_summary": "<concise consensus summary sentence>",
  "green_advantage_pct": <float, e.g. 6.88>,
  "sla_risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "steps": [
    {
      "step_number": 1,
      "role": "MARKET_ANALYST",
      "status": "ANALYZING",
      "thought": "<string>",
      "confidence": <float>,
      "proposed_bid": <float>
    },
    {
      "step_number": 2,
      "role": "CAPACITY_GUARDIAN",
      "status": "APPROVED" | "OBJECTION",
      "thought": "<string>",
      "confidence": <float>,
      "proposed_bid": <float or null>
    },
    {
      "step_number": 3,
      "role": "GREEN_ARBITRAGE",
      "status": "APPROVED" | "OBJECTION",
      "thought": "<string>",
      "confidence": <float>,
      "proposed_bid": <float>
    },
    {
      "step_number": 4,
      "role": "SYNTHESIZER",
      "status": "CONSENSUS" | "OBJECTION",
      "thought": "<string>",
      "confidence": <float>,
      "proposed_bid": <float or null>
    }
  ]
}
"""

class GroqReasoner:
    """
    Ultra-Fast LLM Reasoning Engine powered by Groq LPUs.
    Provides real-time multi-agent deliberation and critique traces.
    """
    def __init__(self):
        self._api_key: Optional[str] = None
        self._model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip()
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.timeout_sec = float(os.getenv("GROQ_TIMEOUT_SEC", "4.0"))
        self.sponsor_hub = SponsorIntegrationHub()
        self._last_call_time: float = 0.0
        self._cooldown_until: float = 0.0
        self.dispatch_interval_sec: float = float(os.getenv("GROQ_DISPATCH_INTERVAL_SEC", "12.0"))

    @property
    def api_key(self) -> str:
        if self._api_key is not None:
            return self._api_key
        key = os.getenv("GROQ_API_KEY", "").strip()
        if not key:
            load_dotenv(override=True)
            key = os.getenv("GROQ_API_KEY", "").strip()
        return key

    @api_key.setter
    def api_key(self, value: str):
        self._api_key = value

    @property
    def model(self) -> str:
        return os.getenv("GROQ_MODEL", self._model).strip()

    @model.setter
    def model(self, value: str):
        self._model = value

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 8)

    def _build_payload(self, auction: AuctionSpec, state: NodeState, adaptive_margin: float) -> Dict[str, Any]:
        task = auction.task
        used_cpu = state.get_used_cpu()
        load_pct = state.get_cpu_utilization() * 100
        budget_ratio = round(task.max_budget / max(0.01, task.base_cost), 2)

        user_content = (
            "Evaluate this auction task and edge node state. Return a JSON object conforming strictly to the 4-step deliberation schema:\n"
            + json.dumps({
                "task": {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "required_cpu": task.required_cpu,
                    "required_ram_mb": task.required_ram_mb,
                    "base_cost": task.base_cost,
                    "max_budget": task.max_budget,
                    "budget_ratio": budget_ratio,
                    "deadline_sec": task.deadline_sec
                },
                "edge_node": {
                    "node_id": state.node_id,
                    "total_cpu_cores": state.cpu_cores,
                    "used_cpu_cores": used_cpu,
                    "current_load_pct": round(load_pct, 1),
                    "green_energy_ratio": state.green_energy_ratio,
                    "active_tasks_count": len(state.active_tasks)
                },
                "market_context": {
                    "round_number": auction.round_number,
                    "adaptive_margin_hint": round(adaptive_margin, 3),
                    "overload_threshold_pct": 85.0
                }
            })
        )

        concise_system = (
            SYSTEM_PROMPT
            + "\nConstraint: Keep each agent role thought under 22 words so response fits in concise JSON."
        )

        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": concise_system},
                {"role": "user", "content": user_content}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 650
        }

    def _parse_groq_response(
        self,
        raw_json: Dict[str, Any],
        auction: AuctionSpec,
        state: NodeState,
        latency_ms: float
    ) -> Optional[DeliberationResult]:
        task = auction.task
        decision = raw_json.get("decision", "BID_SUBMITTED")
        raw_final_bid = raw_json.get("final_bid")
        confidence = float(raw_json.get("confidence_score", 0.94))
        summary = str(raw_json.get("reasoning_summary", "Consensus reached via Groq LPU."))
        green_adv = float(raw_json.get("green_advantage_pct", 6.88))
        sla_risk = str(raw_json.get("sla_risk_level", "LOW"))

        final_bid: Optional[float] = None
        if decision == "BID_SUBMITTED" and raw_final_bid is not None:
            final_bid = float(raw_final_bid)
            # Bound bid between marginal cost floor and max budget
            final_bid = max(task.base_cost * 1.05, min(final_bid, task.max_budget))
            final_bid = round(final_bid, 4)
        else:
            final_bid = None
            decision = "TASK_SKIPPED"

        # Parse steps
        steps: List[DeliberationStep] = []
        raw_steps = raw_json.get("steps", [])
        for idx, s in enumerate(raw_steps, 1):
            role_str = s.get("role", "SYNTHESIZER").upper()
            try:
                role = AgentRole(role_str)
            except Exception:
                role = AgentRole.SYNTHESIZER

            status_str = s.get("status", "APPROVED").upper()
            try:
                status = DeliberationStatus(status_str)
            except Exception:
                status = DeliberationStatus.APPROVED

            step_bid = s.get("proposed_bid")
            if step_bid is not None:
                step_bid = round(float(step_bid), 4)

            steps.append(DeliberationStep(
                step_number=s.get("step_number", idx),
                role=role,
                status=status,
                thought=s.get("thought", ""),
                confidence=float(s.get("confidence", 0.9)),
                proposed_bid=step_bid
            ))

        # Ensure Synthesizer step is always included in multi-agent consensus
        if not any(s.role == AgentRole.SYNTHESIZER for s in steps):
            steps.append(DeliberationStep(
                step_number=len(steps) + 1,
                role=AgentRole.SYNTHESIZER,
                status=DeliberationStatus.CONSENSUS if final_bid is not None else DeliberationStatus.OBJECTION,
                thought=summary,
                confidence=confidence,
                proposed_bid=final_bid
            ))

        # Attach edge telemetry hooks (Groq LPU + SLA Guardrails + Compute Metering + Cluster Telemetry)
        avail_cores = max(0.0, state.cpu_cores - state.get_used_cpu())
        guardrail = self.sponsor_hub.verify_sla_guardrails(
            task_type=task.task_type,
            requested_cores=task.required_cpu,
            available_cores=avail_cores
        )
        metering = self.sponsor_hub.record_compute_metering(
            node_id=state.node_id,
            task_id=task.task_id,
            duration_sec=task.execution_duration_sec,
            cores=task.required_cpu
        )
        cluster_info = self.sponsor_hub.query_cluster_telemetry(location_zone="eu-valencia-edge")

        sponsor_telemetry = {
            "groq_inference": {
                "status": "ACTIVE_LPU",
                "model": self.model,
                "latency_ms": round(latency_ms, 1),
                "engine": "Groq Tensor Streaming Processor"
            },
            "sla_guardrail": guardrail,
            "compute_metering": metering,
            "cluster_telemetry": cluster_info
        }

        return DeliberationResult(
            final_bid=final_bid,
            decision=decision,
            confidence_score=confidence,
            reasoning_summary=summary,
            steps=steps,
            green_advantage_pct=green_adv,
            sla_risk_level=sla_risk,
            sponsor_telemetry=sponsor_telemetry
        )

    def _extract_cooldown_from_error(self, res: httpx.Response) -> float:
        """Extracts seconds to wait from Groq 429 response or returns a safe 15s default."""
        try:
            err_data = res.json()
            msg = err_data.get("error", {}).get("message", "")
            import re
            m = re.search(r"try again in ([0-9.]+)s", msg)
            if m:
                return float(m.group(1)) + 1.0
        except Exception:
            pass
        return 15.0

    async def deliberate_async(
        self,
        auction: AuctionSpec,
        state: NodeState,
        adaptive_margin: float
    ) -> Optional[DeliberationResult]:
        """Calls Groq API asynchronously to generate real LLM deliberation."""
        if not self.is_configured:
            return None

        now = time.time()
        if now < self._cooldown_until:
            return None
        if self.dispatch_interval_sec > 0 and (now - self._last_call_time) < self.dispatch_interval_sec:
            return None

        payload = self._build_payload(auction, state, adaptive_margin)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                res = await client.post(self.api_url, json=payload, headers=headers)
                latency_ms = (time.time() - start_time) * 1000.0

                if res.status_code == 200:
                    self._last_call_time = time.time()
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return self._parse_groq_response(parsed, auction, state, latency_ms)
                elif res.status_code == 429:
                    cooldown = self._extract_cooldown_from_error(res)
                    self._cooldown_until = time.time() + cooldown
                    logger.info(f"[Groq LPU] Rate ceiling reached; pacing for {cooldown:.1f}s (autonomous fallback active)")
                    return None
                else:
                    logger.warning(f"Groq API error HTTP {res.status_code}: {res.text[:200]}")
                    return None
        except Exception as e:
            logger.warning(f"Groq deliberate_async failed ({type(e).__name__}): {e}. Falling back to deterministic engine.")
            return None

    def deliberate_sync(
        self,
        auction: AuctionSpec,
        state: NodeState,
        adaptive_margin: float
    ) -> Optional[DeliberationResult]:
        """Synchronous wrapper for Groq API call."""
        if not self.is_configured:
            return None

        now = time.time()
        if now < self._cooldown_until:
            return None
        if self.dispatch_interval_sec > 0 and (now - self._last_call_time) < self.dispatch_interval_sec:
            return None

        payload = self._build_payload(auction, state, adaptive_margin)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        start_time = time.time()
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                res = client.post(self.api_url, json=payload, headers=headers)
                latency_ms = (time.time() - start_time) * 1000.0

                if res.status_code == 200:
                    self._last_call_time = time.time()
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return self._parse_groq_response(parsed, auction, state, latency_ms)
                elif res.status_code == 429:
                    cooldown = self._extract_cooldown_from_error(res)
                    self._cooldown_until = time.time() + cooldown
                    logger.info(f"[Groq LPU] Rate ceiling reached; pacing for {cooldown:.1f}s (autonomous fallback active)")
                    return None
                else:
                    logger.warning(f"Groq API error HTTP {res.status_code}: {res.text[:200]}")
                    return None
        except Exception as e:
            logger.warning(f"Groq deliberate_sync failed ({type(e).__name__}): {e}. Falling back to deterministic engine.")
            return None
