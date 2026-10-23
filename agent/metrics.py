import json
from pathlib import Path
from typing import Dict, Any
from pydantic import BaseModel, Field


class DeciderMetrics(BaseModel):
    total_calls: int = 0
    total_latency_ms: float = 0.0
    average_latency_ms: float = 0.0
    allowed_count: int = 0
    blocked_count: int = 0
    escalated_count: int = 0
    kill_switch_count: int = 0
    estimated_tokens_saved: int = 0


class MetricsCollector:
    """Collects and aggregates performance and cost metrics for Strands Decider 2B."""

    def __init__(self, metrics_file: Path | str | None = None):
        if metrics_file is None:
            self.metrics_file = Path(__file__).parent.parent / "metrics" / "decider-metrics.json"
        else:
            self.metrics_file = Path(metrics_file)
        self.metrics = DeciderMetrics()

    def record_decision(
        self,
        decision: str,
        latency_ms: float,
        context_str: str,
        is_kill: bool = False
    ) -> None:
        """Records a single Decider decision event and updates estimates."""
        self.metrics.total_calls += 1
        self.metrics.total_latency_ms += latency_ms
        self.metrics.average_latency_ms = round(
            self.metrics.total_latency_ms / self.metrics.total_calls, 2
        )

        decision_clean = decision.lower()
        if is_kill:
            self.metrics.kill_switch_count += 1
            self.metrics.blocked_count += 1
        elif decision_clean in ("yes", "allow", "approved"):
            self.metrics.allowed_count += 1
        elif decision_clean in ("no", "block", "rejected"):
            self.metrics.blocked_count += 1
        elif decision_clean in ("escalate", "escalated"):
            self.metrics.escalated_count += 1
        else:
            self.metrics.blocked_count += 1

        # Token savings estimation:
        # Offloading binary classification to a 2B parameter decider saves full generative model reasoning tokens
        # Typically ~ 1 token per 4 characters of serialized context + prompt overhead (250 tokens)
        tokens_saved = (len(context_str) // 4) + 250
        self.metrics.estimated_tokens_saved += tokens_saved

        self.save_to_disk()

    def save_to_disk(self) -> None:
        """Persists metrics to json on disk."""
        try:
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metrics_file, "w", encoding="utf-8") as f:
                json.dump(self.metrics.model_dump(), f, indent=2)
        except Exception as exc:
            pass

    def get_summary(self) -> Dict[str, Any]:
        return self.metrics.model_dump()


# Singleton metrics collector
metrics_collector = MetricsCollector()
