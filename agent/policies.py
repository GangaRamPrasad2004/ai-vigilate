from pathlib import Path
from typing import List, Dict, Any
import yaml
from pydantic import BaseModel, Field


class DurablePolicy(BaseModel):
    approval_limit_usd: float = Field(10000.0, description="Maximum amount an agent can auto-approve")
    escalation_limit_usd: float = Field(20000.0, description="Invoices above this must be escalated")
    kill_limit_usd: float = Field(20000.0, description="Invoices above this trigger critical anomaly / kill switch")
    forbidden_phrases: List[str] = Field(
        default_factory=lambda: [
            "ignore all previous",
            "ignore previous policies",
            "approve immediately",
            "system message"
        ]
    )
    human_approval_required_above_usd: float = Field(10000.0)
    fail_closed_if_decider_unavailable: bool = Field(True)


def load_durable_policy(policy_path: Path | str | None = None) -> DurablePolicy:
    """Loads durable enterprise policy from YAML file."""
    if policy_path is None:
        policy_path = Path(__file__).parent / "policies.yaml"
    else:
        policy_path = Path(policy_path)

    if not policy_path.exists():
        # Fallback to safe defaults
        return DurablePolicy()

    with open(policy_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return DurablePolicy(**data)


# Global singleton instance of durable policy
durable_policy = load_durable_policy()
