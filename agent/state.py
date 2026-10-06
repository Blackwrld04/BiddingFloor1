import time
from typing import Dict, List, Any
from agent.models import TaskSpec

class NodeState:
    def __init__(
        self,
        node_id: str = "edge_agent_smart_04",
        name: str = "CognitiveSwarmBot (Champion)",
        cpu_cores: float = 8.0,
        ram_mb: int = 16384,
        green_energy_ratio: float = 0.85,
        base_cost_per_core_sec: float = 0.05
    ):
        self.node_id = node_id
        self.name = name
        self.cpu_cores = cpu_cores
        self.ram_mb = ram_mb
        self.green_energy_ratio = green_energy_ratio
        self.base_cost_per_core_sec = base_cost_per_core_sec
        self.active_tasks: List[Dict[str, Any]] = []
        
        # Local performance telemetry
        self.total_bids = 0
        self.total_wins = 0
        self.cumulative_profit = 0.0
        self.sla_breaches = 0

    def cleanup_finished(self):
        now = time.time()
        self.active_tasks = [t for t in self.active_tasks if t["finish_time"] > now]

    def get_used_cpu(self) -> float:
        self.cleanup_finished()
        return sum(t["cpu"] for t in self.active_tasks)

    def get_used_ram(self) -> int:
        self.cleanup_finished()
        return sum(t["ram"] for t in self.active_tasks)

    def get_cpu_utilization(self) -> float:
        return min(1.0, self.get_used_cpu() / self.cpu_cores)

    def get_ram_utilization(self) -> float:
        return min(1.0, self.get_used_ram() / self.ram_mb)

    def can_fit(self, task: TaskSpec, safe_threshold: float = 0.90) -> bool:
        """
        Safety check: avoids bidding if task would overload the node beyond safe threshold,
        which triggers SLA degradation penalties.
        """
        self.cleanup_finished()
        projected_cpu = (self.get_used_cpu() + task.required_cpu) / self.cpu_cores
        projected_ram = (self.get_used_ram() + task.required_ram_mb) / self.ram_mb
        return (projected_cpu <= safe_threshold) and (projected_ram <= safe_threshold)

    def record_win(self, task: TaskSpec, execution_duration: float, profit: float, sla_violated: bool):
        now = time.time()
        self.total_wins += 1
        self.cumulative_profit += profit
        if sla_violated:
            self.sla_breaches += 1

        self.active_tasks.append({
            "task_id": task.task_id,
            "cpu": task.required_cpu,
            "ram": task.required_ram_mb,
            "finish_time": now + execution_duration
        })

    def to_registration_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "cpu_cores": self.cpu_cores,
            "ram_mb": self.ram_mb,
            "hardware_type": "smart_edge_gpu_cluster",
            "location_zone": "eu-valencia-edge",
            "green_energy_ratio": self.green_energy_ratio,
            "base_cost_per_core_sec": self.base_cost_per_core_sec
        }
